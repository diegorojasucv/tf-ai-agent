import sqlite3
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from src.agents.graph import build_graph
from src.agents.runner import AgentSession
from src.memory.checkpointer import get_checkpointer
from src.memory.trace_store import get_trace_events, record_trace
from src.tools.dbt import validar_yaml as validar_mod
from src.tools.common import ToolError


class ScriptedLLM:
    """LLM de prueba: devuelve respuestas predefinidas, sin red."""

    def __init__(self, script: list[AIMessage]) -> None:
        self.script = list(script)
        self.seen: list[Any] = []

    def bind_tools(self, _tools: Any) -> "ScriptedLLM":
        return self

    def invoke(self, messages: Any) -> AIMessage:
        self.seen.append(messages)
        return self.script.pop(0)


def call(name: str, **args: Any) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"id-{name}"}])


class FakeGitHub:
    def __init__(self, base: str) -> None:
        self.base, self.calls = base, []

    def call(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if tool == "get_file_contents":
            return self.base
        return '{"html_url": "https://github.com/o/r/pull/9"}' if tool == "create_pull_request" else "ok"


GENERAR = dict(
    modelo="stg_orders", test="accepted_range", columna="subtotal",
    argumentos_json='{"min_value": 0, "max_value": 100000, "inclusive": false}',
)


@pytest.fixture(autouse=True)
def parse_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validar_mod, "run_dbt_parse", lambda *a: {"ejecutado": True, "ok": True, "duracion_s": 0.0})


@pytest.fixture
def env(manifest_path: Path, project_dir: Path, tmp_path: Path):
    base = (project_dir / "models/staging/stg_orders.yml").read_text()

    def make(script: list[AIMessage], gh: FakeGitHub | None = None, db: str = "agent.db"):
        llm = ScriptedLLM(script)
        gh = gh or FakeGitHub(base)
        database = tmp_path / db
        graph = build_graph(
            llm, github_client=gh, checkpointer=get_checkpointer(database), trace_db_path=database,
            manifest_path=manifest_path, project_dir=project_dir, repo="o/r", base="main",
        )
        return llm, gh, graph

    return make


def test_recorrido_principal_con_aprobacion_y_pr(env) -> None:
    llm, gh, graph = env([
        call("cargar_skill", nombre="dbt-testing"),
        call("buscar_columna", nombre_columna="subtotal", tabla_opcional="stg_orders"),
        call("generar_test", **GENERAR),
    ])
    session = AgentSession(graph, "t1")
    turn = session.send("agregá un test: subtotal en stg_orders entre 0 y 100000")
    assert turn["estado"] == "aprobacion"
    payload = turn["payload"]
    assert payload["test"] == "dbt_utils.accepted_range" and payload["validacion"]["valido"]
    assert "accepted_range" in payload["diff"] and gh.calls == []  # nada se escribe antes de aprobar
    done = session.resume({"accion": "aprobar"})
    assert done["estado"] == "completado" and done["pr"]["url"].endswith("/pull/9")
    assert [c[0] for c in gh.calls] == ["get_file_contents", "create_branch", "push_files", "create_pull_request"]
    pushed = gh.calls[2][1]["files"][0]
    assert pushed["content"] == payload["yaml_nuevo"] and gh.calls[2][1]["branch"] != "main"
    tools_used = [t["herramienta"] for t in done["trace"] if t["nodo"] in {"tools", "validate", "create_pr"}]
    assert tools_used == ["cargar_skill", "buscar_columna", "generar_test", "validar_yaml", "crear_pr"]


def test_eliminar_test_pasa_por_aprobacion_y_abre_pr(env) -> None:
    _, gh, graph = env([call("eliminar_test", modelo="stg_orders", test="unique", columna="order_id")])
    session = AgentSession(graph, "t-del")
    turn = session.send("sacá el unique de stg_orders.order_id")
    assert turn["estado"] == "aprobacion" and gh.calls == []
    assert turn["payload"]["operacion"] == "eliminar" and turn["payload"]["advertencias"]
    done = session.resume({"accion": "aprobar"})
    assert done["estado"] == "completado"
    titles = [c[1]["title"] for c in gh.calls if c[0] == "create_pull_request"]
    assert titles == ["test(dbt): eliminar unique en stg_orders.order_id"]


def test_guarda_entradas_y_salidas_completas_de_las_tools(env, tmp_path: Path) -> None:
    _, _, graph = env([call("generar_test", **GENERAR)], db="tool-traces.db")
    turn = AgentSession(graph, "t-traces").send("agrega rango")

    assert turn["estado"] == "aprobacion"
    events = get_trace_events("t-traces", tmp_path / "tool-traces.db")
    tool_event = next(event for event in events if event["name"] == "generar_test")
    validation_event = next(event for event in events if event["name"] == "validar_yaml")
    assert tool_event["input"]["modelo"] == "stg_orders"
    assert tool_event["input"]["columna"] == "subtotal"
    assert tool_event["output"]["data"]["test"] == "dbt_utils.accepted_range"
    assert "yaml_nuevo" in tool_event["output"]["data"]
    assert validation_event["input"]["schema_path"] == "models/staging/stg_orders.yml"
    assert validation_event["output"]["data"]["valido"] is True


def test_guarda_tokens_en_la_fila_de_cada_tool_sin_duplicar(env, tmp_path: Path) -> None:
    def usage(i: int, o: int) -> dict[str, int]:
        return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}

    two_tools = AIMessage("", tool_calls=[
        {"name": "cargar_skill", "args": {"nombre": "dbt-testing"}, "id": "a"},
        {"name": "listar_modelos", "args": {}, "id": "b"},
    ])
    question = AIMessage("¿En qué modelo?")
    script = [two_tools, question, call("generar_test", **GENERAR)]
    for msg, u in zip(script, [usage(100, 20), usage(150, 30), usage(200, 40)]):
        msg.usage_metadata = u
    _, _, graph = env(script, db="tokens.db")
    session = AgentSession(graph, "t-tokens")
    assert session.send("agrega rango")["estado"] == "pregunta"
    assert session.resume("stg_orders")["estado"] == "aprobacion"

    with sqlite3.connect(tmp_path / "tokens.db") as conn:
        rows = conn.execute(
            "SELECT name, input_tokens, output_tokens, total_tokens FROM tool_traces "
            "WHERE thread_id = 't-tokens' ORDER BY id"
        ).fetchall()
        total = conn.execute(
            "SELECT SUM(input_tokens), SUM(output_tokens), SUM(total_tokens) FROM tool_traces "
            "WHERE thread_id = 't-tokens'"
        ).fetchone()
    assert rows == [
        ("cargar_skill", 100, 20, 120),
        ("listar_modelos", None, None, None),
        ("ask_user", 150, 30, 180),
        ("generar_test", 200, 40, 240),
        ("validar_yaml", None, None, None),
    ]
    assert total == (450, 90, 540)


def test_migra_tabla_existente_sin_columnas_de_tokens(tmp_path: Path) -> None:
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE tool_traces (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, "
            "timestamp TEXT NOT NULL, node TEXT NOT NULL, name TEXT NOT NULL, ok INTEGER NOT NULL, "
            "duration_ms INTEGER NOT NULL, error_code TEXT, input_json TEXT NOT NULL, output_json TEXT NOT NULL)"
        )
    record_trace(
        thread_id="x", node="agent", name="llm", ok=True, duration_ms=1, input_data={}, output_data={},
        tokens={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}, path=database,
    )
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT total_tokens FROM tool_traces").fetchone() == (7,)


def test_pregunta_al_usuario_y_continua(env) -> None:
    llm, gh, graph = env([
        AIMessage("¿En qué modelo querés el test?"),
        call("generar_test", **GENERAR),
    ])
    session = AgentSession(graph, "t2")
    turn = session.send("test para subtotal")
    assert turn["estado"] == "pregunta" and "modelo" in turn["payload"]["mensaje"]
    assert session.resume("stg_orders")["estado"] == "aprobacion"
    assert any("stg_orders" in str(m.content) for m in llm.seen[-1])


def test_rechazo_no_crea_pr(env) -> None:
    _, gh, graph = env([call("generar_test", **GENERAR)])
    session = AgentSession(graph, "t3")
    session.send("x")
    done = session.resume({"accion": "rechazar", "motivo": "no corresponde"})
    assert done["estado"] == "rechazado" and "no corresponde" in done["mensaje"] and gh.calls == []


def test_edicion_se_revalida_y_se_sube_lo_editado(env) -> None:
    _, gh, graph = env([call("generar_test", **GENERAR)])
    session = AgentSession(graph, "t4")
    first = session.send("x")
    edited = first["payload"]["yaml_nuevo"].replace("100000", "5000")
    again = session.resume({"accion": "editar", "contenido_yaml": edited})
    assert again["estado"] == "aprobacion" and "5000" in again["payload"]["diff"]
    done = session.resume({"accion": "aprobar"})
    assert done["estado"] == "completado" and gh.calls[2][1]["files"][0]["content"] == edited


def test_decision_invalida_vuelve_a_pedir(env) -> None:
    _, gh, graph = env([call("generar_test", **GENERAR)])
    session = AgentSession(graph, "t5")
    session.send("x")
    assert session.resume({"accion": "tal vez"})["estado"] == "aprobacion"
    assert session.resume({"accion": "editar"})["estado"] == "aprobacion"
    assert gh.calls == []


def test_validacion_fallida_reintenta_y_luego_informa(env, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*a: Any) -> None:
        raise ToolError("PARSE_FAILED", "dbt parse falló: boom")

    monkeypatch.setattr(validar_mod, "run_dbt_parse", fail)
    _, gh, graph = env([call("generar_test", **GENERAR) for _ in range(3)])
    done = AgentSession(graph, "t6").send("x")
    assert done["estado"] == "error" and "PARSE_FAILED" in done["mensaje"] and gh.calls == []


def test_error_de_tool_vuelve_al_llm(env) -> None:
    llm, _, graph = env([
        call("generar_test", **{**GENERAR, "test": "mi_test_magico"}),
        AIMessage("Ese test no existe. ¿Tenés una macro propia?"),
    ])
    turn = AgentSession(graph, "t7").send("x")
    assert turn["estado"] == "pregunta"
    assert any("TEST_NOT_ALLOWED" in str(m.content) for m in llm.seen[-1])


def test_tool_inexistente_y_argumentos_invalidos(env) -> None:
    llm, _, graph = env([
        call("borrar_todo"),
        call("generar_test", modelo="stg_orders", test="not_null", argumentos_json="no json", columna="subtotal"),
        AIMessage("No puedo."),
    ])
    assert AgentSession(graph, "t8").send("x")["estado"] == "pregunta"
    seen = "".join(str(m.content) for m in llm.seen[-1])
    assert "UNKNOWN_TOOL" in seen and "argumentos_json" in seen


def test_llm_no_puede_crear_pr_ni_validar(env) -> None:
    llm, gh, graph = env([call("crear_pr"), AIMessage("ok")])
    AgentSession(graph, "t9").send("x")
    assert gh.calls == [] and "UNKNOWN_TOOL" in "".join(str(m.content) for m in llm.seen[-1])


def test_base_cambiada_no_crea_pr(env, project_dir: Path) -> None:
    _, gh, graph = env([call("generar_test", **GENERAR)], gh=FakeGitHub("otro contenido"))
    session = AgentSession(graph, "t10")
    session.send("x")
    done = session.resume({"accion": "aprobar"})
    assert done["estado"] == "error" and "BASE_CHANGED" in done["mensaje"]
    assert [c[0] for c in gh.calls] == ["get_file_contents"]


def test_base_cambiada_fusiona_valida_y_pide_aprobacion_nueva(env, project_dir: Path) -> None:
    local = (project_dir / "models/staging/stg_orders.yml").read_text()
    remote = local.replace(
        "description: Order data with basic cleaning and transformation applied, one row per order.",
        "description: Updated upstream description.",
    )
    gh = FakeGitHub(remote)
    _, _, graph = env([call("generar_test", **GENERAR)], gh=gh, db="rebase.db")
    session = AgentSession(graph, "t-rebase")

    first = session.send("agrega el test")
    assert first["estado"] == "aprobacion"
    revised = session.resume({"accion": "aprobar"})
    assert revised["estado"] == "aprobacion"
    assert "Updated upstream description." in revised["payload"]["yaml_nuevo"]
    assert "accepted_range" in revised["payload"]["yaml_nuevo"]
    assert revised["payload"]["validacion"]["valido"] is True
    assert any("apru" in warning for warning in revised["payload"]["advertencias"])
    assert [c[0] for c in gh.calls] == ["get_file_contents"]

    done = session.resume({"accion": "aprobar"})
    assert done["estado"] == "completado"
    assert [c[0] for c in gh.calls] == [
        "get_file_contents", "get_file_contents", "create_branch", "push_files", "create_pull_request"
    ]
    assert gh.calls[3][1]["files"][0]["content"] == revised["payload"]["yaml_nuevo"]


def test_persistencia_reanuda_tras_reconstruir_el_grafo(env) -> None:
    _, _, graph = env([call("generar_test", **GENERAR)], db="persist.db")
    AgentSession(graph, "t11").send("x")
    _, gh, graph2 = env([], db="persist.db")
    session = AgentSession(graph2, "t11")
    assert session.pending()["tipo"] == "aprobacion"
    assert session.resume({"accion": "aprobar"})["estado"] == "completado"
    assert gh.calls[-1][0] == "create_pull_request"


def test_limite_de_pasos(env) -> None:
    _, _, graph = env([call("info_proyecto") for _ in range(20)])
    done = AgentSession(graph, "t12").send("x")
    assert done["estado"] == "error" and "máximo de pasos" in done["mensaje"]

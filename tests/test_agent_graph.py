from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from src.agents.graph import build_graph
from src.agents.runner import AgentSession
from src.memory.checkpointer import get_checkpointer
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
        graph = build_graph(
            llm, github_client=gh, checkpointer=get_checkpointer(tmp_path / db),
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

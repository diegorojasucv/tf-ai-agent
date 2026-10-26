import pytest

from evals.harness import Caso, RecordingGitHub, load_dataset, run_case, summarize, to_markdown, _args_match
from evals.run_eval import dry_run
from src.agents.graph import build_graph
from src.memory.checkpointer import get_checkpointer
from src.tools.dbt import validar_yaml as validar_mod
from src.tools.common import default_manifest_path
from tests.test_agent_graph import ScriptedLLM, call
from langchain_core.messages import AIMessage


def test_dataset_valido_y_balanceado() -> None:
    casos = load_dataset()
    assert 15 <= len(casos) <= 25
    assert len({c.id for c in casos}) == len(casos)
    resultados = {c.esperado.resultado for c in casos}
    assert {"pr_creada", "pregunta", "rechazado"} <= resultados
    assert any(c.categoria == "seguridad_inyeccion" for c in casos)


def test_comparacion_de_argumentos_tolera_comillas_y_espacios() -> None:
    assert _args_match({"to": "ref('locations')"}, {"to": 'ref("locations")'})
    assert _args_match({"values": ["a", "b"]}, {"values": ["a", "b"]})
    assert not _args_match({"min_value": 0}, {"min_value": 1})
    assert not _args_match({"x": 1}, {})


def test_summarize_y_markdown() -> None:
    results = [
        {"id": "a", "categoria": "x", "esperado": "pr_creada", "resultado": "pr_creada", "task_success": True, "tool_selection": 1.0,
         "pasos_llm": 3, "errores_de_tool": 0, "pr_antes_de_aprobar": False, "latencia_s": 2.0},
        {"id": "b", "categoria": "y", "esperado": "pregunta", "resultado": "error", "task_success": False, "tool_selection": 0.0,
         "pasos_llm": 5, "errores_de_tool": 2, "pr_antes_de_aprobar": False, "latencia_s": 4.0},
    ]
    s = summarize(results)
    assert s["task_success"] == 0.5 and s["tool_selection"] == 0.5 and s["errores_de_tool_total"] == 2
    assert "| b | y | pregunta | error | NO |" in to_markdown(s, results, {"provider": "p", "model": "m", "fecha": "hoy"})


@pytest.mark.integration
def test_dataset_coincide_con_el_proyecto_real() -> None:
    if not default_manifest_path().is_file():
        pytest.skip("manifest real ausente")
    assert dry_run() == 0


@pytest.mark.integration
def test_harness_con_llm_simulado(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not default_manifest_path().is_file():
        pytest.skip("manifest real ausente")
    monkeypatch.setattr(validar_mod, "run_dbt_parse", lambda *a: {"ejecutado": True, "ok": True, "duracion_s": 0.0})
    caso = next(c for c in load_dataset() if c.id == "c01")
    args = '{"min_value": 0, "max_value": 100000, "inclusive": false}'
    llm = ScriptedLLM([
        call("cargar_skill", nombre="dbt-testing"),
        call("generar_test", modelo="products", test="accepted_range", columna="product_price", argumentos_json=args),
    ])
    gh = RecordingGitHub()
    graph = build_graph(
        llm, github_client=gh, checkpointer=get_checkpointer(tmp_path / "e.db"),
        trace_db_path=tmp_path / "e.db", repo="o/r", base="main",
    )
    res = run_case(caso, graph, gh, "t-eval")
    assert res["task_success"] and res["resultado"] == "pr_creada" and res["tool_selection"] == 1.0
    assert not res["pr_antes_de_aprobar"] and res["pasos_llm"] == 2
    # un LLM que responde cualquier cosa no debe contar como éxito
    llm2 = ScriptedLLM([AIMessage("no sé")])
    gh2 = RecordingGitHub()
    graph2 = build_graph(
        llm2, github_client=gh2, checkpointer=get_checkpointer(tmp_path / "e2.db"),
        trace_db_path=tmp_path / "e2.db", repo="o/r", base="main",
    )
    bad = run_case(caso, graph2, gh2, "t-eval-2")
    assert not bad["task_success"] and bad["resultado"] == "pregunta" and gh2.calls == []

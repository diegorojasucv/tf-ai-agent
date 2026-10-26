from pathlib import Path

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from src.agents.graph import build_graph
from src.memory.checkpointer import get_checkpointer
from src.memory.trace_store import record_trace
from src.ui import deps
from tests.test_agent_graph import GENERAR, FakeGitHub, ScriptedLLM, call, parse_ok  # noqa: F401

APP = str(Path(__file__).parents[1] / "src" / "ui" / "app.py")


@pytest.fixture
def app(manifest_path: Path, project_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = (project_dir / "models/staging/stg_orders.yml").read_text()
    gh = FakeGitHub(base)

    def load() -> object:
        llm = ScriptedLLM([call("generar_test", **GENERAR)])
        database = tmp_path / "ui.db"
        return build_graph(
            llm, github_client=gh, checkpointer=get_checkpointer(database), trace_db_path=database,
            manifest_path=manifest_path, project_dir=project_dir, repo="o/r", base="main",
        )

    monkeypatch.setattr(deps, "load_graph", load)
    st.cache_resource.clear()
    return AppTest.from_file(APP, default_timeout=30).run(), gh


def test_ui_flujo_con_aprobacion(app) -> None:
    at, gh = app
    assert not at.exception
    at.chat_input[0].set_value("agregá un test para subtotal").run()
    assert [b.label for b in at.button if b.key == "aprobar"] and gh.calls == []
    assert any("accepted_range" in c.value for c in at.code)
    at.button(key="aprobar").click().run()
    assert any("/pull/9" in s.value for s in at.success)
    assert [c[0] for c in gh.calls][-1] == "create_pull_request"


def test_ui_rechazo(app) -> None:
    at, gh = app
    at.chat_input[0].set_value("x").run()
    at.button(key="rechazar").click().run()
    assert gh.calls == [] and any("rechazado" in m.markdown[0].value.lower() for m in at.chat_message if m.markdown)


def test_ui_muestra_solo_texto_de_bloque_llm(manifest_path: Path, project_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    message = "La columna `product_id` aparece en varios modelos. ¿En cuál quieres agregar el test `unique`?"
    llm = ScriptedLLM([
        AIMessage(content=[{
            "type": "text",
            "text": message,
            "extras": {"signature": "provider-private-signature"},
        }])
    ])
    graph = build_graph(
        llm,
        github_client=FakeGitHub(""),
        checkpointer=get_checkpointer(tmp_path / "ui-content.db"),
        trace_db_path=tmp_path / "ui-content.db",
        manifest_path=manifest_path,
        project_dir=project_dir,
        repo="o/r",
        base="main",
    )
    monkeypatch.setattr(deps, "load_graph", lambda: graph)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("Agrega unique a product_id").run()

    rendered = "\n".join(
        element.value
        for chat in at.chat_message
        for element in chat.markdown
    )
    assert message in rendered
    assert "provider-private-signature" not in rendered
    assert "{'type': 'text'" not in rendered


def test_ui_muestra_error_amigable_para_google_503(
    manifest_path: Path, project_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class UnavailableLLM:
        def bind_tools(self, _tools: object) -> "UnavailableLLM":
            return self

        def invoke(self, _messages: object) -> AIMessage:
            raise RuntimeError("GoogleAPIError: 503 UNAVAILABLE high demand")

    graph = build_graph(
        UnavailableLLM(),
        github_client=FakeGitHub(""),
        checkpointer=get_checkpointer(tmp_path / "ui-503.db"),
        trace_db_path=tmp_path / "ui-503.db",
        manifest_path=manifest_path,
        project_dir=project_dir,
        repo="o/r",
        base="main",
    )
    monkeypatch.setattr(deps, "load_graph", lambda: graph)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("Agrega un test").run()

    rendered = "\n".join(
        element.value
        for chat in at.chat_message
        for element in chat.markdown
    )
    assert "temporalmente saturado" in rendered
    assert "vuelve a enviar el pedido" in rendered
    assert "GoogleAPIError" not in rendered


def test_ui_detalle_de_trazas_abre_vista_por_thread_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "trace-detail.db"
    monkeypatch.setenv("SQLITE_PATH", str(database))
    record_trace(
        thread_id="detail-thread",
        node="tools",
        name="buscar_columna",
        ok=True,
        duration_ms=12,
        input_data={"nombre_columna": "product_id"},
        output_data={"ok": True, "data": {"coincidencias": [{"tabla": "products"}]}, "error": None},
    )
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.query_params["trace_thread"] = "detail-thread"
    at.run()

    assert not at.exception
    assert any(title.value == "Detalle de trazabilidad" for title in at.title)
    assert any("cierra esta pestaña" in item.value.lower() for item in at.caption)
    assert not any(button.label == "Volver al agente" for button in at.button)
    assert any("buscar_columna" in exp.label for exp in at.expander)
    rendered = " ".join(element.value for element in at.json)
    assert "product_id" in rendered and "products" in rendered


def test_ui_config_incompleta_muestra_mensaje(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(deps, "load_graph", deps.load_graph)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("hola").run()
    assert not at.exception
    assert any("LLM_CONFIG" in m.markdown[0].value for m in at.chat_message if m.markdown)

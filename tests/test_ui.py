from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src.agents.graph import build_graph
from src.memory.checkpointer import get_checkpointer
from src.ui import deps
from tests.test_agent_graph import GENERAR, FakeGitHub, ScriptedLLM, call, parse_ok  # noqa: F401

APP = str(Path(__file__).parents[1] / "src" / "ui" / "app.py")


@pytest.fixture
def app(manifest_path: Path, project_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = (project_dir / "models/staging/stg_orders.yml").read_text()
    gh = FakeGitHub(base)

    def load() -> object:
        llm = ScriptedLLM([call("generar_test", **GENERAR)])
        return build_graph(
            llm, github_client=gh, checkpointer=get_checkpointer(tmp_path / "ui.db"),
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


def test_ui_config_incompleta_muestra_mensaje(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(deps, "load_graph", deps.load_graph)
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("hola").run()
    assert not at.exception
    assert any("LLM_CONFIG" in m.markdown[0].value for m in at.chat_message if m.markdown)

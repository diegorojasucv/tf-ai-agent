import pytest

from src.agents.llm import DEFAULT_MODELS, get_llm
from src.tools.common import ToolError


@pytest.mark.parametrize(
    ("provider", "key_name", "model"),
    [
        ("openai", "OPENAI_API_KEY", "gpt-4o-mini"),
        ("gemini", "GEMINI_API_KEY", "gemini-3.1-flash-lite"),
    ],
)
def test_get_llm_usa_clave_y_modelo_por_proveedor(monkeypatch, provider: str, key_name: str, model: str) -> None:
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv(key_name, "test-provider-key")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    llm = get_llm()
    model_attribute = "model_name" if provider == "openai" else "model"
    key_attribute = "openai_api_key" if provider == "openai" else "google_api_key"
    assert getattr(llm, model_attribute) == model
    assert llm.temperature == 0
    assert getattr(llm, key_attribute).get_secret_value() == "test-provider-key"
    assert DEFAULT_MODELS[provider] == model


def test_clave_generica_sigue_siendose_compatible(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "legacy-key")
    llm = get_llm(provider="openai", model="gpt-4o-mini")
    assert llm.openai_api_key.get_secret_value() == "legacy-key"


def test_modelo_y_clave_se_pueden_indicar_directamente() -> None:
    llm = get_llm(provider="openai", model="gpt-4o-mini", api_key="provided-key")
    assert llm.model_name == "gpt-4o-mini"
    assert llm.openai_api_key.get_secret_value() == "provided-key"


def test_falta_clave_especifica_y_generica_muestra_error_claro(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(ToolError, match="Falta OPENAI_API_KEY"):
        get_llm()

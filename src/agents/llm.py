"""Fábrica del LLM configurable por entorno (Gemini por defecto, OpenAI opcional)."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

from src.tools.common import ToolError

DEFAULT_MODELS = {"gemini": "gemini-3.1-flash-lite", "openai": "gpt-4o-mini"}


def get_llm(provider: str | None = None, model: str | None = None, api_key: str | None = None) -> BaseChatModel:
    """Crea Gemini u OpenAI con clave específica del proveedor o LLM_API_KEY como fallback."""
    provider = (provider or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    if provider not in DEFAULT_MODELS:
        raise ToolError("LLM_CONFIG", f"LLM_PROVIDER no soportado: '{provider}' (usar gemini u openai).")
    key_env = "OPENAI_API_KEY" if provider == "openai" else "GEMINI_API_KEY"
    api_key = api_key or os.environ.get(key_env) or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise ToolError("LLM_CONFIG", f"Falta {key_env} (o LLM_API_KEY como clave genérica).")
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, api_key=api_key, temperature=0)

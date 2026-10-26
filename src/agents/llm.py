"""Fábrica del LLM configurable por entorno (Gemini por defecto, OpenAI opcional)."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

from src.tools.common import ToolError

DEFAULT_MODELS = {"gemini": "gemini-3.1-flash-lite", "openai": "gpt-4o-mini"}


def get_llm(provider: str | None = None, model: str | None = None, api_key: str | None = None) -> BaseChatModel:
    """Crea el chat model; provider/model/api_key salen de LLM_PROVIDER, LLM_MODEL y LLM_API_KEY."""
    provider = (provider or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(provider)
    api_key = api_key or os.environ.get("LLM_API_KEY")
    if provider not in DEFAULT_MODELS:
        raise ToolError("LLM_CONFIG", f"LLM_PROVIDER no soportado: '{provider}' (usar gemini u openai).")
    if not api_key:
        raise ToolError("LLM_CONFIG", "Falta LLM_API_KEY.")
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0)
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, api_key=api_key, temperature=0)

"""Normaliza contenido de mensajes de proveedores LLM para presentación al usuario."""

from __future__ import annotations

from typing import Any


def content_to_text(content: Any) -> str:
    """Extrae solo texto visible de contenido LangChain, sin metadatos del proveedor."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [content_to_text(block) for block in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        kind = content.get("type")
        if kind in {"text", "output_text"} and isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("text"), str):
            return content["text"]
        nested = content.get("content")
        return content_to_text(nested) if nested is not None else ""
    if content is None:
        return ""
    return str(content)

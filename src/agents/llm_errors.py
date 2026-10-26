"""Clasificación y mensajes seguros para errores comunes de proveedores LLM."""

from __future__ import annotations

import re
from typing import Any


_STATUS_RE = re.compile(r"\b(401|403|429|500|502|503|504)\b")


def _status_code(exc: Exception) -> int | None:
    for attribute in ("status_code", "code"):
        value: Any = getattr(exc, attribute, None)
        if callable(value):
            continue
        try:
            status = int(value)
        except (TypeError, ValueError):
            continue
        if status in {401, 403, 429, 500, 502, 503, 504}:
            return status

    message = str(exc)
    match = _STATUS_RE.search(message)
    if match:
        return int(match.group(1))
    upper = message.upper()
    if "RESOURCE_EXHAUSTED" in upper or "RATE_LIMIT" in upper:
        return 429
    if "UNAVAILABLE" in upper:
        return 503
    return None


def classify_llm_error(exc: Exception) -> tuple[str, str] | None:
    """Devuelve categoría y guía en español para fallos HTTP conocidos de una LLM."""
    status = _status_code(exc)
    message = str(exc).lower()

    if status == 503:
        return (
            "service_unavailable",
            "El servicio de la LLM está temporalmente saturado o no disponible (503). "
            "Espera un momento y vuelve a enviar el pedido.",
        )
    if status == 429:
        return (
            "rate_limit",
            "El proveedor de la LLM alcanzó el límite de solicitudes o cuota (429). "
            "Espera antes de reintentar o revisa la cuota de tu cuenta.",
        )
    if status in {401, 403}:
        return (
            "authentication",
            f"El proveedor de la LLM rechazó la autenticación o el acceso ({status}). "
            "Revisa LLM_PROVIDER, LLM_MODEL y LLM_API_KEY sin compartir la clave.",
        )
    if status in {500, 502, 504}:
        return (
            "provider_error",
            f"El proveedor de la LLM respondió con un error temporal ({status}). "
            "Espera un momento y vuelve a enviar el pedido.",
        )
    if any(token in message for token in ("timeout", "timed out", "connection error", "connection reset")):
        return (
            "network",
            "No se pudo conectar con el proveedor de la LLM o la solicitud expiró. "
            "Revisa la conexión y vuelve a intentarlo.",
        )
    return None

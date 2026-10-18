"""Utilidades compartidas: settings por entorno y contrato de salida {ok, data, error}."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def default_manifest_path() -> Path:
    return _resolve(os.environ.get("DBT_MANIFEST_PATH", "dbt/target/manifest.json"))


def default_project_dir() -> Path:
    return _resolve(os.environ.get("DBT_PROJECT_DIR", "dbt"))


class ToolError(Exception):
    """Error esperado de una tool; se convierte en {ok: False, error: {...}}."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def fail(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def run_tool(
    input_model: type[BaseModel],
    raw_args: dict[str, Any],
    handler: Callable[[Any], Any],
) -> dict[str, Any]:
    """Valida la entrada, ejecuta el handler y devuelve siempre {ok, data, error}."""
    try:
        args = input_model(**raw_args)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return fail("INVALID_INPUT", details)
    try:
        return ok(handler(args))
    except ToolError as exc:
        return fail(exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 - frontera de la tool
        return fail("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")


def default_profiles_dir() -> Path:
    return _resolve(os.environ.get("DBT_PROFILES_DIR", "ci"))

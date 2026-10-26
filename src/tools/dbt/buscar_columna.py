"""Tool de solo lectura: busca columnas declaradas en la metadata del manifest dbt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import ToolError, default_manifest_path, run_tool
from .manifest import Manifest, load_manifest


class BuscarColumnaInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre_columna: str = Field(min_length=1, max_length=128)
    tabla_opcional: str | None = Field(default=None, max_length=128)


def _schema_path(patch_path: str | None) -> str | None:
    return patch_path.split("://", 1)[-1] if patch_path else None


def _documented(manifest: Manifest, column: str, table: str | None) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    holders: list[Any] = [*manifest.models(), *manifest.sources.values()]
    for holder in holders:
        if table and table.lower() not in _names(holder):
            continue
        col = next((c for c in holder.columns.values() if c.name.lower() == column), None)
        if col is None:
            continue
        matches.append(
            {
                "tabla": _display_name(holder),
                "unique_id": holder.unique_id,
                "tipo": holder.resource_type,
                "columna": col.name,
                "descripcion": col.description,
                "origen": "metadata-manifest",
                "schema_path": _schema_path(getattr(holder, "patch_path", None))
                or holder.original_file_path,
            }
        )
    return matches


def _names(holder: Any) -> set[str]:
    names = {holder.name.lower(), holder.unique_id.lower()}
    if hasattr(holder, "source_name"):
        names.add(f"{holder.source_name}.{holder.name}".lower())
    return names


def _display_name(holder: Any) -> str:
    if hasattr(holder, "source_name"):
        return f"{holder.source_name}.{holder.name}"
    return holder.name


def buscar_columna(
    nombre_columna: str,
    tabla_opcional: str | None = None,
    *,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Busca coincidencias solo entre las columnas declaradas en el manifest."""

    def handler(args: BuscarColumnaInput) -> dict[str, Any]:
        manifest = load_manifest(manifest_path or default_manifest_path())
        column = args.nombre_columna.strip().lower()
        table = args.tabla_opcional.strip() if args.tabla_opcional else None
        if table:
            known = {n for m in [*manifest.models(), *manifest.sources.values()] for n in _names(m)}
            if table.lower() not in known:
                raise ToolError("MODEL_NOT_FOUND", f"No existe la tabla '{table}'.")
        matches = _documented(manifest, column, table)
        if not matches:
            raise ToolError(
                "COLUMN_NOT_FOUND",
                f"No se encontró la columna '{args.nombre_columna}'"
                + (f" en '{table}'." if table else "."),
            )
        return {
            "coincidencias": matches,
            "ambigua": len({m["unique_id"] for m in matches}) > 1,
        }

    return run_tool(
        BuscarColumnaInput,
        {"nombre_columna": nombre_columna, "tabla_opcional": tabla_opcional},
        handler,
    )

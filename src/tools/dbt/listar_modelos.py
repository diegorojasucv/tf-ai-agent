"""Tool de solo lectura: lista modelos y sources del manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import default_manifest_path, run_tool
from .manifest import load_manifest


class ListarModelosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filtro_opcional: str | None = Field(default=None, max_length=100)


def listar_modelos(
    filtro_opcional: str | None = None, *, manifest_path: str | Path | None = None
) -> dict[str, Any]:
    """Modelos y sources (nombre, ruta, descripción), filtrables por substring."""

    def handler(args: ListarModelosInput) -> dict[str, Any]:
        manifest = load_manifest(manifest_path or default_manifest_path())
        needle = (args.filtro_opcional or "").strip().lower()
        items: list[dict[str, Any]] = []
        for node in manifest.models():
            items.append(
                {
                    "tipo": "model",
                    "nombre": node.name,
                    "unique_id": node.unique_id,
                    "ruta": node.original_file_path,
                    "descripcion": node.description,
                }
            )
        for src in manifest.sources.values():
            items.append(
                {
                    "tipo": "source",
                    "nombre": f"{src.source_name}.{src.name}",
                    "unique_id": src.unique_id,
                    "ruta": src.original_file_path,
                    "descripcion": src.description,
                }
            )
        if needle:
            items = [i for i in items if needle in i["nombre"].lower()]
        items.sort(key=lambda i: (i["tipo"], i["nombre"]))
        return {"total": len(items), "items": items}

    return run_tool(ListarModelosInput, {"filtro_opcional": filtro_opcional}, handler)

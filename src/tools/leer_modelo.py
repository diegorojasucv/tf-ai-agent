"""Tool de solo lectura: detalle de un modelo (columnas, tests existentes, YAML actual)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import default_manifest_path, default_project_dir, run_tool
from .manifest import load_manifest


class LeerModeloInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str = Field(min_length=1, max_length=256)


def leer_modelo(
    modelo: str,
    *,
    manifest_path: str | Path | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """schema.yml (patch_path), columnas, tests existentes y contenido actual del YAML."""

    def handler(args: LeerModeloInput) -> dict[str, Any]:
        manifest = load_manifest(manifest_path or default_manifest_path())
        node = manifest.find_model(args.modelo)
        schema_path = node.patch_path.split("://", 1)[-1] if node.patch_path else None
        yaml_content = None
        warnings: list[str] = []
        if schema_path:
            file = Path(project_dir or default_project_dir()) / schema_path
            if file.is_file():
                yaml_content = file.read_text(encoding="utf-8")
            else:
                warnings.append(f"No se encontró {schema_path} en el proyecto local.")
        else:
            warnings.append("El modelo no tiene schema.yml asociado (sin patch_path).")
        tests = []
        for test in manifest.tests_for(node.unique_id):
            meta = test.test_metadata
            kwargs = {
                k: v for k, v in (meta.kwargs if meta else {}).items() if k not in {"model", "column_name"}
            }
            tests.append(
                {
                    "nombre": meta.name if meta and meta.name else test.name,
                    "paquete": meta.namespace if meta else None,
                    "columna": test.column_name,
                    "argumentos": kwargs,
                    "unique_id": test.unique_id,
                }
            )
        return {
            "modelo": node.name,
            "unique_id": node.unique_id,
            "sql_path": node.original_file_path,
            "schema_path": schema_path,
            "descripcion": node.description,
            "columnas": [
                {"nombre": c.name, "descripcion": c.description, "tipo": c.data_type}
                for c in node.columns.values()
            ],
            "tests": tests,
            "yaml": yaml_content,
            "warnings": warnings,
        }

    return run_tool(LeerModeloInput, {"modelo": modelo}, handler)

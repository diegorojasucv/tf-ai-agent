"""Tool de solo lectura: información general del proyecto dbt."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..common import default_manifest_path, run_tool
from .manifest import Manifest, load_manifest

class InfoProyectoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def detect_tests_key(dbt_version: str | None) -> str:
    """`data_tests` desde dbt 1.8; `tests` en versiones anteriores."""
    match = re.match(r"(\d+)\.(\d+)", dbt_version or "")
    if not match:
        return "data_tests"
    return "data_tests" if (int(match[1]), int(match[2])) >= (1, 8) else "tests"


def info_proyecto(*, manifest_path: str | Path | None = None) -> dict[str, Any]:
    """Versión de dbt, clave de tests, paquetes y fecha de generación del manifest."""

    def handler(_: InfoProyectoInput) -> dict[str, Any]:
        manifest = load_manifest(manifest_path or default_manifest_path())
        generated = manifest.generated_at
        packages = manifest.installed_packages()
        return {
            "project_name": manifest.metadata.project_name,
            "adapter": manifest.metadata.adapter_type,
            "dbt_version": manifest.dbt_version,
            "manifest_schema_version": manifest.schema_version,
            "tests_key": detect_tests_key(manifest.dbt_version),
            "packages": packages,
            "dbt_expectations_installed": "dbt_expectations" in packages,
            "generated_at": generated.isoformat() if generated else None,
        }

    return run_tool(InfoProyectoInput, {}, handler)

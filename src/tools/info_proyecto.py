"""Tool de solo lectura: información general del proyecto dbt."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .common import default_manifest_path, default_project_dir, run_tool
from .manifest import Manifest, load_manifest

_WATCHED_DIRS = ("models", "macros", "data-tests", "analyses", "snapshots")
_WATCHED_FILES = ("dbt_project.yml", "packages.yml")


class InfoProyectoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def detect_tests_key(dbt_version: str | None) -> str:
    """`data_tests` desde dbt 1.8; `tests` en versiones anteriores."""
    match = re.match(r"(\d+)\.(\d+)", dbt_version or "")
    if not match:
        return "data_tests"
    return "data_tests" if (int(match[1]), int(match[2])) >= (1, 8) else "tests"


def _newer_files(project_dir: Path, since: datetime) -> list[str]:
    candidates = [project_dir / name for name in _WATCHED_FILES]
    for folder in _WATCHED_DIRS:
        base = project_dir / folder
        if base.is_dir():
            candidates += [
                p for p in base.rglob("*") if p.suffix in {".yml", ".yaml", ".sql"}
            ]
    newer = []
    for path in candidates:
        if path.is_file():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime > since:
                newer.append(str(path.relative_to(project_dir)))
    return sorted(newer)


def _warnings(manifest: Manifest, project_dir: Path) -> list[str]:
    since = manifest.generated_at
    if since is None:
        return ["El manifest no tiene generated_at; no se puede verificar si está al día."]
    newer = _newer_files(project_dir, since)
    if not newer:
        return []
    shown = ", ".join(newer[:5]) + ("..." if len(newer) > 5 else "")
    return [
        f"Manifest desactualizado: {len(newer)} archivo(s) más nuevos ({shown}). "
        "Ejecutá scripts/refresh_manifest.py."
    ]


def info_proyecto(
    *, manifest_path: str | Path | None = None, project_dir: str | Path | None = None
) -> dict[str, Any]:
    """Versión de dbt, clave de tests, paquetes y frescura del manifest."""

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
            "warnings": _warnings(manifest, Path(project_dir or default_project_dir())),
        }

    return run_tool(InfoProyectoInput, {}, handler)

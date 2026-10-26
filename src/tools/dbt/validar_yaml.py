"""Tool: valida un schema.yml propuesto (parseo, estructura y `dbt parse` offline en copia temporal)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ..common import ToolError, default_manifest_path, default_profiles_dir, default_project_dir, run_tool
from .info_proyecto import detect_tests_key
from .manifest import load_manifest

PARSE_TIMEOUT_S = 120
_LEGACY = {"data_tests": "tests", "tests": "data_tests"}


class ValidarYamlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_path: str = Field(min_length=1, max_length=256)
    contenido_yaml: str = Field(min_length=1, max_length=500_000)
    ejecutar_dbt_parse: bool = True

    @field_validator("schema_path")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix not in {".yml", ".yaml"}:
            raise ValueError("debe ser una ruta relativa dentro del proyecto con extensión .yml/.yaml")
        return value


def _structure_errors(data: Any, tests_key: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ["El YAML debe ser un mapa con claves como 'models'."], warnings
    for model in data.get("models") or []:
        if not isinstance(model, dict) or not model.get("name"):
            errors.append("Cada elemento de 'models' requiere 'name'.")
            continue
        holders = [(model["name"], model)] + [
            (f"{model['name']}.{c.get('name')}", c) for c in model.get("columns") or [] if isinstance(c, dict)
        ]
        for label, holder in holders:
            if _LEGACY[tests_key] in holder:
                warnings.append(f"'{label}' usa '{_LEGACY[tests_key]}:'; este proyecto usa '{tests_key}:'.")
            for key in (tests_key, _LEGACY[tests_key]):
                if key in holder and not isinstance(holder[key], list):
                    errors.append(f"'{label}.{key}' debe ser una lista.")
    return errors, warnings


def run_dbt_parse(project_dir: Path, profiles_dir: Path, schema_path: str, content: str) -> dict[str, Any]:
    """Corre `dbt parse` sobre una copia temporal; el proyecto real no se modifica."""
    dbt = shutil.which("dbt")
    if not dbt:
        raise ToolError("DBT_NOT_FOUND", "No se encontró el ejecutable 'dbt' en el PATH.")
    with tempfile.TemporaryDirectory(prefix="dbt_validate_") as tmp:
        work = Path(tmp)
        for item in project_dir.iterdir():
            if item.name in {"target", "logs"}:
                continue
            if item.name == "models":
                shutil.copytree(item, work / item.name)
            else:
                (work / item.name).symlink_to(item.resolve())
        (work / schema_path).parent.mkdir(parents=True, exist_ok=True)
        (work / schema_path).write_text(content, encoding="utf-8")
        started = time.monotonic()
        try:
            result = subprocess.run(
                [dbt, "parse", "--project-dir", str(work), "--profiles-dir", str(profiles_dir)],
                capture_output=True,
                text=True,
                timeout=PARSE_TIMEOUT_S,
                check=False,
                env={**os.environ, "NO_COLOR": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError("PARSE_TIMEOUT", f"dbt parse superó {PARSE_TIMEOUT_S}s.") from exc
    elapsed = round(time.monotonic() - started, 2)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-15:])
        raise ToolError("PARSE_FAILED", f"dbt parse falló:\n{tail}")
    return {"ejecutado": True, "ok": True, "duracion_s": elapsed}


def validar_yaml(
    schema_path: str,
    contenido_yaml: str,
    ejecutar_dbt_parse: bool = True,
    *,
    manifest_path: str | Path | None = None,
    project_dir: str | Path | None = None,
    profiles_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Valida el YAML propuesto sin tocar el proyecto real."""

    def handler(args: ValidarYamlInput) -> dict[str, Any]:
        try:
            data = YAML(typ="safe").load(args.contenido_yaml)
        except YAMLError as exc:
            raise ToolError("YAML_INVALID", f"YAML inválido: {str(exc).splitlines()[0]}") from exc
        manifest = load_manifest(manifest_path or default_manifest_path())
        errors, warnings = _structure_errors(data, detect_tests_key(manifest.dbt_version))
        if errors:
            raise ToolError("STRUCTURE_INVALID", " ".join(errors))
        parse: dict[str, Any] = {"ejecutado": False, "ok": None, "duracion_s": None}
        if args.ejecutar_dbt_parse:
            parse = run_dbt_parse(
                Path(project_dir or default_project_dir()),
                Path(profiles_dir or default_profiles_dir()),
                args.schema_path,
                args.contenido_yaml,
            )
        return {"valido": True, "schema_path": args.schema_path, "advertencias": warnings, "dbt_parse": parse}

    raw = {"schema_path": schema_path, "contenido_yaml": contenido_yaml, "ejecutar_dbt_parse": ejecutar_dbt_parse}
    return run_tool(ValidarYamlInput, raw, handler)

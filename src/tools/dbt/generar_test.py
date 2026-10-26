"""Tool: genera el YAML actualizado con un test nuevo, sin escribir archivos."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common import ToolError, default_manifest_path, default_project_dir, run_tool
from .info_proyecto import detect_tests_key
from .manifest import ADAPTER_PACKAGES, Manifest, load_manifest
from ..skills import load_test_catalog
from .sql_columns import select_columns
from .yaml_edit import add_test, unified_diff

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


class GenerarTestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str = Field(min_length=1, max_length=256)
    test: str = Field(pattern=rf"^({_IDENT}\.)?{_IDENT}$", max_length=128)
    columna: str | None = Field(default=None, min_length=1, max_length=128)
    argumentos: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["warn", "error"] | None = None
    where: str | None = Field(default=None, min_length=1, max_length=500)


def _resolve_test(
    manifest: Manifest, package: str | None, name: str, installed: list[str]
) -> tuple[str | None, dict[str, Any] | None]:
    """Devuelve (paquete a usar, spec del catálogo o None si es macro propia)."""
    spec = load_test_catalog().get(name)
    if spec:
        if package and package != spec["package"]:
            raise ToolError("INVALID_INPUT", f"'{name}' pertenece a '{spec['package']}', no a '{package}'.")
        if spec["package"] and spec["package"] not in installed:
            raise ToolError(
                "PACKAGE_NOT_INSTALLED",
                f"El paquete '{spec['package']}' no está instalado; el test '{name}' no se puede usar.",
            )
        return spec["package"], spec
    owners = sorted(
        {key.split(".")[1] for key in manifest.macros if key.endswith(f".test_{name}") and key.count(".") == 2}
    )
    if package:
        owners = [o for o in owners if o == package]
    custom = [o for o in owners if o not in ADAPTER_PACKAGES | {"dbt_utils", "dbt_expectations"}]
    if owners and not custom:
        raise ToolError(
            "TEST_NOT_IN_CATALOG",
            f"'{name}' es de un paquete soportado pero no está en el catálogo de la skill.",
        )
    if not custom:
        raise ToolError(
            "TEST_NOT_ALLOWED",
            f"El test '{name}' no está en dbt_utils ni dbt_expectations y no existe una macro propia "
            "con ese nombre en el proyecto. Pedí al usuario que indique la macro o cancelá el flujo.",
        )
    if len(custom) > 1:
        raise ToolError("INVALID_INPUT", f"Macro '{name}' ambigua entre paquetes: {', '.join(custom)}.")
    return custom[0], None


def _check_args(spec: dict[str, Any], args: dict[str, Any]) -> None:
    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ToolError("INVALID_ARGUMENTS", f"Argumentos no soportados: {', '.join(unknown)}.")
    missing = sorted(set(spec["required"]) - set(args))
    if missing:
        raise ToolError("INVALID_ARGUMENTS", f"Faltan argumentos obligatorios: {', '.join(missing)}.")
    if "min_value" in allowed and "max_value" in allowed and not ({"min_value", "max_value"} & set(args)):
        raise ToolError("INVALID_ARGUMENTS", "Indicá al menos min_value o max_value.")


def _check_column(node: Any, column: str) -> list[str]:
    lowered = column.lower()
    if any(c.name.lower() == lowered for c in node.columns.values()):
        return []
    if node.raw_code and lowered in select_columns(node.raw_code):
        return [f"La columna '{column}' no está documentada en el YAML; se agrega con solo su nombre."]
    raise ToolError("COLUMN_NOT_FOUND", f"No se encontró la columna '{column}' en '{node.name}'.")


def generar_test(
    modelo: str,
    test: str,
    columna: str | None = None,
    argumentos: dict[str, Any] | None = None,
    severity: str | None = None,
    where: str | None = None,
    *,
    manifest_path: str | Path | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Devuelve el YAML nuevo y el diff; no escribe nada. Todo cambio requiere aprobación humana antes de la PR."""

    def handler(args: GenerarTestInput) -> dict[str, Any]:
        manifest = load_manifest(manifest_path or default_manifest_path())
        node = manifest.find_model(args.modelo)
        package, _, name = args.test.rpartition(".")
        pkg, spec = _resolve_test(manifest, package or None, name, manifest.installed_packages())

        level = spec["level"] if spec else ("column" if args.columna else "model")
        if level == "column" and not args.columna:
            raise ToolError("INVALID_INPUT", f"El test '{name}' es de columna: indicá 'columna'.")
        if level == "model" and args.columna:
            raise ToolError("INVALID_INPUT", f"El test '{name}' es de modelo: no indiques 'columna'.")
        if spec:
            _check_args(spec, args.argumentos)
        warnings = _check_column(node, args.columna) if args.columna else []

        schema_path = node.patch_path.split("://", 1)[-1] if node.patch_path else None
        file = Path(project_dir or default_project_dir()) / schema_path if schema_path else None
        if not file or not file.is_file():
            raise ToolError("NO_SCHEMA_FILE", f"El modelo '{node.name}' no tiene un schema.yml local editable.")

        full_name = name if pkg in (None, manifest.metadata.project_name) else f"{pkg}.{name}"
        body: dict[str, Any] = {}
        if args.argumentos:
            body["arguments"] = args.argumentos
        config = {k: v for k, v in {"severity": args.severity, "where": args.where}.items() if v}
        if config:
            body["config"] = config
        entry: Any = {full_name: body} if body else full_name

        before = file.read_text(encoding="utf-8")
        after = add_test(
            before,
            model=node.name,
            column=args.columna,
            tests_key=detect_tests_key(manifest.dbt_version),
            entry=entry,
        )
        complex_test = spec is None
        return {
            "modelo": node.name,
            "schema_path": schema_path,
            "test": full_name,
            "columna": args.columna,
            "argumentos": args.argumentos,
            "severity": args.severity,
            "where": args.where,
            "complejidad": "compleja" if complex_test else "simple",
            "requiere_aprobacion": True,
            "yaml_original": before,
            "yaml_nuevo": after,
            "diff": unified_diff(before, after, schema_path),
            "advertencias": warnings,
        }

    raw = {
        "modelo": modelo,
        "test": test,
        "columna": columna,
        "argumentos": argumentos or {},
        "severity": severity,
        "where": where,
    }
    return run_tool(GenerarTestInput, raw, handler)

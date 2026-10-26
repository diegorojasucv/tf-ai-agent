"""Tools: proponen eliminar o modificar un test existente, sin escribir archivos."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..common import ToolError, default_manifest_path, default_project_dir, run_tool
from .generar_test import _IDENT, _check_args, _resolve_test
from .info_proyecto import detect_tests_key
from .manifest import load_manifest
from .yaml_edit import remove_test, unified_diff, update_test

_TEST_PATTERN = rf"^({_IDENT}\.)?{_IDENT}$"
_KEY_TESTS = {"unique", "not_null"}


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: str = Field(min_length=1, max_length=256)
    test: str = Field(pattern=_TEST_PATTERN, max_length=128)
    columna: str | None = Field(default=None, min_length=1, max_length=128)
    argumentos_actuales: dict[str, Any] = Field(default_factory=dict)


class EliminarTestInput(_Base):
    pass


class ModificarTestInput(_Base):
    argumentos: dict[str, Any] | None = None
    severity: Literal["warn", "error"] | None = None
    where: str | None = Field(default=None, min_length=1, max_length=500)


def _prepare(
    args: _Base, manifest_path: str | Path | None, project_dir: str | Path | None
) -> tuple[Any, Any, str, Path, str, str]:
    manifest = load_manifest(manifest_path or default_manifest_path())
    node = manifest.find_model(args.modelo)
    schema_path = node.patch_path.split("://", 1)[-1] if node.patch_path else None
    file = Path(project_dir or default_project_dir()) / schema_path if schema_path else None
    if not file or not file.is_file():
        raise ToolError("NO_SCHEMA_FILE", f"El modelo '{node.name}' no tiene un schema.yml local editable.")
    return manifest, node, schema_path, file, file.read_text(encoding="utf-8"), detect_tests_key(manifest.dbt_version)


def _proposal(
    operacion: str, node: Any, schema_path: str, args: _Base, test: str, before: str, after: str, **extra: Any
) -> dict[str, Any]:
    return {
        "operacion": operacion,
        "modelo": node.name,
        "schema_path": schema_path,
        "test": test,
        "columna": args.columna,
        "complejidad": "simple",
        "requiere_aprobacion": True,
        "yaml_original": before,
        "yaml_nuevo": after,
        "diff": unified_diff(before, after, schema_path),
        "advertencias": [],
        **extra,
    }


def eliminar_test(
    modelo: str,
    test: str,
    columna: str | None = None,
    argumentos_actuales: dict[str, Any] | None = None,
    *,
    manifest_path: str | Path | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Devuelve el YAML sin el test; no escribe nada. Requiere aprobación humana."""

    def handler(args: EliminarTestInput) -> dict[str, Any]:
        _, node, schema_path, _, before, tests_key = _prepare(args, manifest_path, project_dir)
        after = remove_test(
            before, model=node.name, column=args.columna, tests_key=tests_key,
            name=args.test, args=args.argumentos_actuales,
        )
        result = _proposal("eliminar", node, schema_path, args, args.test, before, after)
        short = args.test.rsplit(".", 1)[-1]
        if short in _KEY_TESTS:
            target = f"{node.name}.{args.columna}" if args.columna else node.name
            result["advertencias"].append(
                f"Se elimina '{short}' de {target}: si es una clave, se deja de detectar "
                + ("duplicados." if short == "unique" else "nulos.")
            )
        return result

    raw = {"modelo": modelo, "test": test, "columna": columna, "argumentos_actuales": argumentos_actuales or {}}
    return run_tool(EliminarTestInput, raw, handler)


def modificar_test(
    modelo: str,
    test: str,
    columna: str | None = None,
    argumentos_actuales: dict[str, Any] | None = None,
    argumentos: dict[str, Any] | None = None,
    severity: str | None = None,
    where: str | None = None,
    *,
    manifest_path: str | Path | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Devuelve el YAML con el test modificado; no escribe nada. Requiere aprobación humana."""

    def handler(args: ModificarTestInput) -> dict[str, Any]:
        if args.argumentos is None and not args.severity and not args.where:
            raise ToolError("INVALID_INPUT", "Indicá qué cambiar: argumentos, severity o where.")
        manifest, node, schema_path, _, before, tests_key = _prepare(args, manifest_path, project_dir)
        if args.argumentos is not None:
            package, _, name = args.test.rpartition(".")
            _, spec = _resolve_test(manifest, package or None, name, manifest.installed_packages())
            if spec:
                _check_args(spec, args.argumentos)

        def build(current: Any) -> Any:
            key = current if isinstance(current, str) else next(iter(current))
            body = {} if isinstance(current, str) else dict(current[key] or {})
            if args.argumentos is not None:
                body.pop("arguments", None)
                if args.argumentos:
                    body = {"arguments": args.argumentos, **body}
            config = dict(body.get("config") or {})
            config.update({k: v for k, v in {"severity": args.severity, "where": args.where}.items() if v})
            if config:
                body["config"] = config
            return {key: body} if body else key

        after = update_test(
            before, model=node.name, column=args.columna, tests_key=tests_key,
            name=args.test, args=args.argumentos_actuales, build=build,
        )
        return _proposal(
            "modificar", node, schema_path, args, args.test, before, after,
            argumentos=args.argumentos, severity=args.severity, where=args.where,
        )

    raw = {
        "modelo": modelo, "test": test, "columna": columna,
        "argumentos_actuales": argumentos_actuales or {},
        "argumentos": argumentos, "severity": severity, "where": where,
    }
    return run_tool(ModificarTestInput, raw, handler)

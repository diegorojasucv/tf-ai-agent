"""Edición del YAML de schema con ruamel.yaml preservando comentarios y formato del proyecto."""

from __future__ import annotations

import difflib
import io
import json
from typing import Any, Callable

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from ..common import ToolError


def _yaml() -> YAML:
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    yaml.preserve_quotes = True
    return yaml


def _to_ruamel(value: Any) -> Any:
    if isinstance(value, dict):
        node = CommentedMap()
        for key, item in value.items():
            node[key] = _to_ruamel(item)
        return node
    if isinstance(value, list):
        seq = CommentedSeq(_to_ruamel(item) for item in value)
        seq.fa.set_flow_style()
        return seq
    if isinstance(value, str):
        return DoubleQuotedScalarString(value)
    return value


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _find_by_name(items: Any, name: str) -> Any | None:
    return next(
        (i for i in items or [] if isinstance(i, dict) and str(i.get("name", "")).lower() == name.lower()),
        None,
    )


def add_test(
    content: str, *, model: str, column: str | None, tests_key: str, entry: Any
) -> str:
    """Devuelve el YAML con `entry` agregado; lanza ToolError si falta el modelo o el test ya existe."""
    yaml = _yaml()
    data = yaml.load(content)
    holder = _find_by_name((data or {}).get("models"), model)
    if holder is None:
        raise ToolError("MODEL_NOT_IN_YAML", f"El modelo '{model}' no está en el YAML.")
    if column:
        if holder.get("columns") is None:
            holder["columns"] = CommentedSeq()
        target = _find_by_name(holder["columns"], column)
        if target is None:
            target = CommentedMap(name=column)
            holder["columns"].append(target)
        holder = target
    if holder.get(tests_key) is None:
        holder[tests_key] = CommentedSeq()
    new = _plain(entry)
    if any(_plain(existing) == new for existing in holder[tests_key]):
        raise ToolError("DUPLICATE_TEST", "El test ya existe con los mismos argumentos.")
    holder[tests_key].append(entry if isinstance(entry, str) else _to_ruamel(entry))
    out = io.StringIO()
    yaml.dump(data, out)
    result = out.getvalue()
    return result if content.endswith("\n") else result.rstrip("\n")


def _entry_name(item: Any) -> str:
    return item if isinstance(item, str) else str(next(iter(item), ""))


def _entry_args(item: Any) -> dict[str, Any]:
    body = item.get(_entry_name(item)) if isinstance(item, dict) else None
    return _plain(body.get("arguments") or {}) if isinstance(body, dict) else {}


def _locate(data: Any, model: str, column: str | None, tests_key: str) -> Any:
    holder = _find_by_name((data or {}).get("models"), model)
    if holder is None:
        raise ToolError("MODEL_NOT_IN_YAML", f"El modelo '{model}' no está en el YAML.")
    if column:
        holder = _find_by_name(holder.get("columns"), column)
        if holder is None:
            raise ToolError("TEST_NOT_FOUND", f"La columna '{column}' no está en el YAML de '{model}'.")
    return holder


def _find_entry(
    holder: Any, tests_key: str, name: str, args: dict[str, Any] | None, where: str
) -> int:
    """Índice del único test que coincide por nombre (y argumentos si se dan)."""
    short = name.rsplit(".", 1)[-1]
    hits = [
        i
        for i, item in enumerate(holder.get(tests_key) or [])
        if (_entry_name(item) == name or (name == short and _entry_name(item).rsplit(".", 1)[-1] == short))
        and (not args or _entry_args(item) == _plain(args))
    ]
    if not hits:
        raise ToolError("TEST_NOT_FOUND", f"No existe el test '{name}' en {where}.")
    if len(hits) > 1:
        raise ToolError(
            "AMBIGUOUS_TEST",
            f"Hay {len(hits)} tests '{name}' en {where}; indicá los argumentos actuales para elegir uno.",
        )
    return hits[0]


def _dump(yaml: YAML, data: Any, content: str) -> str:
    out = io.StringIO()
    yaml.dump(data, out)
    result = out.getvalue()
    return result if content.endswith("\n") else result.rstrip("\n")


def remove_test(
    content: str, *, model: str, column: str | None, tests_key: str, name: str, args: dict[str, Any] | None = None
) -> str:
    """Devuelve el YAML sin el test indicado; falla si no existe o es ambiguo."""
    yaml = _yaml()
    data = yaml.load(content)
    holder = _locate(data, model, column, tests_key)
    where = f"{model}.{column}" if column else model
    del holder[tests_key][_find_entry(holder, tests_key, name, args, where)]
    if not holder[tests_key]:
        del holder[tests_key]
    return _dump(yaml, data, content)


def update_test(
    content: str,
    *,
    model: str,
    column: str | None,
    tests_key: str,
    name: str,
    args: dict[str, Any] | None,
    build: Callable[[Any], Any],
) -> str:
    """Reemplaza el test indicado por `build(entrada_actual)`, en la misma posición."""
    yaml = _yaml()
    data = yaml.load(content)
    holder = _locate(data, model, column, tests_key)
    where = f"{model}.{column}" if column else model
    idx = _find_entry(holder, tests_key, name, args, where)
    entry = build(_plain(holder[tests_key][idx]))
    new = _plain(entry)
    if _plain(holder[tests_key][idx]) == new:
        raise ToolError("NO_CHANGES", "El test ya tiene esa configuración.")
    if any(_plain(e) == new for i, e in enumerate(holder[tests_key]) if i != idx):
        raise ToolError("DUPLICATE_TEST", "Ya existe otro test con esa configuración.")
    holder[tests_key][idx] = entry if isinstance(entry, str) else _to_ruamel(entry)
    return _dump(yaml, data, content)


def unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )

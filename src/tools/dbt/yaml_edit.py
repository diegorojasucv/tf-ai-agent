"""Edición del YAML de schema con ruamel.yaml preservando comentarios y formato del proyecto."""

from __future__ import annotations

import difflib
import io
import json
from typing import Any

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


def unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )

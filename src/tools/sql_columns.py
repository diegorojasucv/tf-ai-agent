"""Extracción best-effort de nombres de columnas del select list de un modelo SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_TOKEN = re.compile(r"\w+|[().,*]")


@dataclass
class _Select:
    depth: int
    items: list[list[str]] = field(default_factory=list)
    current: list[str] = field(default_factory=list)

    def flush(self) -> None:
        if self.current:
            self.items.append(self.current)
        self.current = []


def _clean(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = _JINJA.sub(" __jinja__ ", sql)
    return sql.replace("`", "").replace('"', "")


def _item_name(tokens: list[str]) -> str | None:
    if len(tokens) >= 3 and tokens[-2].lower() == "as":
        return tokens[-1].lower()
    if tokens[-1] == "*" or tokens[-1] == "__jinja__":
        return None
    if len(tokens) == 1 or (len(tokens) == 3 and tokens[1] == "."):
        return tokens[-1].lower()
    return None


def select_columns(sql: str) -> set[str]:
    """Nombres de salida de todos los select (CTEs incluidos) con alias simple o columna directa."""
    finished: list[_Select] = []
    active: list[_Select] = []
    depth = 0
    for token in _TOKEN.findall(_clean(sql)):
        low = token.lower()
        top = active[-1] if active else None
        if low == "select":
            active.append(_Select(depth=depth))
        elif token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
            while active and active[-1].depth > depth:
                done = active.pop()
                done.flush()
                finished.append(done)
        elif top and depth == top.depth and low == "from":
            top.flush()
            finished.append(active.pop())
        elif top and depth == top.depth and token == ",":
            top.flush()
        elif top and depth == top.depth and low != "distinct":
            top.current.append(token)
    for leftover in active:
        leftover.flush()
        finished.append(leftover)

    names: set[str] = set()
    for select in finished:
        for item in select.items:
            name = _item_name(item)
            if name:
                names.add(name)
    return names

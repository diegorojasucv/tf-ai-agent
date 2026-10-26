"""Persistencia SQLite de entradas y salidas de tools por conversación."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .checkpointer import resolve_sqlite_path

logger = logging.getLogger(__name__)
_SENSITIVE_KEY = re.compile(r"(api[_-]?key|token|secret|password|authorization|credential)", re.IGNORECASE)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_MAX_VALUE_CHARS = 100_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    node TEXT NOT NULL,
    name TEXT NOT NULL,
    ok INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_code TEXT,
    input_json TEXT NOT NULL,
    output_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_traces_thread_id_id
    ON tool_traces(thread_id, id);
"""

_TOKEN_COLUMNS = ("input_tokens", "output_tokens", "total_tokens")


def _redact(value: Any, depth: int = 0) -> Any:
    if depth > 20:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item, depth + 1) for item in value]
    if isinstance(value, str):
        safe = _BEARER.sub("Bearer [REDACTED]", value)
        if len(safe) > _MAX_VALUE_CHARS:
            return safe[:_MAX_VALUE_CHARS] + "… [TRUNCATED]"
        return safe
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, default=str)


def init_trace_store(path: str | Path | None = None) -> Path:
    """Crea la tabla de trazas, si todavía no existe."""
    database = resolve_sqlite_path(path)
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.executescript(_SCHEMA)
        existing = {row[1] for row in connection.execute("PRAGMA table_info(tool_traces)")}
        for column in _TOKEN_COLUMNS:
            if column not in existing:
                connection.execute(f"ALTER TABLE tool_traces ADD COLUMN {column} INTEGER")
    return database


def record_trace(
    *,
    thread_id: str,
    node: str,
    name: str,
    ok: bool,
    duration_ms: int,
    input_data: Any,
    output_data: Any,
    error_code: str | None = None,
    tokens: dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> None:
    """Guarda una invocación sin permitir que un fallo de logging interrumpa el agente."""
    try:
        database = init_trace_store(path)
        with sqlite3.connect(database, timeout=10) as connection:
            connection.execute("PRAGMA busy_timeout = 10000")
            connection.execute(
                """INSERT INTO tool_traces
                   (thread_id, timestamp, node, name, ok, duration_ms, error_code, input_json, output_json,
                    input_tokens, output_tokens, total_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    thread_id,
                    datetime.now(timezone.utc).isoformat(),
                    node,
                    name,
                    int(ok),
                    max(0, int(duration_ms)),
                    error_code,
                    _json(input_data),
                    _json(output_data),
                    *[(tokens or {}).get(column) for column in _TOKEN_COLUMNS],
                ),
            )
    except Exception:  # noqa: BLE001 - el registro de trazas no debe romper la ejecución del agente
        logger.exception("No se pudo persistir la traza de %s", name)


def get_trace_events(thread_id: str, path: str | Path | None = None) -> list[dict[str, Any]]:
    """Devuelve los eventos de una conversación en orden cronológico."""
    database = init_trace_store(path)
    with sqlite3.connect(database, timeout=10) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT id, thread_id, timestamp, node, name, ok, duration_ms,
                      error_code, input_json, output_json, input_tokens, output_tokens, total_tokens
               FROM tool_traces WHERE thread_id = ? ORDER BY id""",
            (thread_id,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["ok"] = bool(event["ok"])
        event["input"] = json.loads(event.pop("input_json"))
        event["output"] = json.loads(event.pop("output_json"))
        events.append(event)
    return events

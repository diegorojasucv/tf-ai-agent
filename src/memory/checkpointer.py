"""Checkpointer SQLite: persistencia del estado del agente entre pasos y sesiones."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from src.tools.common import ROOT


def get_checkpointer(path: str | Path | None = None) -> SqliteSaver:
    """Abre (o crea) la base SQLite indicada por SQLITE_PATH."""
    raw = Path(path or os.environ.get("SQLITE_PATH", "data/agent.db"))
    file = raw if raw.is_absolute() else ROOT / raw
    file.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(file, check_same_thread=False))

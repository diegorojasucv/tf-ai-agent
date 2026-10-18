"""Construcción del grafo por defecto a partir del entorno (separado para poder sustituirlo en tests)."""

from __future__ import annotations

from typing import Any

from src.agents.graph import build_graph
from src.agents.llm import get_llm
from src.memory.checkpointer import get_checkpointer


def load_graph() -> Any:
    return build_graph(get_llm(), checkpointer=get_checkpointer())

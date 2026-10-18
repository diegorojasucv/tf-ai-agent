"""Sesión de conversación sobre el grafo: traduce invoke/resume a turnos simples para la UI."""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command


class AgentSession:
    """Un hilo (thread_id) del agente. El estado persiste en el checkpointer."""

    def __init__(self, graph: Any, thread_id: str | None = None) -> None:
        self.graph = graph
        self.thread_id = thread_id or uuid.uuid4().hex
        self.config = {"configurable": {"thread_id": self.thread_id}, "recursion_limit": 40}

    def send(self, text: str) -> dict[str, Any]:
        """Primer mensaje del hilo (el pedido inicial)."""
        return self._turn(self.graph.invoke({"messages": [HumanMessage(text)], "request": text}, self.config))

    def resume(self, value: Any) -> dict[str, Any]:
        """Responde a la pausa actual: texto (pregunta) o decisión {accion, ...} (aprobación)."""
        return self._turn(self.graph.invoke(Command(resume=value), self.config))

    def pending(self) -> dict[str, Any] | None:
        """Payload de la pausa pendiente, p. ej. tras reiniciar la app."""
        for task in self.graph.get_state(self.config).tasks:
            if task.interrupts:
                return task.interrupts[0].value
        return None

    def _turn(self, result: dict[str, Any]) -> dict[str, Any]:
        interrupts = result.get("__interrupt__")
        if interrupts:
            payload = interrupts[0].value
            kind = "pregunta" if payload["tipo"] == "pregunta" else "aprobacion"
            return {"estado": kind, "payload": payload, "trace": result.get("trace", [])}
        status = result.get("status")
        last = result["messages"][-1].content if result.get("messages") else ""
        estado = {"pr_creada": "completado", "rechazado": "rechazado"}.get(status, "error")
        return {"estado": estado, "mensaje": str(last), "pr": result.get("pr"), "trace": result.get("trace", [])}

"""Evaluación del agente: dataset, ejecución por caso y métricas."""

from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.runner import AgentSession
from src.tools.common import ROOT

DATASET = Path(__file__).parent / "dataset" / "casos.jsonl"
MAX_TURNS = 6


class Esperado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resultado: Literal["pr_creada", "pregunta", "rechazado", "error"]
    modelo: str | None = None
    columna: str | None = None
    test: str | None = None
    argumentos: dict[str, Any] = Field(default_factory=dict)
    severity: str | None = None


class Caso(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    categoria: str
    peticion: str
    respuestas: list[str] = Field(default_factory=list)
    decision: Literal["aprobar", "rechazar"] = "aprobar"
    esperado: Esperado
    herramientas_esperadas: list[str] = Field(default_factory=list)
    herramientas_prohibidas: list[str] = Field(default_factory=list)


class RecordingGitHub:
    """GitHub falso: lee el archivo local como 'rama base' y registra las llamadas. No toca GitHub."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if tool == "get_file_contents":
            return (ROOT / args["path"]).read_text(encoding="utf-8")
        if tool == "create_pull_request":
            return '{"html_url": "https://github.com/eval/eval/pull/1"}'
        return "ok"


def load_dataset(path: Path = DATASET) -> list[Caso]:
    return [Caso.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _norm(value: Any) -> str:
    return re.sub(r"[\s'\"]", "", json.dumps(value, sort_keys=True)) if not isinstance(value, str) else re.sub(r"[\s'\"]", "", value)


def _args_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return all(k in actual and _norm(actual[k]) == _norm(v) for k, v in expected.items())


def _proposal_matches(esp: Esperado, payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    checks = [
        esp.modelo in (None, payload.get("modelo")),
        esp.columna in (None, payload.get("columna")),
        esp.test in (None, payload.get("test")),
        esp.severity in (None, payload.get("severity")),
        _args_match(esp.argumentos, payload.get("argumentos") or {}),
    ]
    return all(checks)


def run_case(caso: Caso, graph: Any, github: RecordingGitHub, thread_id: str | None = None) -> dict[str, Any]:
    """Ejecuta un caso con un usuario simulado y devuelve sus métricas."""
    session = AgentSession(graph, thread_id or f"eval-{caso.id}-{int(time.time())}")
    started = time.monotonic()
    replies = list(caso.respuestas)
    trace: list[dict[str, Any]] = []
    payload: dict[str, Any] | None = None
    pr_before_approval = False
    error: str | None = None
    outcome = "error"
    try:
        turn = session.send(caso.peticion)
        for _ in range(MAX_TURNS):
            trace = turn.get("trace", [])
            if turn["estado"] == "pregunta":
                if not replies:
                    outcome = "pregunta"
                    break
                turn = session.resume(replies.pop(0))
            elif turn["estado"] == "aprobacion":
                payload = turn["payload"]
                pr_before_approval = pr_before_approval or bool(github.calls)
                turn = session.resume({"accion": caso.decision} | ({"motivo": "evaluación"} if caso.decision == "rechazar" else {}))
            else:
                outcome = {"completado": "pr_creada", "rechazado": "rechazado"}.get(turn["estado"], "error")
                if outcome == "error":
                    error = turn.get("mensaje")
                break
    except Exception as exc:  # noqa: BLE001 - un caso fallido no detiene la evaluación
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    # `trace` acumula todo el hilo en el estado; el último turno ya lo trae completo.
    used = [t["herramienta"] for t in trace if t["nodo"] in {"tools", "validate", "create_pr"}]
    esp = caso.esperado
    outcome_ok = outcome == esp.resultado
    detail_ok = _proposal_matches(esp, payload) if esp.resultado in {"pr_creada", "rechazado"} else True
    expected_tools = set(caso.herramientas_esperadas)
    forbidden_hit = sorted(set(caso.herramientas_prohibidas) & set(used))
    recall = len(expected_tools & set(used)) / len(expected_tools) if expected_tools else 1.0
    return {
        "id": caso.id,
        "categoria": caso.categoria,
        "resultado": outcome,
        "esperado": esp.resultado,
        "task_success": outcome_ok and detail_ok and not pr_before_approval,
        "tool_selection": recall if not forbidden_hit else 0.0,
        "herramientas_usadas": used,
        "prohibidas_usadas": forbidden_hit,
        "pasos_llm": sum(1 for t in trace if t["nodo"] == "agent"),
        "errores_de_tool": sum(1 for t in trace if not t["ok"]),
        "pr_antes_de_aprobar": pr_before_approval,
        "latencia_s": round(time.monotonic() - started, 2),
        "error": error,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(results) or 1
    lat = sorted(r["latencia_s"] for r in results) or [0.0]
    return {
        "casos": len(results),
        "task_success": round(sum(r["task_success"] for r in results) / n, 3),
        "tool_selection": round(sum(r["tool_selection"] for r in results) / n, 3),
        "pasos_llm_promedio": round(statistics.fmean([r["pasos_llm"] for r in results] or [0]), 2),
        "errores_de_tool_total": sum(r["errores_de_tool"] for r in results),
        "latencia_s_promedio": round(statistics.fmean(lat), 2),
        "latencia_s_p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        "pr_antes_de_aprobar": sum(r["pr_antes_de_aprobar"] for r in results),
    }


def to_markdown(summary: dict[str, Any], results: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {r['id']} | {r['categoria']} | {r['esperado']} | {r['resultado']} | {'si' if r['task_success'] else 'NO'} | "
        f"{r['tool_selection']:.2f} | {r['pasos_llm']} | {r['latencia_s']} |"
        for r in results
    )
    metrics = "\n".join(f"- **{k}:** {v}" for k, v in summary.items())
    return (
        f"# Resultados de evaluación\n\nModelo: `{meta['provider']}/{meta['model']}`  |  Fecha: {meta['fecha']}\n\n{metrics}\n\n"
        "| caso | categoría | esperado | obtenido | éxito | tool selection | pasos LLM | latencia (s) |\n|---|---|---|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def run_all(
    casos: list[Caso], make_graph: Callable[[RecordingGitHub], Any], progress: Callable[[str], None] = print
) -> list[dict[str, Any]]:
    results = []
    for caso in casos:
        github = RecordingGitHub()
        result = run_case(caso, make_graph(github), github)
        progress(f"{caso.id} {caso.categoria}: {'OK' if result['task_success'] else 'FALLA'} ({result['latencia_s']}s)")
        results.append(result)
    return results

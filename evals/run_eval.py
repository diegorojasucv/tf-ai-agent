"""CLI de evaluación: python -m evals.run_eval [--dry-run] [--ids c01 c02] [--limit N]"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from evals.harness import RecordingGitHub, load_dataset, run_all, summarize, to_markdown
from src.agents.graph import build_graph
from src.agents.llm import DEFAULT_MODELS, get_llm
from src.memory.checkpointer import get_checkpointer
from src.tools.common import ToolError
from src.tools.dbt.manifest import load_manifest
from src.tools.common import default_manifest_path

RESULTS = Path(__file__).parent / "resultados"


def dry_run() -> int:
    """Valida el dataset contra el manifest real, sin LLM."""
    casos = load_dataset()
    manifest = load_manifest(default_manifest_path())
    names = {m.name: {c.lower() for c in m.columns} for m in manifest.models()}
    problems = []
    for caso in casos:
        esp = caso.esperado
        if esp.modelo and esp.modelo not in names:
            problems.append(f"{caso.id}: el modelo '{esp.modelo}' no existe")
        elif esp.modelo and esp.columna and esp.columna.lower() not in names[esp.modelo]:
            problems.append(f"{caso.id}: la columna '{esp.columna}' no está documentada en '{esp.modelo}'")
    print(f"{len(casos)} casos válidos" if not problems else "\n".join(problems))
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.dry_run:
        return dry_run()
    casos = [c for c in load_dataset() if not args.ids or c.id in args.ids][: args.limit]
    try:
        llm = get_llm()
    except ToolError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1
    db = Path(tempfile.mkdtemp(prefix="eval_")) / "eval.db"
    saver = get_checkpointer(db)

    def make_graph(github: RecordingGitHub):
        return build_graph(llm, github_client=github, checkpointer=saver, repo="eval/eval", base="main")

    results = run_all(casos, make_graph)
    summary = summarize(results)
    provider = (os.environ.get("LLM_PROVIDER") or "gemini").lower()
    meta = {"provider": provider, "model": os.environ.get("LLM_MODEL") or DEFAULT_MODELS[provider], "fecha": datetime.now().strftime("%Y-%m-%d %H:%M")}
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RESULTS / f"{stamp}_{provider}.json").write_text(json.dumps({"meta": meta, "resumen": summary, "casos": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / "ultimo.md").write_text(to_markdown(summary, results, meta), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

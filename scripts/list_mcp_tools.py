"""Imprime las tools del GitHub MCP Server con sus parámetros."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.common import ToolError  # noqa: E402
from src.tools.github.github_mcp import get_github_tools  # noqa: E402


def _params(tool) -> list[str]:
    schema = tool.args_schema if isinstance(tool.args_schema, dict) else {}
    required = set(schema.get("required", []))
    lines = []
    for name, spec in schema.get("properties", {}).items():
        kind = spec.get("type", "?")
        mark = "*" if name in required else " "
        lines.append(f"    {mark} {name}: {kind}")
    return lines


async def main() -> int:
    try:
        tools = await get_github_tools()
    except ToolError as exc:
        print(f"[{exc.code}] {exc.message}", file=sys.stderr)
        return 1
    print(f"{len(tools)} tools disponibles (* = requerido)\n")
    for tool in sorted(tools, key=lambda t: t.name):
        summary = (tool.description or "").strip().splitlines()[0] if tool.description else ""
        print(f"- {tool.name}: {summary}")
        print("\n".join(_params(tool)))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

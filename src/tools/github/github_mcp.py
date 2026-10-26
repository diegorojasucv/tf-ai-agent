"""Cliente del GitHub MCP Server remoto vía langchain-mcp-adapters."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..common import ToolError

SERVER_NAME = "github"


def build_client(url: str | None = None, token: str | None = None) -> MultiServerMCPClient:
    """Crea el cliente MCP; URL y token salen de GITHUB_MCP_URL y GITHUB_TOKEN."""
    url = url or os.environ.get("GITHUB_MCP_URL")
    token = token or os.environ.get("GITHUB_TOKEN")
    if not url:
        raise ToolError("MCP_CONFIG", "Falta GITHUB_MCP_URL.")
    if not token:
        raise ToolError("MCP_CONFIG", "Falta GITHUB_TOKEN.")
    connection: dict[str, Any] = {
        "transport": "streamable_http",
        "url": url,
        "headers": {"Authorization": f"Bearer {token}"},
    }
    return MultiServerMCPClient({SERVER_NAME: connection}, handle_tool_errors=False)  # type: ignore[arg-type]


async def get_github_tools(client: MultiServerMCPClient | None = None) -> list[BaseTool]:
    """Devuelve las tools del servidor MCP como tools de LangChain."""
    client = client or build_client()
    try:
        return await client.get_tools()
    except Exception as exc:  # noqa: BLE001 - frontera de red
        raise ToolError("MCP_CONNECTION", f"No se pudo listar tools del MCP: {type(exc).__name__}") from exc

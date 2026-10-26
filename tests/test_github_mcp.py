import asyncio

import pytest

from src.tools.github import github_mcp
from src.tools.common import ToolError


class FakeTool:
    name = "create_branch"


class FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def get_tools(self) -> list[FakeTool]:
        if self.fail:
            raise ConnectionError("boom Bearer secret-token")
        return [FakeTool()]


def test_get_tools_with_mock_client() -> None:
    tools = asyncio.run(github_mcp.get_github_tools(FakeClient()))  # type: ignore[arg-type]
    assert [t.name for t in tools] == ["create_branch"]


def test_get_tools_error_does_not_leak_token() -> None:
    with pytest.raises(ToolError) as exc:
        asyncio.run(github_mcp.get_github_tools(FakeClient(fail=True)))  # type: ignore[arg-type]
    assert exc.value.code == "MCP_CONNECTION" and "secret-token" not in exc.value.message


def test_build_client_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_MCP_URL", raising=False)
    with pytest.raises(ToolError) as exc:
        github_mcp.build_client()
    assert exc.value.code == "MCP_CONFIG"


def test_build_client_ok() -> None:
    client = github_mcp.build_client(url="https://example.test/mcp/", token="t")
    assert client.connections["github"]["transport"] == "streamable_http"

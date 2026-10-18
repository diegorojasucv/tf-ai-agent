from typing import Any

import pytest

from src.tools.common import ToolError
from src.tools.pr import crear_pr, repo_path_for

ORIGINAL = "models:\n  - name: orders\n"
NEW = ORIGINAL + "    data_tests:\n      - not_null\n"


class FakeGitHub:
    def __init__(self, base_content: str = ORIGINAL, fail_on: str | None = None, reply: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.base_content, self.fail_on, self.reply = base_content, fail_on, reply

    def call(self, tool: str, args: dict[str, Any]) -> str:
        self.calls.append((tool, args))
        if tool == self.fail_on:
            raise RuntimeError("boom token=secret")
        if tool == "get_file_contents":
            return f"successfully downloaded text file (SHA: abc)\n{self.base_content}"
        if tool == "create_pull_request":
            return self.reply or '{"html_url": "https://github.com/o/r/pull/7"}'
        return "ok"


def _pr(client: FakeGitHub, **kw):
    return crear_pr(
        "dbt/models/marts/orders.yml", ORIGINAL, NEW, "orders", "not_null", "Agrega not_null", "cuerpo",
        client=client, repo="o/r", base="main", **kw,
    )


def test_flujo_feliz_orden_y_nunca_escribe_en_base() -> None:
    gh = FakeGitHub()
    res = _pr(gh)
    assert res["ok"] and res["data"]["url"].endswith("/pull/7")
    assert [c[0] for c in gh.calls] == ["get_file_contents", "create_branch", "push_files", "create_pull_request"]
    branch = res["data"]["rama"]
    assert branch.startswith("dbt-test-agent/") and branch != "main"
    assert gh.calls[2][1]["branch"] == branch and gh.calls[2][1]["files"][0]["content"] == NEW
    assert gh.calls[3][1]["base"] == "main" and gh.calls[3][1]["head"] == branch


def test_base_cambiada_aborta_antes_de_crear_rama() -> None:
    gh = FakeGitHub(base_content="otro contenido")
    res = _pr(gh)
    assert res["error"]["code"] == "BASE_CHANGED"
    assert [c[0] for c in gh.calls] == ["get_file_contents"]


@pytest.mark.parametrize("tool", ["get_file_contents", "create_branch", "push_files", "create_pull_request"])
def test_error_en_cada_paso_es_estructurado(tool: str) -> None:
    res = _pr(FakeGitHub(fail_on=tool))
    assert not res["ok"] and res["error"]["code"].endswith("_FAILED")


def test_sin_url_en_respuesta() -> None:
    assert _pr(FakeGitHub(reply="algo raro"))["error"]["code"] == "PR_FAILED"


def test_repo_invalido() -> None:
    res = crear_pr("a.yml", ORIGINAL, NEW, "m", "t", "x", "y", client=FakeGitHub(), repo="no-slash")
    assert res["error"]["code"] == "PR_CONFIG"


@pytest.mark.parametrize("path", ["../a.yml", "/abs/a.yml", "dbt/a.sql"])
def test_ruta_invalida(path: str) -> None:
    res = crear_pr(path, ORIGINAL, NEW, "m", "t", "x", "y", client=FakeGitHub(), repo="o/r")
    assert res["error"]["code"] == "INVALID_INPUT"


def test_repo_path_for_usa_prefijo_del_proyecto() -> None:
    assert repo_path_for("models/marts/orders.yml") == "dbt/models/marts/orders.yml"


def test_toolerror_se_propaga_tal_cual() -> None:
    class Missing:
        def call(self, tool: str, args: dict[str, Any]) -> str:
            raise ToolError("MCP_TOOL_MISSING", "no existe")

    assert _pr(Missing())["error"]["code"] == "MCP_TOOL_MISSING"

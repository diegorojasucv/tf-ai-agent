"""Tool: crea rama, commit y Pull Request vía GitHub MCP. Nunca escribe en la rama base."""

from __future__ import annotations

import asyncio
import ast
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common import ROOT, ToolError, default_project_dir, run_tool
from .github_mcp import get_github_tools

PROTECTED = {"main", "master", "develop"}
_PR_URL = re.compile(r"https://github\.com/[^\s\"'\\]+/pull/\d+")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubClient(Protocol):
    def call(self, tool: str, args: dict[str, Any]) -> str: ...


def _mcp_result_text(value: Any) -> str:
    """Convierte contenido MCP/LangChain a texto, sin la representación Python de bloques."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[{", "{")):
            try:
                parsed = ast.literal_eval(stripped)
            except (SyntaxError, ValueError):
                return value
            if parsed is not value:
                return _mcp_result_text(parsed)
        return value
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return text
        content = value.get("content")
        return _mcp_result_text(content) if content is not None else str(value)
    if isinstance(value, (list, tuple)):
        parts = [_mcp_result_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    return str(value)


class MCPGitHubClient:
    """Adaptador sync sobre las tools MCP (que son async)."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] | None = None

    @staticmethod
    def _run(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        box: dict[str, Any] = {}
        thread = threading.Thread(target=lambda: box.update(v=asyncio.run(coro)))
        thread.start()
        thread.join()
        return box["v"]

    def call(self, tool: str, args: dict[str, Any]) -> str:
        if self._tools is None:
            self._tools = {t.name: t for t in self._run(get_github_tools())}
        if tool not in self._tools:
            raise ToolError("MCP_TOOL_MISSING", f"El servidor MCP no expone la tool '{tool}'.")
        return _mcp_result_text(self._run(self._tools[tool].ainvoke(args)))


class CrearPrInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ruta_repo: str = Field(min_length=1, max_length=256)
    contenido_original: str = Field(max_length=500_000)
    contenido_nuevo: str = Field(min_length=1, max_length=500_000)
    modelo: str = Field(min_length=1, max_length=128)
    test: str = Field(min_length=1, max_length=200)
    titulo: str = Field(min_length=1, max_length=200)
    cuerpo: str = Field(max_length=20_000)

    @field_validator("ruta_repo")
    @classmethod
    def _safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or path.suffix not in {".yml", ".yaml"}:
            raise ValueError("ruta relativa dentro del repo con extensión .yml/.yaml")
        return value


def repo_path_for(schema_path: str, project_dir: str | Path | None = None) -> str:
    """Ruta del schema.yml relativa a la raíz del repo (p. ej. dbt/models/...)."""
    base = Path(project_dir or default_project_dir()).resolve()
    try:
        prefix = base.relative_to(ROOT)
    except ValueError:
        prefix = Path()
    return (prefix / schema_path).as_posix()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").strip().splitlines())


def _github_file_text(response: str) -> str:
    """Quita el encabezado descriptivo que devuelve get_file_contents, si está presente."""
    return re.sub(
        r"\A(?:successfully downloaded text file \(SHA: [^)]+\)|downloaded text file \(SHA: [^)]+\))\s*\n",
        "",
        response,
        count=1,
        flags=re.IGNORECASE,
    )


def _merge_yaml(base: str, proposed: str, current: str) -> str | None:
    """Fusiona la propuesta con la versión actual de base; devuelve None ante conflictos."""
    git = shutil.which("git")
    if not git:
        return None
    with tempfile.TemporaryDirectory(prefix="dbt-pr-merge-") as directory:
        root = Path(directory)
        proposed_path, base_path, current_path = (
            root / name for name in ("proposed.yml", "base.yml", "current.yml")
        )
        proposed_path.write_text(proposed, encoding="utf-8")
        base_path.write_text(base, encoding="utf-8")
        current_path.write_text(current, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    git, "merge-file", "--stdout", "-L", "propuesta", "-L", "base", "-L", "main",
                    str(proposed_path), str(base_path), str(current_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
    return result.stdout if result.returncode == 0 else None


def crear_pr(
    ruta_repo: str,
    contenido_original: str,
    contenido_nuevo: str,
    modelo: str,
    test: str,
    titulo: str,
    cuerpo: str,
    *,
    client: GitHubClient | None = None,
    repo: str | None = None,
    base: str | None = None,
) -> dict[str, Any]:
    """Abre una PR; si cambió la base, fusiona sin conflictos y solicita nueva aprobación."""

    def handler(args: CrearPrInput) -> dict[str, Any]:
        slug = repo or os.environ.get("GITHUB_REPO", "")
        base_branch = base or os.environ.get("BASE_BRANCH", "main")
        if not _REPO.match(slug):
            raise ToolError("PR_CONFIG", "GITHUB_REPO debe tener el formato owner/repo.")
        owner, name = slug.split("/")
        gh = client or MCPGitHubClient()
        branch = f"dbt-test-agent/{_slug(args.modelo)}-{_slug(args.test)}-{uuid.uuid4().hex[:6]}"
        if branch in PROTECTED or branch == base_branch:
            raise ToolError("PR_UNSAFE_BRANCH", "Se rechaza escribir en una rama protegida.")

        def step(code: str, tool: str, payload: dict[str, Any]) -> str:
            try:
                return gh.call(tool, {"owner": owner, "repo": name, **payload})
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - frontera de red
                detail = str(exc)[:300]
                for secret in filter(None, [os.environ.get("GITHUB_TOKEN")]):
                    detail = detail.replace(secret, "***")
                raise ToolError(code, f"Falló '{tool}': {type(exc).__name__}: {detail}") from exc

        current = _github_file_text(
            step("BASE_READ_FAILED", "get_file_contents", {"path": args.ruta_repo, "ref": base_branch})
        )
        if _normalize(args.contenido_original) != _normalize(current):
            merged = _merge_yaml(args.contenido_original, args.contenido_nuevo, current)
            if merged is None:
                raise ToolError(
                    "BASE_CHANGED",
                    f"{args.ruta_repo} cambió en '{base_branch}' y no se pudo fusionar automáticamente "
                    "(conflicto o git no disponible). Actualizá la propuesta y volvé a revisarla.",
                )
            return {
                "necesita_revision": True,
                "contenido_base_actual": current,
                "contenido_fusionado": merged,
                "mensaje": "La base cambió. Se integraron cambios no conflictivos; el YAML fusionado requiere validación y nueva aprobación.",
            }
        step("BRANCH_FAILED", "create_branch", {"branch": branch, "from_branch": base_branch})
        step(
            "PUSH_FAILED",
            "push_files",
            {
                "branch": branch,
                "message": args.titulo,
                "files": [{"path": args.ruta_repo, "content": args.contenido_nuevo}],
            },
        )
        reply = step(
            "PR_FAILED",
            "create_pull_request",
            {"title": args.titulo, "body": args.cuerpo, "head": branch, "base": base_branch, "draft": False},
        )
        found = _PR_URL.search(reply)
        if not found:
            raise ToolError("PR_FAILED", f"No se obtuvo la URL de la PR: {reply[:200]}")
        return {"url": found.group(0), "rama": branch, "base": base_branch}

    raw = {
        "ruta_repo": ruta_repo,
        "contenido_original": contenido_original,
        "contenido_nuevo": contenido_nuevo,
        "modelo": modelo,
        "test": test,
        "titulo": titulo,
        "cuerpo": cuerpo,
    }
    return run_tool(CrearPrInput, raw, handler)

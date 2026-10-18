"""Tool de solo lectura: catálogo y carga progresiva de skills (metadata, SKILL.md, references)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from ruamel.yaml import YAML

from .common import ROOT, ToolError, run_tool

SKILLS_DIR = ROOT / "src" / "skills"
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_RESOURCE_SUFFIXES = {".md", ".yml", ".yaml"}


class ListarSkillsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CargarSkillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(min_length=1, max_length=64, pattern=_NAME.pattern)
    recurso_opcional: str | None = Field(default=None, max_length=128)


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        raise ToolError("SKILL_INVALID", "SKILL.md sin frontmatter.")
    meta = YAML(typ="safe").load(match[1]) or {}
    if not meta.get("name") or not meta.get("description"):
        raise ToolError("SKILL_INVALID", "El frontmatter requiere name y description.")
    return meta, match[2].strip()


def _skill_dir(root: Path, name: str) -> Path:
    path = root / name
    if not (path / "SKILL.md").is_file():
        raise ToolError("SKILL_NOT_FOUND", f"No existe la skill '{name}'.")
    return path


def _resource(skill_dir: Path, name: str) -> Path:
    refs = (skill_dir / "references").resolve()
    path = (refs / name).resolve()
    if path.parent != refs or path.suffix not in _RESOURCE_SUFFIXES or not path.is_file():
        raise ToolError("RESOURCE_NOT_FOUND", f"No existe el recurso '{name}'.")
    return path


def listar_skills(*, skills_dir: str | Path | None = None) -> dict[str, Any]:
    """Nivel 1: nombre y descripción de cada skill, sin cargar su contenido."""

    def handler(_: ListarSkillsInput) -> dict[str, Any]:
        root = Path(skills_dir or SKILLS_DIR)
        items = []
        for path in sorted(root.glob("*/SKILL.md")):
            meta, _body = _split_frontmatter(path.read_text(encoding="utf-8"))
            refs = sorted(p.name for p in (path.parent / "references").glob("*") if p.suffix in _RESOURCE_SUFFIXES)
            items.append({"nombre": meta["name"], "descripcion": meta["description"], "recursos": refs})
        return {"skills": items}

    return run_tool(ListarSkillsInput, {}, handler)


def cargar_skill(
    nombre: str,
    recurso_opcional: str | None = None,
    *,
    skills_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Nivel 2: cuerpo de SKILL.md. Nivel 3: un recurso de references/ si se indica."""

    def handler(args: CargarSkillInput) -> dict[str, Any]:
        directory = _skill_dir(Path(skills_dir or SKILLS_DIR), args.nombre)
        if args.recurso_opcional:
            file = _resource(directory, args.recurso_opcional)
            return {"nombre": args.nombre, "recurso": file.name, "contenido": file.read_text(encoding="utf-8")}
        meta, body = _split_frontmatter((directory / "SKILL.md").read_text(encoding="utf-8"))
        return {"nombre": meta["name"], "descripcion": meta["description"], "contenido": body}

    return run_tool(
        CargarSkillInput, {"nombre": nombre, "recurso_opcional": recurso_opcional}, handler
    )


def load_test_catalog(skills_dir: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Catálogo de tests permitidos (fuente única para generar_test)."""
    file = Path(skills_dir or SKILLS_DIR) / "dbt-testing" / "references" / "test-catalog.yml"
    return YAML(typ="safe").load(file.read_text(encoding="utf-8"))["tests"]

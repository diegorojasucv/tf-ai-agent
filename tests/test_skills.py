from pathlib import Path

import pytest

from src.tools.common import default_manifest_path
from src.tools.manifest import load_manifest
from src.tools.skills import cargar_skill, listar_skills, load_test_catalog


def test_listar_skills_incluye_dbt_testing() -> None:
    res = listar_skills()
    assert res["ok"]
    (skill,) = [s for s in res["data"]["skills"] if s["nombre"] == "dbt-testing"]
    assert "test-catalog.yml" in skill["recursos"] and skill["descripcion"]


def test_cargar_skill_devuelve_cuerpo_sin_frontmatter() -> None:
    res = cargar_skill("dbt-testing")
    assert res["ok"] and res["data"]["contenido"].startswith("# dbt-testing")


def test_cargar_recurso() -> None:
    res = cargar_skill("dbt-testing", "yaml-syntax.md")
    assert res["ok"] and "data_tests" in res["data"]["contenido"]


@pytest.mark.parametrize("recurso", ["../SKILL.md", "../../common.py", "nada.md", "x.py"])
def test_recurso_invalido_o_fuera_de_references(recurso: str) -> None:
    assert cargar_skill("dbt-testing", recurso)["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_skill_inexistente_y_nombre_invalido() -> None:
    assert cargar_skill("no-existe")["error"]["code"] == "SKILL_NOT_FOUND"
    assert cargar_skill("../etc")["error"]["code"] == "INVALID_INPUT"


def test_skill_sin_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "SKILL.md").write_text("sin frontmatter")
    assert cargar_skill("x", skills_dir=tmp_path)["error"]["code"] == "SKILL_INVALID"


def test_catalogo_bien_formado() -> None:
    catalog = load_test_catalog()
    for name, spec in catalog.items():
        assert spec["level"] in {"column", "model"}, name
        assert spec["package"] in {None, "dbt_utils", "dbt_expectations"}, name


@pytest.mark.integration
def test_catalogo_existe_en_paquetes_instalados() -> None:
    path = default_manifest_path()
    if not path.is_file():
        pytest.skip("manifest real ausente")
    macros = load_manifest(path).macros
    for name, spec in load_test_catalog().items():
        if spec["package"]:
            assert f"macro.{spec['package']}.test_{name}" in macros, name

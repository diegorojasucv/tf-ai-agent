from pathlib import Path

import pytest

from src.tools.dbt.buscar_columna import buscar_columna
from src.tools.common import default_manifest_path
from src.tools.dbt.info_proyecto import info_proyecto, detect_tests_key
from src.tools.dbt.leer_modelo import leer_modelo
from src.tools.dbt.listar_modelos import listar_modelos
from src.tools.dbt.sql_columns import select_columns


def _contract(result: dict) -> None:
    assert set(result) == {"ok", "data", "error"}


# --- info_proyecto
def test_info_proyecto_ok(manifest_path: Path) -> None:
    res = info_proyecto(manifest_path=manifest_path)
    _contract(res)
    data = res["data"]
    assert res["ok"] and data["dbt_version"] == "2.0.8"
    assert data["manifest_schema_version"] == 12
    assert data["tests_key"] == "data_tests"
    assert data["packages"] == ["dbt_utils"]
    assert data["dbt_expectations_installed"] is False
    assert data["generated_at"].startswith("2026-10-18")


def test_manifest_missing(tmp_path: Path) -> None:
    for call in (
        lambda p: info_proyecto(manifest_path=p),
        lambda p: listar_modelos(manifest_path=p),
        lambda p: buscar_columna("a", manifest_path=p),
        lambda p: leer_modelo("a", manifest_path=p),
    ):
        res = call(tmp_path / "nope.json")
        assert not res["ok"] and res["error"]["code"] == "MANIFEST_NOT_FOUND"


def test_manifest_invalid(tmp_path: Path) -> None:
    bad = tmp_path / "m.json"
    bad.write_text("{not json")
    assert info_proyecto(manifest_path=bad)["error"]["code"] == "MANIFEST_INVALID"


@pytest.mark.parametrize(
    ("version", "key"), [("1.7.9", "tests"), ("1.8.0", "data_tests"), ("2.0.8", "data_tests")]
)
def test_detect_tests_key(version: str, key: str) -> None:
    assert detect_tests_key(version) == key


# --- listar_modelos
def test_listar_modelos_all_and_filter(manifest_path: Path) -> None:
    all_ = listar_modelos(manifest_path=manifest_path)["data"]
    assert {i["nombre"] for i in all_["items"]} == {
        "orders", "stg_orders", "order_items", "ecom.raw_orders"
    }
    filtered = listar_modelos("stg", manifest_path=manifest_path)["data"]
    assert [i["nombre"] for i in filtered["items"]] == ["stg_orders"]


def test_listar_modelos_invalid_input(manifest_path: Path) -> None:
    res = listar_modelos("x" * 101, manifest_path=manifest_path)
    assert res["error"]["code"] == "INVALID_INPUT"


# --- buscar_columna
def test_buscar_columna_documentada(manifest_path: Path) -> None:
    res = buscar_columna("customer_id", "orders", manifest_path=manifest_path)
    (match,) = res["data"]["coincidencias"]
    assert match["origen"] == "documentada" and match["tabla"] == "orders"
    assert match["schema_path"] == "models/marts/orders.yml"


def test_buscar_columna_no_busca_en_sql_si_no_esta_en_manifest(manifest_path: Path) -> None:
    res = buscar_columna("subtotal", manifest_path=manifest_path)
    assert not res["ok"]
    assert res["error"]["code"] == "COLUMN_NOT_FOUND"


def test_buscar_columna_en_varios_modelos(manifest_path: Path) -> None:
    res = buscar_columna("ORDER_ID", manifest_path=manifest_path)
    assert res["data"]["ambigua"] is True
    assert {m["tabla"] for m in res["data"]["coincidencias"]} >= {"orders", "stg_orders"}


def test_buscar_columna_inexistente(manifest_path: Path) -> None:
    assert buscar_columna("nope", manifest_path=manifest_path)["error"]["code"] == "COLUMN_NOT_FOUND"


def test_buscar_columna_tabla_inexistente(manifest_path: Path) -> None:
    res = buscar_columna("order_id", "zzz", manifest_path=manifest_path)
    assert res["error"]["code"] == "MODEL_NOT_FOUND"


def test_buscar_columna_input_vacio(manifest_path: Path) -> None:
    assert buscar_columna("", manifest_path=manifest_path)["error"]["code"] == "INVALID_INPUT"


# --- leer_modelo
def test_leer_modelo_ok(manifest_path: Path, project_dir: Path) -> None:
    res = leer_modelo("orders", manifest_path=manifest_path, project_dir=project_dir)
    data = res["data"]
    assert res["ok"] and data["schema_path"] == "models/marts/orders.yml"
    assert "order_id" in {c["nombre"] for c in data["columnas"]}
    assert "data_tests:" in data["yaml"]
    names = {(t["nombre"], t["columna"]) for t in data["tests"]}
    assert ("not_null", "order_id") in names
    assert ("expression_is_true", None) in names
    assert all("model" not in t["argumentos"] for t in data["tests"])


def test_leer_modelo_inexistente(manifest_path: Path, project_dir: Path) -> None:
    res = leer_modelo("nada", manifest_path=manifest_path, project_dir=project_dir)
    assert res["error"]["code"] == "MODEL_NOT_FOUND"


def test_leer_modelo_yaml_faltante_da_warning(manifest_path: Path, tmp_path: Path) -> None:
    res = leer_modelo("orders", manifest_path=manifest_path, project_dir=tmp_path)
    assert res["ok"] and res["data"]["yaml"] is None and res["data"]["warnings"]


# --- sql_columns
def test_select_columns_handles_jinja_and_aliases() -> None:
    sql = """with s as (select * from {{ source('a','b') }}),
    r as (select id as order_id, t.store_id, {{ f('x') }} as total,
          cast(y as int) as y2, count(*) as n from s)
    select * from r"""
    assert select_columns(sql) >= {"order_id", "store_id", "total", "y2", "n"}


# --- integración (manifest real)
@pytest.mark.integration
def test_integration_real_manifest() -> None:
    path = default_manifest_path()
    if not path.is_file():
        pytest.skip("manifest real ausente")
    info = info_proyecto()
    assert info["ok"] and info["data"]["tests_key"] in {"data_tests", "tests"}
    models = listar_modelos()["data"]["items"]
    first = next(i for i in models if i["tipo"] == "model")
    assert leer_modelo(first["nombre"])["ok"]

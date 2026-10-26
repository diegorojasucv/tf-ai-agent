import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from src.tools.common import default_manifest_path
from src.tools.dbt.generar_test import generar_test


@pytest.fixture
def manifest(tmp_path: Path, manifest_path: Path) -> Path:
    data = json.loads(manifest_path.read_text())
    data["macros"].update(
        {
            "macro.dbt_utils.test_not_constant": {},
            "macro.jaffle_shop.test_is_positive": {},
        }
    )
    data["nodes"]["model.jaffle_shop.orders"]["columns"]["order_total"] = {"name": "order_total", "description": ""}
    out = tmp_path / "manifest.json"
    out.write_text(json.dumps(data))
    return out


def _gen(manifest: Path, project_dir: Path, **kw):
    return generar_test(manifest_path=manifest, project_dir=project_dir, **kw)


def _parses(text: str) -> dict:
    return YAML(typ="safe").load(text)


def test_accepted_range_columna_sin_documentar(manifest: Path, project_dir: Path) -> None:
    res = _gen(
        manifest, project_dir, modelo="stg_orders", test="accepted_range", columna="subtotal",
        argumentos={"min_value": 0, "max_value": 100000, "inclusive": False}, 
    )
    assert res["ok"], res
    data = res["data"]
    assert data["complejidad"] == "simple" and data["requiere_aprobacion"]
    assert data["test"] == "dbt_utils.accepted_range" and data["advertencias"]
    col = [c for c in _parses(data["yaml_nuevo"])["models"][0]["columns"] if c["name"] == "subtotal"][0]
    assert col["data_tests"][0]["dbt_utils.accepted_range"]["arguments"] == {
        "min_value": 0, "max_value": 100000, "inclusive": False,
    }
    assert "+          - dbt_utils.accepted_range:" in data["diff"]


def test_no_escribe_archivos(manifest: Path, project_dir: Path) -> None:
    path = project_dir / "models/marts/orders.yml"
    before = path.read_text()
    _gen(manifest, project_dir, modelo="orders", test="not_null", columna="location_id")
    assert path.read_text() == before


def test_agrega_a_lista_existente_y_conserva_formato(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="not_null", columna="customer_id")
    diff = res["data"]["diff"]
    assert "+          - not_null" in diff
    assert [l for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")] == []


def test_test_simple_en_columna_con_nombre_plano(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="not_null", columna="order_total")
    assert res["ok"] and res["data"]["test"] == "not_null"


def test_duplicado(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="not_null", columna="order_id")
    assert res["error"]["code"] == "DUPLICATE_TEST"


def test_config_where_y_severity(manifest: Path, project_dir: Path) -> None:
    res = _gen(
        manifest, project_dir, modelo="orders", test="accepted_values", columna="location_id",
        argumentos={"values": ["a", "b"]}, severity="warn", where="ordered_at >= '2024-01-01'",
    )
    entry = _parses(res["data"]["yaml_nuevo"])["models"][0]["columns"][2]["data_tests"][0]["accepted_values"]
    assert entry["arguments"] == {"values": ["a", "b"]}
    assert entry["config"] == {"severity": "warn", "where": "ordered_at >= '2024-01-01'"}


def test_nivel_modelo(manifest: Path, project_dir: Path) -> None:
    ok = _gen(manifest, project_dir, modelo="stg_orders", test="dbt_utils.expression_is_true",
              argumentos={"expression": "subtotal >= 0"})
    assert ok["ok"]
    bad = _gen(manifest, project_dir, modelo="stg_orders", test="expression_is_true", columna="subtotal",
               argumentos={"expression": "x"})
    assert bad["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"modelo": "orders", "test": "relationships", "columna": "order_id", "argumentos": {"to": "ref('x')"}}, "INVALID_ARGUMENTS"),
        ({"modelo": "orders", "test": "not_null", "columna": "order_id", "argumentos": {"zzz": 1}}, "INVALID_ARGUMENTS"),
        ({"modelo": "orders", "test": "accepted_range", "columna": "order_total"}, "INVALID_ARGUMENTS"),
        ({"modelo": "orders", "test": "not_null"}, "INVALID_INPUT"),
        ({"modelo": "orders", "test": "not_null", "columna": "nope"}, "COLUMN_NOT_FOUND"),
        ({"modelo": "nada", "test": "not_null", "columna": "x"}, "MODEL_NOT_FOUND"),
        ({"modelo": "orders", "test": "not null!", "columna": "order_id"}, "INVALID_INPUT"),
        ({"modelo": "orders", "test": "not_null", "columna": "order_id", "severity": "fatal"}, "INVALID_INPUT"),
        ({"modelo": "orders", "test": "dbt_utils.not_null", "columna": "order_id"}, "INVALID_INPUT"),
    ],
)
def test_errores_de_validacion(manifest: Path, project_dir: Path, kwargs: dict, code: str) -> None:
    assert _gen(manifest, project_dir, **kwargs)["error"]["code"] == code


def test_paquete_no_instalado(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="expect_column_values_to_be_between", columna="order_total")
    assert res["error"]["code"] == "PACKAGE_NOT_INSTALLED"


def test_test_inexistente_se_rechaza(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="mi_test_magico", columna="order_id")
    assert res["error"]["code"] == "TEST_NOT_ALLOWED"


def test_test_de_paquete_fuera_del_catalogo(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="not_constant", columna="order_id")
    assert res["error"]["code"] == "TEST_NOT_IN_CATALOG"


def test_macro_propia_es_compleja(manifest: Path, project_dir: Path) -> None:
    res = _gen(manifest, project_dir, modelo="orders", test="is_positive", columna="order_total")
    assert res["ok"], res
    assert res["data"]["complejidad"] == "compleja" and res["data"]["requiere_aprobacion"]
    assert res["data"]["test"] == "is_positive"


def test_modelo_sin_schema_local(manifest: Path, tmp_path: Path) -> None:
    res = _gen(manifest, tmp_path, modelo="orders", test="not_null", columna="location_id")
    assert res["error"]["code"] == "NO_SCHEMA_FILE"


def test_manifest_ausente(tmp_path: Path) -> None:
    res = generar_test("orders", "not_null", "x", manifest_path=tmp_path / "no.json")
    assert res["error"]["code"] == "MANIFEST_NOT_FOUND"


@pytest.mark.integration
def test_integration_dbt_expectations_real() -> None:
    if not default_manifest_path().is_file():
        pytest.skip("manifest real ausente")
    res = generar_test(
        "orders", "expect_column_values_to_be_within_n_stdevs", "order_total", {"sigma_threshold": 3}
    )
    assert res["ok"], res
    assert res["data"]["test"] == "dbt_expectations.expect_column_values_to_be_within_n_stdevs"
    assert res["data"]["requiere_aprobacion"]

from pathlib import Path

from ruamel.yaml import YAML

from src.tools.dbt.cambiar_test import eliminar_test, modificar_test


def _parses(text: str) -> dict:
    return YAML(typ="safe").load(text)


def _del(manifest_path: Path, project_dir: Path, **kw):
    return eliminar_test(manifest_path=manifest_path, project_dir=project_dir, **kw)


def _mod(manifest_path: Path, project_dir: Path, **kw):
    return modificar_test(manifest_path=manifest_path, project_dir=project_dir, **kw)


def test_eliminar_quita_solo_ese_test_y_avisa_si_es_clave(manifest_path: Path, project_dir: Path) -> None:
    res = _del(manifest_path, project_dir, modelo="orders", test="unique", columna="order_id")
    assert res["ok"], res
    data = res["data"]
    col = _parses(data["yaml_nuevo"])["models"][0]["columns"][0]
    assert col["data_tests"] == ["not_null"]
    assert data["operacion"] == "eliminar" and data["requiere_aprobacion"]
    assert "duplicados" in data["advertencias"][0]
    assert [l for l in data["diff"].splitlines() if l.startswith("+") and not l.startswith("+++")] == []


def test_eliminar_no_avisa_para_otros_tests(manifest_path: Path, project_dir: Path) -> None:
    res = _del(manifest_path, project_dir, modelo="orders", test="relationships", columna="customer_id")
    assert res["ok"] and res["data"]["advertencias"] == []
    col = [c for c in _parses(res["data"]["yaml_nuevo"])["models"][0]["columns"] if c["name"] == "customer_id"][0]
    assert "data_tests" not in col


def test_eliminar_ambiguo_y_desambiguado_por_argumentos(manifest_path: Path, project_dir: Path) -> None:
    res = _del(manifest_path, project_dir, modelo="orders", test="dbt_utils.expression_is_true")
    assert res["error"]["code"] == "AMBIGUOUS_TEST"
    res = _del(
        manifest_path, project_dir, modelo="orders", test="expression_is_true",
        argumentos_actuales={"expression": "order_total = subtotal + tax_paid"},
    )
    assert res["ok"]
    tests = _parses(res["data"]["yaml_nuevo"])["models"][0]["data_tests"]
    assert len(tests) == 1


def test_eliminar_inexistente(manifest_path: Path, project_dir: Path) -> None:
    res = _del(manifest_path, project_dir, modelo="orders", test="accepted_values", columna="order_id")
    assert res["error"]["code"] == "TEST_NOT_FOUND"


def test_eliminar_no_escribe_archivos(manifest_path: Path, project_dir: Path) -> None:
    path = project_dir / "models/marts/orders.yml"
    before = path.read_text()
    _del(manifest_path, project_dir, modelo="orders", test="not_null", columna="order_id")
    assert path.read_text() == before


def test_modificar_severity_de_test_plano(manifest_path: Path, project_dir: Path) -> None:
    res = _mod(manifest_path, project_dir, modelo="orders", test="not_null", columna="order_id", severity="warn")
    assert res["ok"], res
    col = _parses(res["data"]["yaml_nuevo"])["models"][0]["columns"][0]
    assert col["data_tests"] == [{"not_null": {"config": {"severity": "warn"}}}, "unique"]
    assert res["data"]["operacion"] == "modificar"


def test_modificar_argumentos_de_test_existente(manifest_path: Path, project_dir: Path) -> None:
    res = _mod(
        manifest_path, project_dir, modelo="orders", test="dbt_utils.expression_is_true",
        argumentos_actuales={"expression": "order_total = subtotal + tax_paid"},
        argumentos={"expression": "order_total >= 0"},
    )
    assert res["ok"], res
    tests = _parses(res["data"]["yaml_nuevo"])["models"][0]["data_tests"]
    assert tests[1]["dbt_utils.expression_is_true"]["arguments"] == {"expression": "order_total >= 0"}


def test_modificar_valida_argumentos_contra_el_catalogo(manifest_path: Path, project_dir: Path) -> None:
    res = _mod(
        manifest_path, project_dir, modelo="orders", test="dbt_utils.expression_is_true",
        argumentos_actuales={"expression": "order_total = subtotal + tax_paid"}, argumentos={"inventado": 1},
    )
    assert res["error"]["code"] == "INVALID_ARGUMENTS"


def test_modificar_sin_cambios(manifest_path: Path, project_dir: Path) -> None:
    res = _mod(manifest_path, project_dir, modelo="orders", test="not_null", columna="order_id")
    assert res["error"]["code"] == "INVALID_INPUT"
    res = _mod(manifest_path, project_dir, modelo="orders", test="not_null", columna="order_id", argumentos={})
    assert res["error"]["code"] == "NO_CHANGES"

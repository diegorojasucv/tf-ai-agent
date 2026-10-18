from pathlib import Path

import pytest

from src.tools import validar_yaml as mod
from src.tools.common import ROOT, ToolError, default_manifest_path
from src.tools.generar_test import generar_test
from src.tools.validar_yaml import validar_yaml

GOOD = "models:\n  - name: orders\n    columns:\n      - name: order_id\n        data_tests:\n          - not_null\n"


def _v(manifest_path: Path, content: str, **kw):
    return validar_yaml("models/marts/orders.yml", content, ejecutar_dbt_parse=False, manifest_path=manifest_path, **kw)


def test_yaml_valido_sin_parse(manifest_path: Path) -> None:
    res = _v(manifest_path, GOOD)
    assert res["ok"] and res["data"]["valido"] and res["data"]["dbt_parse"]["ejecutado"] is False


def test_yaml_sintaxis_invalida(manifest_path: Path) -> None:
    assert _v(manifest_path, "models: [\n  - a")["error"]["code"] == "YAML_INVALID"


@pytest.mark.parametrize(
    "content",
    ["- solo una lista\n", "models:\n  - description: sin nombre\n", "models:\n  - name: a\n    data_tests: not_null\n"],
)
def test_estructura_invalida(manifest_path: Path, content: str) -> None:
    assert _v(manifest_path, content)["error"]["code"] == "STRUCTURE_INVALID"


def test_clave_legacy_es_advertencia(manifest_path: Path) -> None:
    res = _v(manifest_path, "models:\n  - name: a\n    tests:\n      - unique\n")
    assert res["ok"] and "data_tests" in res["data"]["advertencias"][0]


@pytest.mark.parametrize("path", ["../x.yml", "/etc/x.yml", "models/x.txt", "models/../../x.yml"])
def test_ruta_invalida(manifest_path: Path, path: str) -> None:
    res = validar_yaml(path, GOOD, ejecutar_dbt_parse=False, manifest_path=manifest_path)
    assert res["error"]["code"] == "INVALID_INPUT"


def test_manifest_ausente(tmp_path: Path) -> None:
    res = validar_yaml("models/x.yml", GOOD, ejecutar_dbt_parse=False, manifest_path=tmp_path / "no.json")
    assert res["error"]["code"] == "MANIFEST_NOT_FOUND"


def test_parse_se_ejecuta_y_fallo_se_reporta(manifest_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_ok(*a):
        calls.append(a)
        return {"ejecutado": True, "ok": True, "duracion_s": 0.1}

    monkeypatch.setattr(mod, "run_dbt_parse", fake_ok)
    res = validar_yaml("models/marts/orders.yml", GOOD, manifest_path=manifest_path)
    assert res["data"]["dbt_parse"]["ok"] and calls[0][2] == "models/marts/orders.yml"

    def fake_fail(*a):
        raise ToolError("PARSE_FAILED", "dbt parse falló: boom")

    monkeypatch.setattr(mod, "run_dbt_parse", fake_fail)
    assert validar_yaml("models/marts/orders.yml", GOOD, manifest_path=manifest_path)["error"]["code"] == "PARSE_FAILED"


@pytest.mark.integration
def test_integration_dbt_parse_real_no_modifica_el_proyecto() -> None:
    if not default_manifest_path().is_file() or not (ROOT / "dbt" / "dbt_packages").is_dir():
        pytest.skip("proyecto dbt real no disponible")
    gen = generar_test("orders", "not_null", "location_id")
    assert gen["ok"], gen
    target = ROOT / "dbt" / gen["data"]["schema_path"]
    before = target.read_text()
    res = validar_yaml(gen["data"]["schema_path"], gen["data"]["yaml_nuevo"])
    assert res["ok"], res
    assert target.read_text() == before


@pytest.mark.integration
def test_integration_parse_detecta_test_roto() -> None:
    if not default_manifest_path().is_file() or not (ROOT / "dbt" / "dbt_packages").is_dir():
        pytest.skip("proyecto dbt real no disponible")
    original = (ROOT / "dbt/models/marts/orders.yml").read_text()
    broken = original.replace("    columns:\n", "    columns:\n      - name: x\n        data_tests:\n          - test_que_no_existe\n", 1)
    res = validar_yaml("models/marts/orders.yml", broken)
    assert not res["ok"] and res["error"]["code"] == "PARSE_FAILED"

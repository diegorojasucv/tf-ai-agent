"""Tools expuestas al LLM: envoltorios con esquemas simples y salida {ok, data, error} en JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from src.tools.buscar_columna import buscar_columna
from src.tools.generar_test import generar_test
from src.tools.info_proyecto import info_proyecto
from src.tools.leer_modelo import leer_modelo
from src.tools.listar_modelos import listar_modelos
from src.tools.skills import cargar_skill

# Campos voluminosos que el LLM no necesita ver; el grafo conserva el resultado completo.
_HIDDEN = {"leer_modelo": ("yaml",), "generar_test": ("yaml_original", "yaml_nuevo")}


class _NoArgs(BaseModel):
    pass


class _Listar(BaseModel):
    filtro_opcional: str | None = Field(default=None, description="Texto a buscar en el nombre.")


class _Buscar(BaseModel):
    nombre_columna: str = Field(description="Nombre de la columna.")
    tabla_opcional: str | None = Field(default=None, description="Modelo o source para acotar.")


class _Leer(BaseModel):
    modelo: str = Field(description="Nombre del modelo.")


class _Skill(BaseModel):
    nombre: str = Field(description="Nombre de la skill, p. ej. dbt-testing.")
    recurso_opcional: str | None = Field(default=None, description="Archivo de references/ a leer.")


class _Generar(BaseModel):
    modelo: str = Field(description="Modelo donde va el test.")
    test: str = Field(description="Nombre del test del catálogo, p. ej. accepted_range o dbt_utils.accepted_range.")
    columna: str | None = Field(default=None, description="Columna (solo para tests de columna).")
    argumentos_json: str = Field(default="{}", description='Argumentos del test como objeto JSON, p. ej. {"min_value": 0}.')
    severity: str | None = Field(default=None, description="warn o error.")
    where: str | None = Field(default=None, description="Filtro SQL (Spark SQL) opcional.")


def _generar(argumentos_json: str = "{}", **kwargs: Any) -> dict[str, Any]:
    try:
        args = json.loads(argumentos_json or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": "argumentos_json no es JSON válido."}}
    if not isinstance(args, dict):
        return {"ok": False, "data": None, "error": {"code": "INVALID_INPUT", "message": "argumentos_json debe ser un objeto."}}
    return generar_test(argumentos=args, **kwargs)


def llm_view(tool_name: str, result: dict[str, Any]) -> str:
    """Resultado de la tool en JSON para el LLM, sin los campos voluminosos."""
    data = result.get("data")
    if result.get("ok") and isinstance(data, dict):
        data = {k: v for k, v in data.items() if k not in _HIDDEN.get(tool_name, ())}
    return json.dumps({**result, "data": data}, ensure_ascii=False)


def build_tools(
    *, manifest_path: str | Path | None = None, project_dir: str | Path | None = None
) -> dict[str, BaseTool]:
    """Tools de lectura y generación. validar_yaml y crear_pr NO se exponen: las ejecuta el grafo."""
    paths = {"manifest_path": manifest_path}
    with_dir = {**paths, "project_dir": project_dir}

    def make(name: str, fn: Callable[..., dict[str, Any]], desc: str, schema: type[BaseModel]) -> BaseTool:
        return StructuredTool.from_function(func=fn, name=name, description=desc, args_schema=schema)

    return {
        t.name: t
        for t in [
            make("info_proyecto", lambda: info_proyecto(**with_dir),
                 "Versión de dbt, clave de tests, paquetes instalados y frescura del manifest.", _NoArgs),
            make("listar_modelos", lambda filtro_opcional=None: listar_modelos(filtro_opcional, **paths),
                 "Lista modelos y sources del proyecto, con filtro opcional por nombre.", _Listar),
            make("buscar_columna", lambda nombre_columna, tabla_opcional=None: buscar_columna(nombre_columna, tabla_opcional, **paths),
                 "Busca una columna; indica si es 'documentada' o 'solo_en_sql' y si aparece en varios modelos (ambigua).", _Buscar),
            make("leer_modelo", lambda modelo: leer_modelo(modelo, **with_dir),
                 "Columnas, tests existentes y ruta del schema.yml de un modelo.", _Leer),
            make("cargar_skill", lambda nombre, recurso_opcional=None: cargar_skill(nombre, recurso_opcional),
                 "Carga las instrucciones de una skill (o un recurso de su carpeta references/).", _Skill),
            make("generar_test", lambda **kw: _generar(**kw, **with_dir),
                 "Propone un test de dbt para un modelo/columna. No escribe archivos: el usuario aprueba antes de la PR.", _Generar),
        ]
    }

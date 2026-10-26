"""Loader del manifest de dbt con modelos pydantic tolerantes a la versión del esquema."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..common import ToolError

ADAPTER_PACKAGES = {
    "dbt",
    "dbt_databricks",
    "dbt_spark",
    "dbt_postgres",
    "dbt_snowflake",
    "dbt_bigquery",
    "dbt_redshift",
}


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Metadata(_Lenient):
    dbt_schema_version: str | None = None
    dbt_version: str | None = None
    generated_at: str | None = None
    project_name: str | None = None
    adapter_type: str | None = None


class Column(_Lenient):
    name: str
    description: str = ""
    data_type: str | None = None


class GenericTestMetadata(_Lenient):
    name: str | None = None
    namespace: str | None = None
    kwargs: dict[str, Any] = Field(default_factory=dict)


class Node(_Lenient):
    unique_id: str
    name: str
    resource_type: str
    package_name: str | None = None
    path: str | None = None
    original_file_path: str | None = None
    patch_path: str | None = None
    description: str = ""
    columns: dict[str, Column] = Field(default_factory=dict)
    raw_code: str | None = None
    attached_node: str | None = None
    column_name: str | None = None
    test_metadata: GenericTestMetadata | None = None


class Source(_Lenient):
    unique_id: str
    name: str
    source_name: str
    package_name: str | None = None
    original_file_path: str | None = None
    description: str = ""
    columns: dict[str, Column] = Field(default_factory=dict)


class Manifest(_Lenient):
    metadata: Metadata
    nodes: dict[str, Node] = Field(default_factory=dict)
    sources: dict[str, Source] = Field(default_factory=dict)
    macros: dict[str, Any] = Field(default_factory=dict)

    @property
    def dbt_version(self) -> str | None:
        return self.metadata.dbt_version

    @property
    def schema_version(self) -> int | None:
        match = re.search(r"/v(\d+)\.json", self.metadata.dbt_schema_version or "")
        return int(match.group(1)) if match else None

    @property
    def generated_at(self) -> datetime | None:
        raw = self.metadata.generated_at
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def models(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.resource_type == "model"]

    def find_model(self, name: str) -> Node:
        """Busca un modelo por nombre o unique_id (sin distinguir mayúsculas)."""
        needle = name.strip().lower()
        hits = [
            m for m in self.models() if needle in (m.name.lower(), m.unique_id.lower())
        ]
        if not hits:
            raise ToolError("MODEL_NOT_FOUND", f"No existe el modelo '{name}'.")
        if len(hits) > 1:
            own = [m for m in hits if m.package_name == self.metadata.project_name]
            hits = own or hits
        if len(hits) > 1:
            ids = ", ".join(m.unique_id for m in hits)
            raise ToolError("AMBIGUOUS_MODEL", f"'{name}' coincide con varios modelos: {ids}.")
        return hits[0]

    def tests_for(self, unique_id: str) -> list[Node]:
        return [
            n
            for n in self.nodes.values()
            if n.resource_type == "test" and n.attached_node == unique_id
        ]

    def installed_packages(self) -> list[str]:
        """Paquetes de terceros inferidos de los macros (excluye dbt, adapters y el proyecto)."""
        found = {key.split(".")[1] for key in self.macros if key.count(".") >= 2}
        found -= ADAPTER_PACKAGES
        found.discard(self.metadata.project_name or "")
        return sorted(found)


def load_manifest(path: str | Path) -> Manifest:
    """Lee y valida el manifest; lanza ToolError si falta o es inválido."""
    file = Path(path)
    if not file.is_file():
        raise ToolError(
            "MANIFEST_NOT_FOUND",
            f"No existe el manifest en {file}. Ejecutá scripts/refresh_manifest.py.",
        )
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
        return Manifest(**raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ToolError("MANIFEST_INVALID", f"Manifest ilegible: {exc}") from exc

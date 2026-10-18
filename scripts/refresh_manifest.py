"""Regenera el manifest con `dbt parse` usando el profile dummy (sin conexión)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: str) -> Path:
    path = Path(os.environ.get(name, default))
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    project_dir = _path_from_env("DBT_PROJECT_DIR", "dbt")
    profiles_dir = _path_from_env("DBT_PROFILES_DIR", "ci")
    manifest_path = _path_from_env("DBT_MANIFEST_PATH", "dbt/target/manifest.json")

    cmd = [
        "dbt",
        "parse",
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(profiles_dir),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        print("dbt parse falló", file=sys.stderr)
        return result.returncode

    generated = project_dir / "target" / "manifest.json"
    if not generated.exists():
        print(f"No se generó {generated}", file=sys.stderr)
        return 1
    if generated.resolve() != manifest_path.resolve():
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generated, manifest_path)
    print(f"Manifest listo en {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

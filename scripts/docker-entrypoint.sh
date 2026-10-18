#!/bin/sh
set -e
# Instala paquetes dbt y regenera el manifest (sin conexión) antes de arrancar.
if [ ! -d "${DBT_PROJECT_DIR:-dbt}/dbt_packages" ]; then
  dbt deps --project-dir "${DBT_PROJECT_DIR:-dbt}" --profiles-dir "${DBT_PROFILES_DIR:-ci}"
fi
python scripts/refresh_manifest.py
exec "$@"

# Sintaxis de data_tests en dbt 2.x

Formato del proyecto: 2 espacios, listas indentadas bajo su clave, `data_tests:` y argumentos en `arguments:`.

## Test de columna

```yaml
models:
  - name: stg_orders
    columns:
      - name: order_id
        data_tests:
          - not_null
          - unique
      - name: subtotal
        data_tests:
          - dbt_utils.accepted_range:
              arguments:
                min_value: 0
                max_value: 100000
                inclusive: false
```

## Test de modelo

```yaml
models:
  - name: orders
    data_tests:
      - dbt_utils.expression_is_true:
          arguments:
            expression: "order_total = subtotal + tax_paid"
```

## Configuración del test (where, severity)

`config` va junto a `arguments`, no dentro:

```yaml
- relationships:
    arguments:
      to: ref('stg_customers')
      field: customer_id
    config:
      severity: warn
      where: "ordered_at >= current_date - interval 7 days"
```

## Reglas

- Los paquetes se prefijan con su nombre: `dbt_utils.` y `dbt_expectations.`.
- Si el modelo ya tiene `data_tests:`, agregar a la lista existente; no crear una segunda clave.
- Strings con operadores o dos puntos van entre comillas.
- Valores de `where` y expresiones: Spark SQL / Databricks SQL.

# Contexto del proyecto

Estoy construyendo mi Trabajo Final Integrador (TFI) de la Certificación en AI Agent Developer (ITBA).

## Fuentes de referencia
- **Consigna oficial:** docs/consigna_tfi.pdf. Es la referencia principal: ante cualquier duda de alcance, entregables, README o rúbrica, mandan estos documentos.
- **Notebooks de las clases:** están en notebooks/. Consultalas solo si hacen falta (por ejemplo, para recordar cómo se vio un patrón de LangGraph, HITL o MCP). No copies código sin entenderlo ni adaptarlo a este proyecto.

## Qué es
Un agente que traduce pedidos en lenguaje natural a tests de dbt y abre una Pull Request en GitHub con el test agregado.
Ejemplo: "agrega un test que valide que amount en sales sea > 0 y < 100000" -> el agente ubica la columna en el proyecto dbt, genera el test en el schema.yml correcto y abre una PR.
Si el test es complejo (ej. detección de anomalías), el agente pausa y pide aprobación humana (HITL) antes de crear la PR.

## Stack (no cambiar sin consultarme)
- Python 3.11+
- LangGraph (agente, estado, checkpointer SQLite, interrupt() para HITL)
- LangChain core + langchain-mcp-adapters para consumir el MCP de GitHub como tools
- **GitHub MCP Server** (github/github-mcp-server) para leer archivos, crear rama, commit y PR. No usar PyGithub salvo que el MCP no cubra algo, y en ese caso avisame.
- Streamlit (interfaz, desplegable en Streamlit Community Cloud)
- ruamel.yaml para editar schema.yml preservando comentarios y formato
- **dbt-core + dbt-databricks**: mi proyecto dbt real corre sobre Databricks
- pytest, Docker + docker-compose
- LLM configurable por variables de entorno, sin hardcodear nada

## Decisiones sobre Databricks y dbt
- El agente NO se conecta al warehouse. Trabaja sobre archivos del repo dbt (schema.yml, models/, tests/).
- Validación local: ruamel.yaml (parseo) + `dbt parse` con un profile dummy. No ejecutar `dbt test` ni `dbt compile` contra Databricks.
- Respetar la sintaxis de la versión de dbt del proyecto (`data_tests:` en dbt >= 1.8, `tests:` en versiones anteriores). Detectarla leyendo dbt_project.yml / packages.
- El SQL de tests singulares y de anomalías debe ser compatible con Spark SQL / Databricks SQL.
- Preferir dbt_utils y tests nativos. Usar dbt_expectations solo si el proyecto ya lo tiene instalado (compatibilidad parcial con Databricks): el agente debe revisar packages.yml antes de proponerlo.

## Arquitectura: agente único robusto (NO multiagente, NO RAG)
Flujo:
1. Clasificar pedido: simple / complejo / ambiguo
2. Tools de exploración (via MCP de GitHub + helpers propios): listar_modelos, buscar_columna, leer_schema_yml
3. Si hay varios candidatos (ej. stg_sales vs fct_sales) -> preguntar al usuario
4. generar_test (usa la skill dbt-testing) + validar_yaml
5. Si es complejo -> interrupt() para HITL (aprobar / editar / rechazar)
6. crear_pr vía MCP: create_branch -> create_or_update_file -> create_pull_request. NUNCA escribir en main.
7. Respuesta final con link a la PR

Al inicio, listá las tools que expone el MCP en la versión instalada y usá los nombres reales. No asumas nombres de memoria.

## Requisitos obligatorios del TFI
(Detalle completo en docs/consigna_tfi.pdf. Cada decisión debe cubrirlos.)
1. Capacidad agéntica: >= 2 tools, selección dinámica de acciones, validación de entradas/salidas, manejo de errores. No secuencia fija.
2. Al menos una skill reutilizable (skills/dbt-testing).
3. Estado y memoria con persistencia básica (checkpointer SQLite).
4. HITL: al menos una acción pausable con aprobar/modificar/rechazar.
5. Integración externa real (GitHub MCP).
6. Interfaz usable sin tocar código (Streamlit).
7. Ejecución reproducible: README, .env.example, dependencias, Docker Compose. Cero secretos.
8. Evidencia de calidad: tests de tools y del recorrido principal, dataset de evaluación (15-20 casos), métricas (task success, tool selection, pasos, latencia) y trazabilidad.
README con las 13 secciones que pide la consigna.

## Principios
- Prioridad: solución acotada, estable y bien evaluada > arquitectura ambiciosa.
- Anomalías: tests SQL/dbt (singulares o dbt_utils), sin modelos estadísticos propios.
- Seguridad: token fine-grained de GitHub con permisos mínimos sobre un solo repo; nunca escribir en main; nunca loguear tokens.
- Código tipado, funciones chicas, docstrings cortos, nombres en inglés, documentación en español.
- Cada tool devuelve errores estructurados {ok, data, error}, no excepciones crudas.
- Los tests mockean el MCP de GitHub y el LLM; nada de llamadas reales en CI.
- No agregues librerías, agentes ni componentes innecesarios.

## Estructura del repo
README.md, .env.example, requirements.txt, docker-compose.yml, Dockerfile,
src/{agents,tools,skills,memory,ui}, dbt/, tests/, evals/{dataset,resultados}, docs/{arquitectura, consigna_tfi.pdf}

## Cómo trabajar conmigo
- Trabajá por fases y esperá mi OK antes de pasar a la siguiente.
- Antes de escribir código, explicá en pocas líneas qué vas a hacer y por qué.
- Si una API de LangGraph/LangChain/MCP no es la que recordás, avisame en vez de inventarla.
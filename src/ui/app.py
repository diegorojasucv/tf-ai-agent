"""Interfaz Streamlit del agente. Ejecutar: streamlit run src/ui/app.py"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from src.agents.runner import AgentSession  # noqa: E402
from src.agents.llm_errors import classify_llm_error  # noqa: E402
from src.memory.trace_store import get_trace_events  # noqa: E402
from src.tools.common import ToolError  # noqa: E402
from src.tools.dbt.info_proyecto import info_proyecto  # noqa: E402
from src.tools.github.github_mcp import get_github_tools  # noqa: E402
from src.ui import deps  # noqa: E402

st.set_page_config(page_title="Data Quality Agent", page_icon=None, layout="wide")
logger = logging.getLogger(__name__)


@st.cache_resource
def _graph():
    return deps.load_graph()


def _tool_schema(tool) -> dict:
    schema = tool.args_schema
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    if hasattr(schema, "schema"):
        return schema.schema()
    return {}


def _github_mcp_inventory() -> dict:
    cached = st.session_state.get("github_mcp_inventory")
    if cached is not None:
        return cached

    if not os.environ.get("GITHUB_MCP_URL") or not os.environ.get("GITHUB_TOKEN"):
        inventory = {"tools": [], "error": "Configura GITHUB_MCP_URL y GITHUB_TOKEN para conectar GitHub MCP."}
    else:
        try:
            tools = asyncio.run(get_github_tools())
            inventory = {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "schema": _tool_schema(tool),
                    }
                    for tool in tools
                ],
                "error": None,
            }
        except ToolError as exc:
            inventory = {"tools": [], "error": f"No se pudo conectar ({exc.code}): {exc.message}"}

    st.session_state.github_mcp_inventory = inventory
    return inventory


def _mcp_section() -> None:
    with st.expander("MCP conectados", on_change="rerun") as section:
        if not section.open:
            return

        if st.button("Actualizar MCP", key="actualizar_mcp", icon=":material/refresh:"):
            st.session_state.pop("github_mcp_inventory", None)
            st.rerun()

        inventory = _github_mcp_inventory()
        if inventory["error"]:
            st.warning(inventory["error"], title="GitHub MCP no conectado")
            return

        tools = inventory["tools"]
        st.success(f"GitHub MCP conectado · {len(tools)} tools disponibles")
        for tool in sorted(tools, key=lambda item: item["name"]):
            with st.expander(tool["name"]):
                if tool["description"]:
                    st.write(tool["description"])
                schema = tool["schema"]
                properties = schema.get("properties", {})
                required = set(schema.get("required", []))
                if not properties:
                    st.caption("No requiere parámetros.")
                for name, details in properties.items():
                    details = details if isinstance(details, dict) else {}
                    kind = details.get("type", "valor")
                    requirement = "requerido" if name in required else "opcional"
                    description = details.get("description", "")
                    st.markdown(f"- `{name}` ({kind}, {requirement})" + (f": {description}" if description else ""))


def _reset() -> None:
    for key in ("session", "turn", "history", "trace"):
        st.session_state.pop(key, None)


def _say(role: str, text: str) -> None:
    st.session_state.history.append((role, text))


def _apply(turn: dict) -> None:
    """Guarda el turno y refleja en el chat lo que el agente dice."""
    st.session_state.turn = turn
    st.session_state.trace = st.session_state.get("trace", []) + turn.get("trace", [])
    if turn["estado"] == "pregunta":
        _say("assistant", turn["payload"]["mensaje"])
    elif turn["estado"] != "aprobacion":
        _say("assistant", turn["mensaje"])


def _run(action) -> None:
    try:
        with st.spinner("Trabajando..."):
            _apply(action())
    except ToolError as exc:
        _say("assistant", f"Error de configuración ({exc.code}): {exc.message}")
        st.session_state.turn = {"estado": "error"}
    except Exception as exc:  # noqa: BLE001 - frontera de la UI
        classified = classify_llm_error(exc)
        if classified:
            category, message = classified
            logger.warning("Fallo de proveedor LLM: categoría=%s tipo=%s", category, type(exc).__name__)
            _say("assistant", message)
        else:
            logger.exception("Error inesperado durante la ejecución del agente: tipo=%s", type(exc).__name__)
            _say("assistant", f"Error inesperado ({type(exc).__name__}). Revisa el log del servidor para más detalles.")
        st.session_state.turn = {"estado": "error"}


def _approval_card(payload: dict, session: AgentSession) -> None:
    target = f"{payload['modelo']}.{payload['columna']}" if payload.get("columna") else payload["modelo"]
    st.subheader("Revisión humana")
    operation = {"crear": "Agregar", "modificar": "Modificar", "eliminar": "Eliminar"}.get(payload.get("operacion", "crear"), "Agregar")
    st.write(f"**{operation} test:** `{payload['test']}` en `{target}`  |  **Archivo:** `{payload['schema_path']}`  |  **Complejidad:** {payload['complejidad']}")
    validation = payload["validacion"]
    if validation["valido"]:
        st.success("Validación OK (sintaxis, estructura y dbt parse offline).")
    else:
        st.error(f"Validación fallida ({validation.get('codigo')}): {validation.get('mensaje')}")
    for warning in payload.get("advertencias", []) + validation.get("advertencias", []):
        st.warning(warning)
    st.code(payload["diff"], language="diff")
    cols = st.columns(2)
    if cols[0].button("Aprobar y abrir PR", type="primary", key="aprobar", disabled=not validation["valido"]):
        _say("user", "Aprobado.")
        _run(lambda: session.resume({"accion": "aprobar"}))
        st.rerun()
    with st.expander("Editar el YAML"):
        edited = st.text_area("schema.yml", payload["yaml_nuevo"], height=300, key="yaml_edit")
        if st.button("Enviar edición", key="editar"):
            _say("user", "Edité el YAML.")
            _run(lambda: session.resume({"accion": "editar", "contenido_yaml": edited}))
            st.rerun()
    reason = st.text_input("Motivo del rechazo (opcional)", key="motivo")
    if cols[1].button("Rechazar", key="rechazar"):
        _say("user", "Rechazado.")
        _run(lambda: session.resume({"accion": "rechazar", "motivo": reason or None}))
        st.rerun()


def _trace_detail(thread_id: str) -> None:
    st.title("Detalle de trazabilidad")
    st.caption("Entradas y salidas persistidas por invocación. Los valores sensibles conocidos se redactan.")
    st.caption("Para volver a tu conversación, cierra esta pestaña de detalle.")
    try:
        events = get_trace_events(thread_id)
    except Exception as exc:  # noqa: BLE001 - errores de lectura de observabilidad
        st.error(f"No se pudo leer la trazabilidad ({type(exc).__name__}).")
        return
    if not events:
        st.info("Todavía no hay eventos guardados para esta conversación.")
        return

    failed = sum(not event["ok"] for event in events)
    first, second, third = st.columns(3)
    first.metric("Invocaciones", len(events))
    second.metric("Con error", failed)
    third.metric("Duración total", f"{sum(e['duration_ms'] for e in events)} ms")
    for index, event in enumerate(events, start=1):
        state = "OK" if event["ok"] else f"Error · {event['error_code'] or 'sin código'}"
        label = f"{index}. {event['name']} · {state} · {event['duration_ms']} ms"
        with st.expander(label, expanded=index == len(events)):
            st.caption(f"{event['timestamp']} · nodo: {event['node']} · evento: {event['id']}")
            st.markdown("**Entrada**")
            st.json(event["input"])
            st.markdown("**Salida**")
            st.json(event["output"])


def main() -> None:
    trace_thread = st.query_params.get("trace_thread")
    if trace_thread:
        _trace_detail(trace_thread)
        return

    st.title("Data Quality Agent")
    st.caption("Pedí un test en lenguaje natural; el agente lo propone, vos lo aprobás y se abre la PR.")
    st.session_state.setdefault("history", [])

    with st.sidebar:
        if st.button("Nueva conversación"):
            _reset()
            st.rerun()
        info = info_proyecto()
        if info["ok"]:
            data = info["data"]
            st.write(f"dbt {data['dbt_version']} | `{data['tests_key']}`")
            st.write("Paquetes: " + ", ".join(data["packages"]))
        else:
            st.error(info["error"]["message"])
        _mcp_section()
        with st.expander("Trazabilidad"):
            st.dataframe(st.session_state.get("trace", []), use_container_width=True)
            session = st.session_state.get("session")
            if session:
                trace_url = f"?{urlencode({'trace_thread': session.thread_id})}"
                st.link_button(
                    "Ver entradas y salidas",
                    trace_url,
                    icon=":material/open_in_new:",
                    width="stretch",
                )

    for role, text in st.session_state.history:
        with st.chat_message(role):
            st.markdown(text)

    turn = st.session_state.get("turn")
    session: AgentSession | None = st.session_state.get("session")
    if turn and turn["estado"] == "aprobacion" and session:
        _approval_card(turn["payload"], session)
        return
    if turn and turn["estado"] == "completado" and turn.get("pr"):
        st.success(f"PR creada: {turn['pr']['url']}")

    waiting = turn is not None and turn["estado"] == "pregunta"
    prompt = st.chat_input("Respondé al agente..." if waiting else "Ej.: agregá un test que valide que subtotal en stg_orders sea > 0 y < 100000")
    if not prompt:
        return
    _say("user", prompt)
    if waiting and session:
        _run(lambda: session.resume(prompt))
    else:
        try:
            st.session_state.session = session = AgentSession(_graph())
        except ToolError as exc:
            _say("assistant", f"Configuración incompleta ({exc.code}): {exc.message}")
            st.rerun()
        _run(lambda: session.send(prompt))
    st.rerun()


main()

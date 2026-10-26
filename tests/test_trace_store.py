from src.memory.trace_store import get_trace_events, record_trace


def test_trace_se_guarda_en_sqlite_y_redacta_datos_sensibles(tmp_path) -> None:
    database = tmp_path / "traces.db"
    record_trace(
        thread_id="conversation-1",
        node="tools",
        name="example_tool",
        ok=True,
        duration_ms=23,
        input_data={"column": "id", "api_key": "secret-value", "filter": "Bearer token-value"},
        output_data={"ok": True, "data": [1, 2, 3]},
        path=database,
    )

    events = get_trace_events("conversation-1", database)
    assert len(events) == 1
    assert events[0]["input"]["column"] == "id"
    assert events[0]["input"]["api_key"] == "[REDACTED]"
    assert events[0]["input"]["filter"] == "Bearer [REDACTED]"
    assert events[0]["output"]["data"] == [1, 2, 3]
    assert get_trace_events("another-conversation", database) == []

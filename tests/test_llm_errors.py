from src.agents.llm_errors import classify_llm_error


def test_google_503_recibe_mensaje_de_saturacion() -> None:
    exc = RuntimeError(
        "GoogleAPIError: 503 UNAVAILABLE. {'error': {'message': 'high demand'}}"
    )
    category, message = classify_llm_error(exc)
    assert category == "service_unavailable"
    assert "temporalmente saturado" in message
    assert "vuelve a enviar el pedido" in message
    assert "high demand" not in message


def test_rate_limit_y_credenciales_tienen_guia_especifica() -> None:
    assert classify_llm_error(RuntimeError("429 RESOURCE_EXHAUSTED"))[0] == "rate_limit"
    category, message = classify_llm_error(RuntimeError("403 PERMISSION_DENIED"))
    assert category == "authentication"
    assert "LLM_API_KEY" in message


def test_error_no_reconocido_se_deja_al_manejador_generico() -> None:
    assert classify_llm_error(RuntimeError("fallo inesperado")) is None

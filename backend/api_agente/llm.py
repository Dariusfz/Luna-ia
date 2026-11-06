"""
Cliente LLM compatible-OpenAI (plan §5.1). Solo configuración por entorno:
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_SEGUNDOS.
"""

import httpx
from django.conf import settings


class LLMError(Exception):
    pass


def _con_no_think(mensajes: list) -> list:
    """Añade /no_think al último mensaje del sistema (interruptor de qwen3)."""
    copia = [dict(m) for m in mensajes]
    for mensaje in copia:
        if mensaje.get("role") == "system" and "/no_think" not in mensaje.get("content", ""):
            mensaje["content"] = mensaje["content"] + "\n/no_think"
    return copia


def chat(mensajes: list, herramientas: list) -> dict:
    """Llama a /chat/completions y devuelve el mensaje del modelo (puede traer tool_calls)."""
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    cabeceras = {}
    if settings.LLM_API_KEY:
        cabeceras["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
    cuerpo = {
        "model": settings.LLM_MODEL,
        "messages": mensajes,
        "tools": herramientas,
        "tool_choice": "auto",
        "temperature": 0.2,
    }
    # qwen3 razona en bloques <think> antes de cada respuesta; en el chat con pacientes
    # eso solo añade latencia. Se desactiva con el interruptor que entiende el modelo.
    if "qwen3" in settings.LLM_MODEL.lower():
        cuerpo["messages"] = _con_no_think(mensajes)
    try:
        respuesta = httpx.post(
            url,
            json=cuerpo,
            headers=cabeceras,
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_SEGUNDOS, connect=5.0),
        )
    except httpx.HTTPError as error:
        raise LLMError(f"No se pudo contactar al LLM: {error}") from error
    if respuesta.status_code >= 400:
        raise LLMError(f"El LLM devolvió {respuesta.status_code}")
    try:
        return respuesta.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as error:
        raise LLMError("Respuesta del LLM con formato inesperado") from error

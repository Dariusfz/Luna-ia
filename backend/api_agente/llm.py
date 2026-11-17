"""
Cliente LLM compatible-OpenAI (plan §5.1). Solo configuración por entorno:
LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT_SEGUNDOS, LLM_REINTENTOS_429, LLM_USER_AGENT.
"""

import time

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


def _segundos_de_espera(respuesta: httpx.Response, intento: int) -> float:
    """Segundos a esperar antes de reintentar un 429 (usa Retry-After o retryDelay)."""
    cabecera = respuesta.headers.get("retry-after")
    if cabecera:
        try:
            return min(30.0, max(1.0, float(cabecera)))
        except ValueError:
            pass
    # Gemini devuelve el retraso en el cuerpo: error.details[].retryDelay = "27s".
    try:
        detalles = respuesta.json().get("error", {}).get("details", [])
    except ValueError:
        detalles = []
    for detalle in detalles:
        retraso = detalle.get("retryDelay")
        if isinstance(retraso, str) and retraso.endswith("s"):
            try:
                return min(30.0, max(1.0, float(retraso[:-1])))
            except ValueError:
                pass
    return float(min(30.0, 2 ** intento))


def chat(mensajes: list, herramientas: list, session_id: str | None = None) -> dict:
    """Llama a /chat/completions y devuelve el mensaje del modelo (puede traer tool_calls)."""
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    cabeceras = {"User-Agent": settings.LLM_USER_AGENT}
    if settings.LLM_API_KEY:
        cabeceras["Authorization"] = f"Bearer {settings.LLM_API_KEY}"
    if session_id:
        # OpenCode Go lo exige para enrutar y cachear la conversación.
        cabeceras["x-opencode-session"] = session_id
    cuerpo = {
        "model": settings.LLM_MODEL,
        "messages": mensajes,
        "temperature": 0.2,
    }
    if herramientas:
        cuerpo["tools"] = herramientas
        cuerpo["tool_choice"] = "auto"
    # qwen3 razona en bloques <think> antes de cada respuesta; en el chat con pacientes
    # eso solo añade latencia. Se desactiva con el interruptor que entiende el modelo.
    if "qwen3" in settings.LLM_MODEL.lower():
        cuerpo["messages"] = _con_no_think(mensajes)
    intentos = 1 + max(0, settings.LLM_REINTENTOS_429)
    for intento in range(intentos):
        try:
            respuesta = httpx.post(
                url,
                json=cuerpo,
                headers=cabeceras,
                timeout=httpx.Timeout(settings.LLM_TIMEOUT_SEGUNDOS, connect=5.0),
            )
        except httpx.HTTPError as error:
            raise LLMError(f"No se pudo contactar al LLM: {error}") from error
        # 429 = límite de peticiones del proveedor: se reintenta con espera.
        if respuesta.status_code != 429 or intento == intentos - 1:
            break
        time.sleep(_segundos_de_espera(respuesta, intento))
    if respuesta.status_code >= 400:
        detalle = (respuesta.text or "").strip()
        raise LLMError(
            f"El LLM devolvió {respuesta.status_code}" + (f": {detalle[:300]}" if detalle else "")
        )
    try:
        return respuesta.json()["choices"][0]["message"]
    except (KeyError, IndexError, ValueError) as error:
        raise LLMError("Respuesta del LLM con formato inesperado") from error

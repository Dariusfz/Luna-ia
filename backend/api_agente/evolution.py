"""
Cliente de Evolution API v2 (WhatsApp). Solo se llama desde tareas Celery o desde
la capa de respuesta; nunca desde el request del webhook.
"""

import base64

import httpx
from django.conf import settings


class EvolutionError(Exception):
    pass


def _crear_cliente() -> httpx.Client:
    return httpx.Client(
        base_url=settings.EVOLUTION_BASE_URL,
        headers={"apikey": settings.EVOLUTION_API_KEY},
        timeout=httpx.Timeout(20.0, connect=5.0),
    )


def _numero_whatsapp(telefono: str) -> str:
    """Evolution espera el número sin '+' (ej. 50499999999)."""
    return telefono.lstrip("+")


def enviar_texto(telefono: str, texto: str) -> str | None:
    """Envía un texto y devuelve el id del mensaje en WhatsApp (para reconocer su eco)."""
    ruta = f"/message/sendText/{settings.EVOLUTION_INSTANCE}"
    with _crear_cliente() as cliente:
        respuesta = cliente.post(
            ruta, json={"number": _numero_whatsapp(telefono), "text": texto}
        )
    if respuesta.status_code >= 400:
        raise EvolutionError(f"sendText devolvió {respuesta.status_code}")
    try:
        return respuesta.json().get("key", {}).get("id")
    except ValueError:
        return None


def descargar_audio(message_id: str, remote_jid: str) -> tuple[bytes, str]:
    """
    Descarga una nota de voz en memoria. Devuelve (bytes, mimetype).
    Lo usará la transcripción (paso 5); no se guarda en disco.
    """
    ruta = f"/chat/getBase64FromMediaMessage/{settings.EVOLUTION_INSTANCE}"
    cuerpo = {
        "message": {"key": {"id": message_id, "remoteJid": remote_jid, "fromMe": False}},
        "convertToMp4": False,
    }
    with _crear_cliente() as cliente:
        respuesta = cliente.post(ruta, json=cuerpo)
    if respuesta.status_code >= 400:
        raise EvolutionError(f"getBase64FromMediaMessage devolvió {respuesta.status_code}")
    datos = respuesta.json()
    contenido = datos.get("base64", "")
    if "," in contenido:  # algunas versiones devuelven data URI
        contenido = contenido.split(",", 1)[1]
    if not contenido:
        raise EvolutionError("Evolution no devolvió el contenido del audio.")
    return base64.b64decode(contenido), datos.get("mimetype", "audio/ogg")

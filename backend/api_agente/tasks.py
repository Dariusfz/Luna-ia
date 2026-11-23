import logging

import httpx
from celery import shared_task

from . import agente, evolution, transcripcion
from .cifrado import cifrar
from .models import MensajeWhatsApp

logger = logging.getLogger(__name__)

# Se responde cuando la nota de voz no se puede descargar o no se entiende (plan §5.3).
RESPUESTA_AUDIO_NO_DISPONIBLE = (
    "No pude escuchar tu nota de voz. ¿Me la puedes escribir por favor?"
)


def _responder(mensaje: MensajeWhatsApp, texto: str) -> None:
    """Envía la respuesta por Evolution y la guarda cifrada en la conversación."""
    conversacion = mensaje.conversacion
    wa_id = evolution.enviar_texto(conversacion.telefono, texto)
    MensajeWhatsApp.objects.create(
        conversacion=conversacion,
        rol=MensajeWhatsApp.Rol.AGENTE,
        tipo=MensajeWhatsApp.Tipo.TEXTO,
        # Evolution nos devolverá este mismo id como evento "fromMe": así sabemos que es nuestro eco.
        wa_message_id=wa_id or None,
        contenido_cifrado=cifrar(texto),
    )


def _ultimo_mensaje_es_del_paciente(conversacion) -> bool:
    """El LLM no acepta historiales que terminan en un turno del agente (tareas atrasadas)."""
    ultimo = (
        MensajeWhatsApp.objects.filter(conversacion=conversacion)
        .exclude(rol=MensajeWhatsApp.Rol.SISTEMA)
        .order_by("-creado", "-pk")
        .values_list("rol", flat=True)
        .first()
    )
    return ultimo == MensajeWhatsApp.Rol.PACIENTE


@shared_task(
    bind=True,
    autoretry_for=(evolution.EvolutionError, httpx.HTTPError),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def procesar_texto(self, mensaje_id: int) -> None:
    mensaje = MensajeWhatsApp.objects.select_related("conversacion").get(pk=mensaje_id)
    if not mensaje.conversacion.agente_activo:
        # Una persona tomó el hilo mientras el mensaje esperaba en cola.
        logger.info("Conversación %s atendida por personal; no se responde", mensaje.conversacion_id)
        return
    if not _ultimo_mensaje_es_del_paciente(mensaje.conversacion):
        logger.info(
            "El mensaje %s ya no es el último de la conversación %s; se omite",
            mensaje.pk, mensaje.conversacion_id,
        )
        return
    logger.info("Procesando mensaje %s de la conversación %s", mensaje_id, mensaje.conversacion_id)
    respuesta = agente.responder(mensaje.conversacion)
    _responder(mensaje, respuesta)


@shared_task(
    bind=True,
    autoretry_for=(evolution.EvolutionError, httpx.HTTPError),
    retry_backoff=5,
    retry_kwargs={"max_retries": 3},
)
def procesar_audio(self, mensaje_id: int) -> None:
    """
    Descarga la nota de voz, la transcribe con faster-whisper y la trata como un mensaje
    de texto normal (plan §5.3). El audio no se guarda: solo el texto transcrito.
    """
    mensaje = MensajeWhatsApp.objects.select_related("conversacion").get(pk=mensaje_id)
    conversacion = mensaje.conversacion
    if not conversacion.agente_activo:
        return
    if not _ultimo_mensaje_es_del_paciente(conversacion):
        logger.info(
            "El mensaje %s ya no es el último de la conversación %s; se omite",
            mensaje.pk, mensaje.conversacion_id,
        )
        return

    jid = f"{conversacion.telefono.lstrip('+')}@s.whatsapp.net"
    # EvolutionError y httpx.HTTPError se reintentan (autoretry_for).
    audio, mimetype = evolution.descargar_audio(mensaje.wa_message_id, jid)
    try:
        texto = (transcripcion.transcribir(audio, mimetype) or "").strip()
    except transcripcion.TranscripcionError:
        logger.exception("No se pudo transcribir el audio %s", mensaje.pk)
        _responder(mensaje, RESPUESTA_AUDIO_NO_DISPONIBLE)
        return

    if not texto:
        logger.info("El audio %s no tiene voz reconocible", mensaje.pk)
        _responder(mensaje, RESPUESTA_AUDIO_NO_DISPONIBLE)
        return

    # El texto transcrito reemplaza el marcador "[audio]": así el historial y el LLM lo ven.
    mensaje.contenido_cifrado = cifrar(texto)
    mensaje.save(update_fields=["contenido_cifrado"])
    logger.info("Audio %s transcrito (%d caracteres)", mensaje.pk, len(texto))

    respuesta = agente.responder(conversacion)
    _responder(mensaje, respuesta)

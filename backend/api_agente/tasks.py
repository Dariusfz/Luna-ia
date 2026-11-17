import logging

import httpx
from celery import shared_task

from . import agente, evolution
from .cifrado import cifrar
from .models import MensajeWhatsApp

logger = logging.getLogger(__name__)

# Respuesta fija mientras no hay transcripción de audio (paso 5, plan §5.3).
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
    Paso 5 (Whisper) aún no implementado. Mientras tanto aplica el fallback del plan
    (§5.3): pedir al paciente que escriba.
    """
    mensaje = MensajeWhatsApp.objects.select_related("conversacion").get(pk=mensaje_id)
    if not mensaje.conversacion.agente_activo:
        return
    if not _ultimo_mensaje_es_del_paciente(mensaje.conversacion):
        logger.info(
            "El mensaje %s ya no es el último de la conversación %s; se omite",
            mensaje.pk, mensaje.conversacion_id,
        )
        return
    _responder(mensaje, RESPUESTA_AUDIO_NO_DISPONIBLE)

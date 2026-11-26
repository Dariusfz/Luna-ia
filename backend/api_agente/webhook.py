import hmac
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .cifrado import cifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp
from .tasks import procesar_audio, procesar_texto
from . import vigencia

logger = logging.getLogger(__name__)

EVENTOS_MENSAJE = {"messages.upsert", "messages_upsert"}
TIPOS_TEXTO = {"conversation", "extendedTextMessage"}
TIPO_AUDIO = "audioMessage"


def _texto_del_mensaje(mensaje: dict) -> str:
    if "conversation" in mensaje:
        return mensaje["conversation"]
    return mensaje.get("extendedTextMessage", {}).get("text", "")


def _telefono_desde_jid(jid: str) -> str:
    return "+" + jid.split("@", 1)[0]


def _jid_del_contacto(clave: dict) -> str:
    """WhatsApp puede entregar el chat como @lid (linked ID); el teléfono real
    viene en remoteJidAlt. Se prefiere ese JID para guardar y responder."""
    jid = clave.get("remoteJid", "")
    if jid.endswith("@lid"):
        alterno = clave.get("remoteJidAlt", "")
        if alterno.endswith("@s.whatsapp.net"):
            return alterno
    return jid


def _es_numero_admin(telefono: str) -> bool:
    """True si el remitente es uno de los números configurados como administrador.

    Esos números son de uso humano: si escriben, el agente se pausa. Para que el
    agente vuelva a responder hay que reactivarlo manualmente desde el admin.
    """
    digitos = "".join(c for c in telefono if c.isdigit())
    if not digitos:
        return False
    crudos = (getattr(settings, "ADMIN_WHATSAPP", "") or "").split(",")
    return any("".join(c for c in numero if c.isdigit()) == digitos for numero in crudos)


class WebhookEvolutionView(APIView):
    """
    Recibe eventos de Evolution API. Responde 200 rápido y deja el trabajo a Celery,
    porque Evolution tiene timeouts y reintenta si no recibe respuesta a tiempo.

    La autenticación es el secreto en la ruta (EVOLUTION_WEBHOOK_SECRET): Evolution v2
    no firma los webhooks en la versión fijada.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, secreto):
        esperado = settings.EVOLUTION_WEBHOOK_SECRET
        if not esperado or not hmac.compare_digest(secreto, esperado):
            return Response(status=status.HTTP_404_NOT_FOUND)  # no revelar que la ruta existe

        # Evolution envía eventos de sincronización histórica que pueden superar
        # DATA_UPLOAD_MAX_MEMORY_SIZE (2,5 MB por defecto) y Django los rechaza con
        # 400 antes de llegar aquí, haciendo que Evolution reintente en bucle.
        # Solo interesan los mensajes, así que un cuerpo enorme se descarta con 200.
        limite = getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
        largo = int(request.META.get("CONTENT_LENGTH") or 0)
        if largo > limite:
            logger.info("Webhook de Evolution ignorado por tamaño (%s bytes)", largo)
            return Response(status=status.HTTP_200_OK)

        datos = request.data or {}
        evento = str(datos.get("event", "")).lower()
        if evento not in EVENTOS_MENSAJE:
            return Response(status=status.HTTP_200_OK)

        mensaje_data = datos.get("data") or {}
        clave = mensaje_data.get("key") or {}

        # Solo chats 1 a 1. Grupos y difusiones se ignoran.
        jid = _jid_del_contacto(clave)
        if not jid.endswith("@s.whatsapp.net"):
            return Response(status=status.HTTP_200_OK)

        wa_id = clave.get("id")
        from_me = bool(clave.get("fromMe"))
        mensaje = mensaje_data.get("message") or {}
        tipo_wa = mensaje_data.get("messageType", "")

        if tipo_wa in TIPOS_TEXTO:
            tipo, texto = MensajeWhatsApp.Tipo.TEXTO, _texto_del_mensaje(mensaje)
        elif tipo_wa == TIPO_AUDIO and not from_me:
            tipo, texto = MensajeWhatsApp.Tipo.AUDIO, ""
        else:
            # Imágenes, stickers, ubicaciones y audios de la clínica: el agente no los procesa.
            return Response(status=status.HTTP_200_OK)

        if not wa_id or (tipo == MensajeWhatsApp.Tipo.TEXTO and not texto.strip()):
            return Response(status=status.HTTP_200_OK)

        # Mensajes que Evolution acumuló mientras el proyecto estaba apagado: son
        # viejos y responderlos continuaría hilos que ya terminaron.
        motivo = vigencia.motivo_para_ignorar(
            {**mensaje_data, "date_time": mensaje_data.get("date_time") or datos.get("date_time")}
        )
        if motivo:
            logger.info("Mensaje de WhatsApp ignorado (%s): %s", motivo, wa_id)
            return Response(status=status.HTTP_200_OK)

        telefono = _telefono_desde_jid(jid)
        try:
            with transaction.atomic():
                conversacion = ConversacionWhatsApp.objects.filter(telefono=telefono).first()

                # Hilo con el agente desactivado: no se guarda nada hasta reactivarlo.
                if conversacion is not None and not conversacion.agente_activo:
                    return Response(status=status.HTTP_200_OK)

                if from_me:
                    if MensajeWhatsApp.objects.filter(wa_message_id=wa_id).exists():
                        # Eco de una respuesta del propio agente: no es una intervención humana.
                        return Response(status=status.HTTP_200_OK)
                    # Escribió una persona desde el WhatsApp de la clínica: el agente se calla
                    # en este hilo y tampoco se registra el mensaje.
                    if conversacion is not None:
                        conversacion.agente_activo = False
                        conversacion.save(update_fields=["agente_activo", "ultima_actividad"])
                    return Response(status=status.HTTP_200_OK)

                if _es_numero_admin(telefono):
                    # El administrador escribió: el hilo pasa a atención humana y no se guarda.
                    # Solo se reactiva manualmente desde el panel.
                    if conversacion is not None:
                        conversacion.agente_activo = False
                        conversacion.save(update_fields=["agente_activo", "ultima_actividad"])
                    return Response(status=status.HTTP_200_OK)

                if conversacion is None:
                    conversacion = ConversacionWhatsApp.objects.create(telefono=telefono)
                registro = MensajeWhatsApp.objects.create(
                    conversacion=conversacion,
                    rol=MensajeWhatsApp.Rol.PACIENTE,
                    tipo=tipo,
                    wa_message_id=wa_id,
                    contenido_cifrado=cifrar(texto or "[audio]"),
                )
        except IntegrityError:
            # Evolution reenvió el mismo evento: ya está guardado y en cola.
            logger.info("Mensaje WhatsApp duplicado ignorado: %s", wa_id)
            return Response(status=status.HTTP_200_OK)

        tarea = procesar_audio if tipo == MensajeWhatsApp.Tipo.AUDIO else procesar_texto
        # Encolar solo cuando la transacción esté confirmada, para que el worker vea el registro.
        transaction.on_commit(lambda: tarea.delay(registro.pk))
        return Response(status=status.HTTP_200_OK)

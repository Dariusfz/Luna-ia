import base64
from datetime import timedelta
from unittest.mock import patch

import httpx
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import evolution, tasks, transcripcion
from .cifrado import cifrar, descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp

SECRETO = "secreto-de-prueba"
URL = f"/api/agente/webhook/evolution/{SECRETO}/"
TELEFONO = "+50499999999"
JID = "50499999999@s.whatsapp.net"


def evento(
    texto="Hola",
    *,
    jid=JID,
    from_me=False,
    wa_id="MSG1",
    tipo_wa="conversation",
    evento="messages.upsert",
    timestamp=None,
):
    if tipo_wa == "conversation":
        mensaje = {"conversation": texto}
    elif tipo_wa == "extendedTextMessage":
        mensaje = {"extendedTextMessage": {"text": texto}}
    else:
        mensaje = {"audioMessage": {"mimetype": "audio/ogg; codecs=opus"}}
    datos = {
        "event": evento,
        "instance": "luna-ia",
        "data": {
            "key": {"remoteJid": jid, "fromMe": from_me, "id": wa_id},
            "messageType": tipo_wa,
            "message": mensaje,
            "pushName": "Ana",
        },
    }
    if timestamp is not None:
        datos["data"]["messageTimestamp"] = timestamp
    return datos


@override_settings(EVOLUTION_WEBHOOK_SECRET=SECRETO, ADMIN_WHATSAPP="")
class WebhookEvolutionTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.delay_texto = patch.object(tasks.procesar_texto, "delay").start()
        self.delay_audio = patch.object(tasks.procesar_audio, "delay").start()
        self.addCleanup(patch.stopall)

    def test_secreto_incorrecto_responde_404_y_no_guarda_nada(self):
        respuesta = self.api.post("/api/agente/webhook/evolution/otro/", evento(), format="json")
        self.assertEqual(respuesta.status_code, 404)
        self.assertFalse(MensajeWhatsApp.objects.exists())

    def test_sin_secreto_configurado_el_webhook_no_acepta_nada(self):
        with override_settings(EVOLUTION_WEBHOOK_SECRET=""):
            respuesta = self.api.post(URL, evento(), format="json")
        self.assertEqual(respuesta.status_code, 404)

    def test_texto_se_guarda_cifrado_y_se_encola_tras_confirmar(self):
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(URL, evento("Quiero cita mañana"), format="json")
        self.assertEqual(respuesta.status_code, 200)
        conversacion = ConversacionWhatsApp.objects.get(telefono=TELEFONO)
        mensaje = conversacion.mensajes.get()
        self.assertEqual(mensaje.rol, MensajeWhatsApp.Rol.PACIENTE)
        self.assertEqual(mensaje.wa_message_id, "MSG1")
        self.assertEqual(descifrar(mensaje.contenido_cifrado), "Quiero cita mañana")
        self.delay_texto.assert_called_once_with(mensaje.pk)
        self.delay_audio.assert_not_called()

    def test_mismo_mensaje_reenviado_no_se_procesa_dos_veces(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(URL, evento(wa_id="DUP"), format="json")
            respuesta = self.api.post(URL, evento(wa_id="DUP"), format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(MensajeWhatsApp.objects.filter(wa_message_id="DUP").count(), 1)
        self.delay_texto.assert_called_once()

    def test_eco_de_respuesta_del_agente_no_pausa_el_hilo(self):
        conversacion = ConversacionWhatsApp.objects.create(telefono=TELEFONO)
        MensajeWhatsApp.objects.create(
            conversacion=conversacion, rol=MensajeWhatsApp.Rol.AGENTE,
            wa_message_id="ECO1", contenido_cifrado=cifrar("respuesta"),
        )
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(URL, evento(from_me=True, wa_id="ECO1"), format="json")
        self.assertEqual(respuesta.status_code, 200)
        conversacion.refresh_from_db()
        self.assertTrue(conversacion.agente_activo)
        self.assertFalse(MensajeWhatsApp.objects.filter(rol=MensajeWhatsApp.Rol.HUMANO).exists())

    def test_mensaje_escrito_desde_la_clinica_pausa_el_agente_en_ese_hilo(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(URL, evento("Hola, soy Marta de la clínica", from_me=True, wa_id="HUM1"), format="json")
        conversacion = ConversacionWhatsApp.objects.get(telefono=TELEFONO)
        self.assertFalse(conversacion.agente_activo)
        mensaje = conversacion.mensajes.get(wa_message_id="HUM1")
        self.assertEqual(mensaje.rol, MensajeWhatsApp.Rol.HUMANO)
        self.assertEqual(descifrar(mensaje.contenido_cifrado), "Hola, soy Marta de la clínica")
        self.delay_texto.assert_not_called()

    @override_settings(ADMIN_WHATSAPP="+50494165195")
    def test_el_numero_del_administrador_pausa_el_agente_al_escribir(self):
        telefono_admin = "+50494165195"
        ConversacionWhatsApp.objects.create(telefono=telefono_admin, agente_activo=True)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(
                URL,
                evento("Hola, escribo como administrador", jid="50494165195@s.whatsapp.net", wa_id="ADM1"),
                format="json",
            )
        self.assertEqual(respuesta.status_code, 200)
        conversacion = ConversacionWhatsApp.objects.get(telefono=telefono_admin)
        self.assertFalse(conversacion.agente_activo)
        mensaje = conversacion.mensajes.get(wa_message_id="ADM1")
        self.assertEqual(mensaje.rol, MensajeWhatsApp.Rol.HUMANO)
        self.delay_texto.assert_not_called()

    def test_con_el_hilo_pausado_el_paciente_se_guarda_sin_responder(self):
        ConversacionWhatsApp.objects.create(telefono=TELEFONO, agente_activo=False)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(URL, evento("¿Me atienden hoy?", wa_id="PAC9"), format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(MensajeWhatsApp.objects.filter(wa_message_id="PAC9").exists())
        self.delay_texto.assert_not_called()

    def test_tarea_no_responde_si_una_persona_tomo_el_hilo_en_cola(self):
        conversacion = ConversacionWhatsApp.objects.create(telefono=TELEFONO, agente_activo=False)
        mensaje = MensajeWhatsApp.objects.create(
            conversacion=conversacion, rol=MensajeWhatsApp.Rol.PACIENTE, contenido_cifrado=cifrar("hola"),
        )
        with patch("api_agente.evolution.enviar_texto") as enviar:
            tasks.procesar_texto(mensaje.pk)
        enviar.assert_not_called()

    def test_grupos_y_difusiones_se_ignoran(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(URL, evento(jid="120363@g.us"), format="json")
            self.api.post(URL, evento(jid="status@broadcast", wa_id="B"), format="json")
        self.assertFalse(MensajeWhatsApp.objects.exists())

    def test_mensaje_con_lid_usa_el_telefono_alterno(self):
        datos = evento("Hola desde LID", wa_id="LID1")
        datos["data"]["key"]["remoteJid"] = "75574412374121@lid"
        datos["data"]["key"]["remoteJidAlt"] = JID
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(URL, datos, format="json")
        self.assertEqual(respuesta.status_code, 200)
        conversacion = ConversacionWhatsApp.objects.get(telefono=TELEFONO)
        mensaje = conversacion.mensajes.get(wa_message_id="LID1")
        self.assertEqual(mensaje.rol, MensajeWhatsApp.Rol.PACIENTE)
        self.assertEqual(descifrar(mensaje.contenido_cifrado), "Hola desde LID")
        self.delay_texto.assert_called_once_with(mensaje.pk)

    def test_lid_sin_telefono_alterno_se_ignora(self):
        datos = evento("Hola desde LID", wa_id="LID2")
        datos["data"]["key"]["remoteJid"] = "75574412374121@lid"
        respuesta = self.api.post(URL, datos, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(MensajeWhatsApp.objects.exists())

    def test_audio_se_encola_como_audio(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(URL, evento(tipo_wa="audioMessage", wa_id="AUD"), format="json")
        mensaje = MensajeWhatsApp.objects.get(wa_message_id="AUD")
        self.assertEqual(mensaje.tipo, MensajeWhatsApp.Tipo.AUDIO)
        self.delay_audio.assert_called_once_with(mensaje.pk)
        self.delay_texto.assert_not_called()

    def test_extended_text_tambien_es_texto(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.api.post(URL, evento("Hola con link", tipo_wa="extendedTextMessage", wa_id="EXT"), format="json")
        mensaje = MensajeWhatsApp.objects.get(wa_message_id="EXT")
        self.assertEqual(descifrar(mensaje.contenido_cifrado), "Hola con link")

    def test_eventos_que_no_son_mensajes_se_ignoran(self):
        respuesta = self.api.post(URL, evento(evento="connection.update"), format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(MensajeWhatsApp.objects.exists())

    def test_imagenes_no_se_guardan(self):
        datos = evento(wa_id="IMG")
        datos["data"]["messageType"] = "imageMessage"
        self.api.post(URL, datos, format="json")
        self.assertFalse(MensajeWhatsApp.objects.exists())

    def test_mensaje_antiguo_se_ignora_sin_guardar_ni_encolar(self):
        atrasado = (timezone.now() - timedelta(hours=2)).timestamp()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(
                URL, evento("Hola, escrito ayer", wa_id="VIEJO", timestamp=atrasado), format="json"
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(ConversacionWhatsApp.objects.exists())
        self.assertFalse(MensajeWhatsApp.objects.exists())
        self.delay_texto.assert_not_called()

    def test_mensaje_reciente_con_marca_temporal_se_procesa(self):
        ahora = timezone.now().timestamp()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.api.post(
                URL, evento("Hola de ahora", wa_id="NUEVO", timestamp=ahora), format="json"
            )
        self.assertEqual(respuesta.status_code, 200)
        mensaje = MensajeWhatsApp.objects.get(wa_message_id="NUEVO")
        self.delay_texto.assert_called_once_with(mensaje.pk)

    def test_mensaje_anterior_al_arranque_se_ignora(self):
        with patch("api_agente.vigencia.ARRANQUE", timezone.now()), override_settings(
            WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS=3600,
            WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS=30,
        ):
            marca = (timezone.now() - timedelta(minutes=5)).timestamp()
            with self.captureOnCommitCallbacks(execute=True):
                respuesta = self.api.post(
                    URL, evento("Hola antes de reiniciar", wa_id="PREVIO", timestamp=marca), format="json"
                )
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(MensajeWhatsApp.objects.exists())
        self.delay_texto.assert_not_called()


class ProcesarMensajeTests(TestCase):
    def setUp(self):
        self.conversacion = ConversacionWhatsApp.objects.create(telefono=TELEFONO)
        self.mensaje = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=b"x",
        )

    @patch("api_agente.evolution.enviar_texto", return_value="SENT1")
    @patch("api_agente.agente.responder", return_value="Hola, ¿en qué te ayudo?")
    def test_respuesta_del_agente_se_envia_y_se_guarda_cifrada(self, responder, enviar):
        tasks.procesar_texto(self.mensaje.pk)
        responder.assert_called_once()
        enviar.assert_called_once_with(TELEFONO, "Hola, ¿en qué te ayudo?")
        respuesta = self.conversacion.mensajes.get(rol=MensajeWhatsApp.Rol.AGENTE)
        self.assertEqual(descifrar(respuesta.contenido_cifrado), "Hola, ¿en qué te ayudo?")

    @patch("api_agente.evolution.enviar_texto")
    @patch("api_agente.agente.responder")
    def test_no_responde_mensaje_antiguo_que_quedo_en_la_cola(self, responder, enviar):
        MensajeWhatsApp.objects.filter(pk=self.mensaje.pk).update(
            creado=timezone.now() - timedelta(hours=2)
        )
        tasks.procesar_texto(self.mensaje.pk)
        responder.assert_not_called()
        enviar.assert_not_called()

    @patch("api_agente.evolution.enviar_texto", return_value="SENT1")
    @patch(
        "api_agente.transcripcion.transcribir",
        side_effect=transcripcion.TranscripcionError("modelo no disponible"),
    )
    @patch("api_agente.evolution.descargar_audio", return_value=(b"ogg", "audio/ogg"))
    def test_audio_sin_transcripcion_pide_que_escriba(self, descargar, transcribir, enviar):
        tasks.procesar_audio(self.mensaje.pk)
        enviar.assert_called_once_with(TELEFONO, tasks.RESPUESTA_AUDIO_NO_DISPONIBLE)


def _cliente_con(handler):
    return httpx.Client(
        base_url="http://evolution.test",
        headers={"apikey": "clave"},
        transport=httpx.MockTransport(handler),
    )


@override_settings(EVOLUTION_INSTANCE="luna-ia", EVOLUTION_API_KEY="clave")
class EvolutionClienteTests(TestCase):
    def test_enviar_texto_quita_el_mas_y_usa_la_instancia(self):
        capturadas = []

        def handler(request):
            capturadas.append(request)
            return httpx.Response(201, json={})

        with patch.object(evolution, "_crear_cliente", lambda: _cliente_con(handler)):
            evolution.enviar_texto("+50499999999", "Hola")

        peticion = capturadas[0]
        self.assertEqual(peticion.url.path, "/message/sendText/luna-ia")
        self.assertEqual(peticion.headers["apikey"], "clave")
        self.assertIn(b'"number":"50499999999"', peticion.content)

    def test_enviar_texto_con_error_lanza_excepcion(self):
        def handler(request):
            return httpx.Response(500)

        with patch.object(evolution, "_crear_cliente", lambda: _cliente_con(handler)):
            with self.assertRaises(evolution.EvolutionError):
                evolution.enviar_texto("+50499999999", "Hola")

    def test_descargar_audio_decodifica_base64(self):
        contenido = b"audio-de-prueba"

        def handler(request):
            return httpx.Response(
                200,
                json={"base64": base64.b64encode(contenido).decode(), "mimetype": "audio/ogg"},
            )

        with patch.object(evolution, "_crear_cliente", lambda: _cliente_con(handler)):
            datos, mimetype = evolution.descargar_audio("AUD", JID)
        self.assertEqual(datos, contenido)
        self.assertEqual(mimetype, "audio/ogg")

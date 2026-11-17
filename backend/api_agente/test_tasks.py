from unittest.mock import patch

from django.test import TestCase

from .cifrado import cifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp
from .tasks import procesar_audio, procesar_texto


class TareasAgenteTests(TestCase):
    def setUp(self):
        self.conversacion = ConversacionWhatsApp.objects.create(telefono="+50499999999")
        self.paciente = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=cifrar("Hola"),
        )

    def _respuesta_del_agente(self, texto="Ya le respondí."):
        return MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.AGENTE,
            contenido_cifrado=cifrar(texto),
        )

    @patch("api_agente.tasks.evolution.enviar_texto")
    @patch("api_agente.tasks.agente.responder")
    def test_omite_texto_si_ya_hay_respuesta_posterior(self, responder, enviar):
        self._respuesta_del_agente()
        procesar_texto(self.paciente.pk)
        responder.assert_not_called()
        enviar.assert_not_called()

    @patch("api_agente.tasks.evolution.enviar_texto", return_value="wamid")
    @patch("api_agente.tasks.agente.responder", return_value="Hola, ¿en qué le ayudo?")
    def test_responde_si_el_ultimo_mensaje_es_del_paciente(self, responder, enviar):
        procesar_texto(self.paciente.pk)
        responder.assert_called_once_with(self.conversacion)
        enviar.assert_called_once_with(self.conversacion.telefono, "Hola, ¿en qué le ayudo?")
        self.assertTrue(
            MensajeWhatsApp.objects.filter(
                conversacion=self.conversacion, rol=MensajeWhatsApp.Rol.AGENTE
            ).exists()
        )

    @patch("api_agente.tasks.evolution.enviar_texto")
    def test_omite_audio_si_ya_hay_respuesta_posterior(self, enviar):
        audio = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            tipo=MensajeWhatsApp.Tipo.AUDIO,
            contenido_cifrado=cifrar("[audio]"),
        )
        self._respuesta_del_agente()
        procesar_audio(audio.pk)
        enviar.assert_not_called()

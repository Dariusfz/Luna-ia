from unittest.mock import patch

from django.test import TestCase

from . import evolution, transcripcion
from .cifrado import cifrar, descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp
from .tasks import RESPUESTA_AUDIO_NO_DISPONIBLE, procesar_audio, procesar_texto


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

    def _audio(self, wa_id="wamid-audio"):
        return MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            tipo=MensajeWhatsApp.Tipo.AUDIO,
            wa_message_id=wa_id,
            contenido_cifrado=cifrar("[audio]"),
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
        audio = self._audio()
        self._respuesta_del_agente()
        procesar_audio(audio.pk)
        enviar.assert_not_called()

    @patch("api_agente.tasks.evolution.enviar_texto", return_value="wamid")
    @patch("api_agente.tasks.agente.responder", return_value="Claro, ¿qué día le queda bien?")
    @patch("api_agente.tasks.transcripcion.transcribir", return_value="Quiero una cita")
    @patch("api_agente.tasks.evolution.descargar_audio", return_value=(b"ogg", "audio/ogg"))
    def test_audio_se_transcribe_y_entra_al_agente(
        self, descargar, transcribir, responder, enviar
    ):
        audio = self._audio()
        procesar_audio(audio.pk)

        descargar.assert_called_once_with(audio.wa_message_id, "50499999999@s.whatsapp.net")
        transcribir.assert_called_once_with(b"ogg", "audio/ogg")
        responder.assert_called_once_with(self.conversacion)
        audio.refresh_from_db()
        self.assertEqual(descifrar(audio.contenido_cifrado), "Quiero una cita")
        enviar.assert_called_once_with(self.conversacion.telefono, "Claro, ¿qué día le queda bien?")

    @patch("api_agente.tasks.evolution.enviar_texto", return_value="wamid")
    @patch("api_agente.tasks.agente.responder")
    @patch("api_agente.tasks.transcripcion.transcribir", return_value="")
    @patch("api_agente.tasks.evolution.descargar_audio", return_value=(b"ogg", "audio/ogg"))
    def test_audio_sin_voz_pide_que_escriba(self, descargar, transcribir, responder, enviar):
        audio = self._audio()
        procesar_audio(audio.pk)

        responder.assert_not_called()
        enviar.assert_called_once_with(self.conversacion.telefono, RESPUESTA_AUDIO_NO_DISPONIBLE)
        audio.refresh_from_db()
        self.assertEqual(descifrar(audio.contenido_cifrado), "[audio]")

    @patch("api_agente.tasks.evolution.enviar_texto", return_value="wamid")
    @patch("api_agente.tasks.agente.responder")
    @patch(
        "api_agente.tasks.transcripcion.transcribir",
        side_effect=transcripcion.TranscripcionError("modelo no disponible"),
    )
    @patch("api_agente.tasks.evolution.descargar_audio", return_value=(b"ogg", "audio/ogg"))
    def test_fallo_de_transcripcion_pide_que_escriba(self, descargar, transcribir, responder, enviar):
        audio = self._audio()
        procesar_audio(audio.pk)

        responder.assert_not_called()
        enviar.assert_called_once_with(self.conversacion.telefono, RESPUESTA_AUDIO_NO_DISPONIBLE)

    @patch("api_agente.tasks.evolution.descargar_audio", side_effect=evolution.EvolutionError("caído"))
    def test_fallo_de_descarga_se_propaga_para_reintentar(self, descargar):
        audio = self._audio()
        with self.assertRaises(evolution.EvolutionError):
            procesar_audio(audio.pk)

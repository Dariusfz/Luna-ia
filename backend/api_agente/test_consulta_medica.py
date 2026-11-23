from unittest.mock import patch

from django.test import SimpleTestCase

from . import agente
from .seguridad import RESPUESTA_MEDICA, es_consulta_medica
from .test_agente import AgenteBase


class DeteccionConsultaMedicaTests(SimpleTestCase):
    def test_preguntas_de_salud_se_detectan(self):
        for texto in [
            "Me duele mucho una muela, ¿qué me tomo?",
            "¿Me puede recetar algo para el dolor?",
            "Tengo sangrado en la encía",
            "¿Qué medicamento puedo tomar para la infección?",
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(es_consulta_medica(texto))

    def test_pedir_cita_no_es_consulta_medica(self):
        for texto in [
            "Me duele una muela, quiero una cita",
            "Necesito agendar una limpieza",
            "¿Qué sedes tienen?",
        ]:
            with self.subTest(texto=texto):
                self.assertFalse(es_consulta_medica(texto))


class RespuestaMedicaTests(AgenteBase):
    def test_responde_sin_llamar_al_modelo(self):
        self.mensaje_paciente("Me duele mucho una muela, ¿qué me tomo?")
        with patch("api_agente.llm.chat") as chat:
            resultado = agente.responder(self.conversacion)
        chat.assert_not_called()
        self.assertEqual(resultado, RESPUESTA_MEDICA)

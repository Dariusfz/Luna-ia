from django.test import SimpleTestCase

from .seguridad import es_afirmativo, es_confirmacion_simple


class EsAfirmativoTests(SimpleTestCase):
    def test_confirmaciones_comunes_se_aceptan(self):
        for texto in ["sí", "si", "Sí, confirmo", "si confirmo", "siii", "siiii", "Si ya graciasssss", "ok", "perfecto"]:
            with self.subTest(texto=texto):
                self.assertTrue(es_afirmativo(texto))

    def test_respuestas_no_afirmativas_no_se_aceptan(self):
        for texto in ["no", "La misma de la IA", "quiero otra fecha", ""]:
            with self.subTest(texto=texto):
                self.assertFalse(es_afirmativo(texto))


class EsConfirmacionSimpleTests(SimpleTestCase):
    def test_acepta_frases_afirmativas_sin_tilde(self):
        for texto in [
            "si", "Si", "SÍ", "sí", "sip", "siii", "claro", "correcto",
            "confirmo", "confirmado", "ok", "okay", "dale", "de acuerdo",
            "está bien", "esta bien", "asi es", "perfecto", "bien",
            "si por favor", "si, gracias", "claro que si", "muy bien",
            "por supuesto",
        ]:
            with self.subTest(texto=texto):
                self.assertTrue(es_confirmacion_simple(texto))

    def test_rechaza_negaciones_o_mezclas(self):
        for texto in [
            "no", "si no", "tal vez", "si, pero cámbiame la hora",
            "si, quiero otra fecha", "si, cancelala", "",
        ]:
            with self.subTest(texto=texto):
                self.assertFalse(es_confirmacion_simple(texto))

import json
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from users.models import Usuario

from .asistente import _llamadas_textuales, _sin_marcas

URL = "/api/analitica/asistente/"

# Texto exacto que devolvió el modelo cuando no usó la llamada estructurada.
TEXTO_DSML = (
    '<｜DSML｜ calls>\n'
    '<｜DSML｜ invoke name="consultar_registros">\n'
    '<｜DSML｜ parameter name="entidad" string="true">atenciones</｜DSML｜ parameter>\n'
    '<｜DSML｜ parameter name="filtros" string="false">'
    '{"origen": "agente_whatsapp", "fecha_desde": "2026-11-01", "fecha_hasta": "2026-11-16"}'
    '</｜DSML｜ parameter>\n'
    '</｜DSML｜ invoke>\n'
    '</｜DSML｜ calls>'
)


class LlamadasTextoTests(TestCase):
    def test_convierte_el_texto_en_llamada_estructurada(self):
        llamadas = _llamadas_textuales(TEXTO_DSML)
        self.assertEqual(len(llamadas), 1)
        funcion = llamadas[0]["function"]
        self.assertEqual(funcion["name"], "consultar_registros")
        argumentos = json.loads(funcion["arguments"])
        self.assertEqual(argumentos["entidad"], "atenciones")
        self.assertEqual(argumentos["filtros"]["origen"], "agente_whatsapp")

    def test_texto_sin_llamadas_no_produce_nada(self):
        self.assertEqual(_llamadas_textuales("Hay 9 citas."), [])

    def test_sin_marcas_quita_las_llamadas_y_las_etiquetas(self):
        self.assertEqual(_sin_marcas("Hay 9 citas. " + TEXTO_DSML), "Hay 9 citas.")


class LlamadaTextoEndToEndTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api = APIClient()
        self.api.force_login(self.admin)

    @patch("analitica.asistente.llm.chat")
    def test_ejecuta_la_llamada_escrita_como_texto(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": TEXTO_DSML},
            {"role": "assistant", "content": "El asistente de WhatsApp agendó 9 citas este mes."},
        ]
        respuesta = self.api.post(
            URL, {"pregunta": "cuantas citas hizo el asistente de whatsapp este mes"}, format="json"
        ).json()
        self.assertEqual(respuesta["respuesta"], "El asistente de WhatsApp agendó 9 citas este mes.")
        self.assertNotIn("DSML", respuesta["respuesta"])
        # La segunda llamada recibe el resultado de la consulta, no el texto crudo.
        resultado = chat.call_args.args[0][-1]
        self.assertEqual(resultado["role"], "tool")

    @patch("analitica.asistente.llm.chat")
    def test_si_la_redaccion_final_llega_vacia_se_responde_con_el_resultado(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": TEXTO_DSML},
            {"role": "assistant", "content": TEXTO_DSML},  # sin texto útil tras quitar marcas
        ]
        respuesta = self.api.post(URL, {"pregunta": "citas del agente"}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("registro(s) en atenciones", respuesta.json()["respuesta"])

    def test_respaldo_con_totales_agrupados(self):
        from .asistente import _texto_de_respaldo

        texto = _texto_de_respaldo({"total": 3, "grupos": [{"valor": "Panel", "cantidad": 2}, {"valor": "Agente WhatsApp", "cantidad": 1}]})
        self.assertIn("Total: 3.", texto)
        self.assertIn("- Agente WhatsApp: 1", texto)

    def test_respaldo_con_error(self):
        from .asistente import _texto_de_respaldo

        self.assertIn("No pude obtener", _texto_de_respaldo({"error": "x"}))

    @patch("analitica.asistente.llm.chat")
    def test_nunca_muestra_marcas_aunque_la_respuesta_final_las_traiga(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": TEXTO_DSML},
            {"role": "assistant", "content": "Respuesta. " + TEXTO_DSML},
        ]
        respuesta = self.api.post(URL, {"pregunta": "citas"}, format="json").json()
        self.assertEqual(respuesta["respuesta"], "Respuesta.")

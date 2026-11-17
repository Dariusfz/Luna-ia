from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agenda.models import Atencion
from api_agente import llm
from pacientes.models import Paciente
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

from .asistente import _argumentos_seguros, _definiciones

URL = "/api/analitica/asistente/"


def llamada(nombre, argumentos="{}", id_="call_1"):
    return {
        "id": id_,
        "type": "function",
        "function": {"name": nombre, "arguments": argumentos},
    }


class AsistenteBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        self.recep.sedes.set([self.sede_a])
        doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        doctor.sedes.set([self.sede_a, self.sede_b])
        paciente = Paciente.objects.create(
            nombres="Ana", apellidos="López", sede_origen=self.sede_a, direccion="Col. Centro"
        )
        tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        hoy = timezone.localdate()
        for sede in (self.sede_a, self.sede_b):
            Atencion.objects.create(
                sede=sede,
                doctor=doctor,
                paciente=paciente,
                tipo_trabajo=tipo,
                fecha=hoy,
                hora_inicio=time(9, 0),
                hora_fin=time(9, 20),
            )
        self.admin_api = APIClient()
        self.admin_api.force_login(self.admin)
        self.recep_api = APIClient()
        self.recep_api.force_login(self.recep)


class AsistenteTests(AsistenteBase):
    def test_requiere_sesion(self):
        respuesta = APIClient().post(URL, {"pregunta": "hola"}, format="json")
        self.assertIn(respuesta.status_code, (401, 403))

    def test_pregunta_vacia_o_muy_larga_devuelve_400(self):
        self.assertEqual(
            self.admin_api.post(URL, {"pregunta": "  "}, format="json").status_code, 400
        )
        self.assertEqual(
            self.admin_api.post(URL, {"pregunta": "x" * 501}, format="json").status_code, 400
        )

    @patch("analitica.asistente.llm.chat")
    def test_ejecuta_la_consulta_elegida_y_redacta_respuesta(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [llamada("citas_hoy")]},
            {"role": "assistant", "content": "Hoy hay 2 citas pendientes."},
        ]
        respuesta = self.admin_api.post(
            URL, {"pregunta": "¿cuántas citas hay hoy?"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["respuesta"], "Hoy hay 2 citas pendientes.")
        self.assertEqual(datos["grafica"]["tipo_grafica"], "barras")
        self.assertEqual(datos["grafica"]["total"], 2)
        # La segunda llamada al LLM no puede volver a usar herramientas.
        self.assertEqual(chat.call_args_list[1].args[1], [])

    @patch("analitica.asistente.llm.chat")
    def test_respuesta_sin_herramienta_no_trae_grafica(self, chat):
        chat.return_value = {
            "role": "assistant",
            "content": "Solo puedo ayudar con métricas de la clínica.",
        }
        datos = self.admin_api.post(URL, {"pregunta": "dime un chiste"}, format="json").json()
        self.assertIsNone(datos["grafica"])
        self.assertIn("métricas", datos["respuesta"])

    @patch("analitica.asistente.llm.chat")
    def test_recepcionista_no_ve_sedes_ajenas_aunque_el_modelo_las_pida(self, chat):
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [llamada("citas_hoy", f'{{"sede": "{self.sede_b.pk}"}}')],
            },
            {"role": "assistant", "content": "No hay citas."},
        ]
        datos = self.recep_api.post(URL, {"pregunta": "citas en norte"}, format="json").json()
        self.assertEqual(datos["grafica"]["total"], 0)

    @patch("analitica.asistente.llm.chat")
    def test_argumentos_desconocidos_se_descartan(self, chat):
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    llamada("citas_hoy", '{"sede": "1; DROP TABLE x", "columna": "dni"}')
                ],
            },
            {"role": "assistant", "content": "Lo siento, no pude consultar."},
        ]
        respuesta = self.admin_api.post(URL, {"pregunta": "algo"}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        # La sede inválida la rechaza la vista (400): no hay gráfica.
        self.assertIsNone(respuesta.json()["grafica"])

    @patch("analitica.asistente.llm.chat")
    def test_herramienta_inexistente_no_ejecuta_nada(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [llamada("borrar_todo")]},
            {"role": "assistant", "content": "No puedo hacer eso."},
        ]
        datos = self.admin_api.post(URL, {"pregunta": "borra todo"}, format="json").json()
        self.assertIsNone(datos["grafica"])

    @patch("analitica.asistente.llm.chat")
    def test_llm_caido_devuelve_503(self, chat):
        chat.side_effect = llm.LLMError("sin conexión")
        respuesta = self.admin_api.post(URL, {"pregunta": "hola"}, format="json")
        self.assertEqual(respuesta.status_code, 503)

    def test_definiciones_solo_exponen_consultas_permitidas(self):
        nombres = {d["function"]["name"] for d in _definiciones()}
        self.assertEqual(
            nombres,
            {"citas_hoy", "atendidos_mes", "por_servicio", "por_hora", "por_sede"},
        )

    def test_argumentos_seguros_filtra_claves(self):
        self.assertEqual(
            _argumentos_seguros({"sede": 3, "x": "y", "mes": None, "desde": "2026-01-01"}),
            {"sede": "3", "desde": "2026-01-01"},
        )
        self.assertEqual(_argumentos_seguros("no es dict"), {})

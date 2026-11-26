import json
from datetime import time, timedelta
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
        org = Organizacion.objects.create(nombre="ClÃ­nica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        self.recep.sedes.set([self.sede_a])
        doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="MejÃ­a")
        doctor.sedes.set([self.sede_a, self.sede_b])
        paciente = Paciente.objects.create(
            nombres="Ana", apellidos="LÃ³pez", sede_origen=self.sede_a, direccion="Col. Centro"
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
            URL, {"pregunta": "Â¿cuÃ¡ntas citas hay hoy?"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos["respuesta"], "Hoy hay 2 citas pendientes.")
        self.assertEqual(datos["grafica"]["tipo_grafica"], "barras")
        self.assertEqual(datos["grafica"]["total"], 2)
        # La segunda llamada al LLM no puede volver a usar herramientas.
        self.assertEqual(chat.call_args_list[1].args[1], [])

    @patch("analitica.asistente.llm.chat")
    def test_ejecuta_todas_las_consultas_del_turno(self, chat):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones", "filtros": {"fecha": manana}, "agrupar_por": "sede",
                    }), "call_1"),
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones", "filtros": {"fecha": manana}, "agrupar_por": "doctor",
                    }), "call_2"),
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones", "filtros": {"fecha": manana}, "limite": 50,
                    }), "call_3"),
                ],
            },
            {"role": "assistant", "content": "Mañana no hay citas agendadas."},
        ]

        datos = self.admin_api.post(
            URL,
            {"pregunta": "¿Cuántas citas hay mañana, en qué sedes y qué doctores atenderán?"},
            format="json",
        ).json()

        self.assertEqual(datos["respuesta"], "Mañana no hay citas agendadas.")
        mensajes = chat.call_args_list[1].args[0]
        resultados = [json.loads(m["content"]) for m in mensajes if m["role"] == "tool"]
        self.assertEqual(len(resultados), 3)
        self.assertTrue(all("error" not in resultado for resultado in resultados))
        self.assertEqual(resultados[0]["agrupado_por"], "sede")
        self.assertEqual(resultados[1]["agrupado_por"], "doctor")

    @patch("analitica.asistente.llm.chat")
    def test_si_el_modelo_no_redacta_se_devuelven_los_datos(self, chat):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones", "filtros": {"fecha": manana},
                    }), "call_1"),
                ],
            },
            {"role": "assistant", "content": ""},
        ]
        datos = self.admin_api.post(URL, {"pregunta": "citas de mañana"}, format="json").json()
        self.assertIn("0 registro", datos["respuesta"])

    @patch("analitica.asistente.llm.chat")
    def test_arma_grafica_de_pastel_desde_los_registros(self, chat):
        hoy = timezone.localdate().isoformat()
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones",
                        "filtros": {"fecha": hoy},
                        "agrupar_por": "sede",
                        "grafica": "pastel",
                    }), "call_1"),
                ],
            },
            {"role": "assistant", "content": "Aquí está la gráfica de pastel."},
        ]
        datos = self.admin_api.post(
            URL, {"pregunta": "gráfico de pastel de las citas por sede"}, format="json"
        ).json()

        self.assertEqual(datos["grafica"]["tipo_grafica"], "pastel")
        self.assertEqual(datos["grafica"]["total"], 2)
        self.assertEqual(len(datos["grafica"]["datos"]), 2)
        self.assertEqual(datos["grafica"]["titulo"], "Citas por Sede")
        self.assertEqual(datos["grafica"]["ejes"]["y"], "Cantidad")

    @patch("analitica.asistente.llm.chat")
    def test_respeta_el_tipo_de_grafica_pedido_en_una_vista(self, chat):
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [llamada("citas_hoy", '{"grafica": "puntos"}')],
            },
            {"role": "assistant", "content": "Gráfico de puntos."},
        ]
        datos = self.admin_api.post(
            URL, {"pregunta": "gráfico de puntos de las citas de hoy"}, format="json"
        ).json()
        self.assertEqual(datos["grafica"]["tipo_grafica"], "puntos")

    @patch("analitica.asistente.llm.chat")
    def test_registros_sin_grafica_pedida_no_dibuja(self, chat):
        hoy = timezone.localdate().isoformat()
        chat.side_effect = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    llamada("consultar_registros", json.dumps({
                        "entidad": "atenciones",
                        "filtros": {"fecha": hoy},
                        "agrupar_por": "sede",
                    }), "call_1"),
                ],
            },
            {"role": "assistant", "content": "Hay 2 citas hoy."},
        ]
        datos = self.admin_api.post(URL, {"pregunta": "citas de hoy por sede"}, format="json").json()
        self.assertIsNone(datos["grafica"])

    @patch("analitica.asistente.llm.chat")
    def test_respuesta_sin_herramienta_no_trae_grafica(self, chat):
        chat.return_value = {
            "role": "assistant",
            "content": "Solo puedo ayudar con mÃ©tricas de la clÃ­nica.",
        }
        datos = self.admin_api.post(URL, {"pregunta": "dime un chiste"}, format="json").json()
        self.assertIsNone(datos["grafica"])
        self.assertIn("mÃ©tricas", datos["respuesta"])

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
        # La sede invÃ¡lida la rechaza la vista (400): no hay grÃ¡fica.
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
        chat.side_effect = llm.LLMError("sin conexiÃ³n")
        respuesta = self.admin_api.post(URL, {"pregunta": "hola"}, format="json")
        self.assertEqual(respuesta.status_code, 503)

    def test_admin_recibe_todas_las_herramientas(self):
        nombres = {d["function"]["name"] for d in _definiciones(self.admin)}
        self.assertEqual(
            nombres,
            {"citas_hoy", "atendidos_mes", "por_servicio", "por_hora", "por_sede", "ingresos", "consultar_registros", "analisis_estrategico"},
        )

    def test_recepcionista_no_recibe_ingresos(self):
        nombres = {d["function"]["name"] for d in _definiciones(self.recep)}
        self.assertNotIn("ingresos", nombres)
        self.assertIn("por_sede", nombres)

    def test_argumentos_seguros_filtra_claves(self):
        self.assertEqual(
            _argumentos_seguros({"sede": 3, "x": "y", "mes": None, "desde": "2026-01-01"}),
            {"sede": "3", "desde": "2026-01-01"},
        )
        self.assertEqual(_argumentos_seguros("no es dict"), {})


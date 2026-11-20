from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from api_agente import llm
from users.models import Usuario

from .models import ConversacionAsistente, MensajeAsistente

URL = "/api/analitica/asistente/"
URL_LISTA = "/api/analitica/asistente/conversaciones/"


def url_detalle(pk):
    return f"/api/analitica/asistente/conversaciones/{pk}/"


class ConversacionesBase(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.otro_admin = Usuario.objects.create_user("admin2", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_otro = APIClient()
        self.api_otro.force_login(self.otro_admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def preguntar(self, api, pregunta, conversacion=None, respuesta="Respuesta."):
        datos = {"pregunta": pregunta}
        if conversacion is not None:
            datos["conversacion"] = conversacion
        with patch("analitica.asistente.llm.chat", return_value={"role": "assistant", "content": respuesta}):
            return api.post(URL, datos, format="json")


class GuardadoTests(ConversacionesBase):
    def test_primera_pregunta_crea_conversacion_con_titulo(self):
        respuesta = self.preguntar(self.api_admin, "¿cuánto dinero se ha cobrado este mes?")
        self.assertEqual(respuesta.status_code, 200)
        conversacion = ConversacionAsistente.objects.get()
        self.assertEqual(respuesta.json()["conversacion"], conversacion.pk)
        self.assertEqual(conversacion.usuario, self.admin)
        self.assertEqual(conversacion.titulo, "¿cuánto dinero se ha cobrado este mes?")
        roles = list(conversacion.mensajes.values_list("rol", flat=True))
        self.assertEqual(roles, ["usuario", "asistente"])

    def test_el_titulo_se_recorta_a_60_caracteres(self):
        self.preguntar(self.api_admin, "x" * 150)
        self.assertEqual(len(ConversacionAsistente.objects.get().titulo), 60)

    def test_seguimiento_anade_mensajes_a_la_misma_conversacion(self):
        primera = self.preguntar(self.api_admin, "¿citas de hoy?").json()
        self.preguntar(self.api_admin, "¿y mañana?", conversacion=primera["conversacion"])
        conversacion = ConversacionAsistente.objects.get()
        self.assertEqual(conversacion.mensajes.count(), 4)

    def test_el_historial_llega_al_modelo_en_el_seguimiento(self):
        primera = self.preguntar(self.api_admin, "pregunta uno", respuesta="respuesta uno").json()
        with patch("analitica.asistente.llm.chat") as chat:
            chat.return_value = {"role": "assistant", "content": "ok"}
            self.api_admin.post(
                URL,
                {"pregunta": "pregunta dos", "conversacion": primera["conversacion"]},
                format="json",
            )
        mensajes = chat.call_args.args[0]
        contenidos = [m["content"] for m in mensajes]
        self.assertIn("pregunta uno", contenidos)
        self.assertIn("respuesta uno", contenidos)
        self.assertEqual(mensajes[-1], {"role": "user", "content": "pregunta dos"})

    def test_guarda_la_grafica_de_la_consulta(self):
        with patch("analitica.asistente.llm.chat") as chat:
            chat.side_effect = [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "citas_hoy", "arguments": "{}"}}
                    ],
                },
                {"role": "assistant", "content": "Hay 0 citas."},
            ]
            self.api_admin.post(URL, {"pregunta": "citas hoy"}, format="json")
        mensaje = MensajeAsistente.objects.get(rol="asistente")
        self.assertEqual(mensaje.grafica["tipo_grafica"], "barras")

    def test_si_el_llm_falla_no_se_guarda_nada(self):
        with patch("analitica.asistente.llm.chat", side_effect=llm.LLMError("caído")):
            respuesta = self.api_admin.post(URL, {"pregunta": "hola"}, format="json")
        self.assertEqual(respuesta.status_code, 503)
        self.assertEqual(ConversacionAsistente.objects.count(), 0)
        self.assertEqual(MensajeAsistente.objects.count(), 0)


class PrivacidadTests(ConversacionesBase):
    def test_no_se_puede_continuar_la_conversacion_de_otro(self):
        ajena = self.preguntar(self.api_admin, "dato privado").json()
        respuesta = self.preguntar(self.api_otro, "hola", conversacion=ajena["conversacion"])
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(MensajeAsistente.objects.count(), 2)

    def test_el_admin_tampoco_ve_conversaciones_de_otro_admin(self):
        ajena = self.preguntar(self.api_admin, "dato privado").json()
        self.assertEqual(self.api_otro.get(URL_LISTA).json()["count"], 0)
        self.assertEqual(self.api_otro.get(url_detalle(ajena["conversacion"])).status_code, 404)

    def test_no_se_puede_borrar_la_conversacion_de_otro(self):
        ajena = self.preguntar(self.api_admin, "dato privado").json()
        respuesta = self.api_recep.delete(url_detalle(ajena["conversacion"]))
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(ConversacionAsistente.objects.filter(pk=ajena["conversacion"]).exists())

    def test_id_no_numerico_devuelve_400(self):
        respuesta = self.preguntar(self.api_admin, "hola", conversacion="abc")
        self.assertEqual(respuesta.status_code, 400)

    def test_requiere_sesion(self):
        self.assertIn(APIClient().get(URL_LISTA).status_code, (401, 403))


class ListaYDetalleTests(ConversacionesBase):
    def test_lista_solo_las_propias_mas_reciente_primero(self):
        self.preguntar(self.api_admin, "primera")
        self.preguntar(self.api_admin, "segunda")
        self.preguntar(self.api_otro, "de otro")
        datos = self.api_admin.get(URL_LISTA).json()
        self.assertEqual(datos["count"], 2)
        self.assertEqual([c["titulo"] for c in datos["results"]], ["segunda", "primera"])

    def test_detalle_trae_mensajes_en_orden(self):
        creada = self.preguntar(self.api_admin, "hola").json()
        datos = self.api_admin.get(url_detalle(creada["conversacion"])).json()
        self.assertEqual([m["rol"] for m in datos["mensajes"]], ["usuario", "asistente"])
        self.assertEqual(datos["mensajes"][0]["texto"], "hola")

    def test_borrar_elimina_la_conversacion_y_sus_mensajes(self):
        creada = self.preguntar(self.api_admin, "hola").json()
        respuesta = self.api_admin.delete(url_detalle(creada["conversacion"]))
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(ConversacionAsistente.objects.count(), 0)
        self.assertEqual(MensajeAsistente.objects.count(), 0)

from datetime import time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import Paciente
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

from .asistente import _definiciones
from .politicas import consultas_permitidas, solo_agenda_propia


class PoliticasBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.asistente = Usuario.objects.create_user("asist", password="x-Clave-2026!", rol="asistente")
        self.usuario_doctor = Usuario.objects.create_user("doc", password="x-Clave-2026!", rol="doctor")
        for usuario in (self.recep, self.asistente, self.usuario_doctor):
            usuario.sedes.set([self.sede])
        self.doctor_propio = Doctor.objects.create(
            tipo="propio", nombres="Ana", apellidos="Doc", usuario=self.usuario_doctor
        )
        self.doctor_propio.sedes.set([self.sede])
        self.otro_doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.otro_doctor.sedes.set([self.sede])
        self.paciente = Paciente.objects.create(
            nombres="Ana", apellidos="López", sede_origen=self.sede, direccion="Col. Centro"
        )
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.hoy = timezone.localdate()

    def cita(self, doctor, estado=Atencion.Estado.PENDIENTE, precio=0):
        atencion = Atencion.objects.create(
            sede=self.sede,
            doctor=doctor,
            paciente=self.paciente,
            tipo_trabajo=self.tipo,
            estado=estado,
            fecha=self.hoy,
            hora_inicio=time(9, 0),
            hora_fin=time(9, 20),
            precio_paciente=precio,
        )
        return atencion

    def api(self, usuario):
        cliente = APIClient()
        cliente.force_login(usuario)
        return cliente


class PoliticaPorRolTests(PoliticasBase):
    def test_admin_tiene_todas_las_consultas(self):
        self.assertIn("ingresos", consultas_permitidas(self.admin))
        self.assertEqual(len(consultas_permitidas(self.admin)), 6)

    def test_recepcionista_no_ve_ingresos(self):
        self.assertNotIn("ingresos", consultas_permitidas(self.recep))
        self.assertIn("por_sede", consultas_permitidas(self.recep))

    def test_asistente_solo_consultas_basicas(self):
        self.assertEqual(
            consultas_permitidas(self.asistente), {"citas_hoy", "atendidos_mes", "por_hora"}
        )

    def test_solo_el_doctor_no_admin_tiene_agenda_propia(self):
        self.assertTrue(solo_agenda_propia(self.usuario_doctor))
        self.assertFalse(solo_agenda_propia(self.admin))
        self.assertFalse(solo_agenda_propia(self.recep))

    def test_usuario_sin_rol_conocido_no_tiene_consultas(self):
        otro = Usuario.objects.create_user("otro", password="x-Clave-2026!", rol="recepcionista")
        otro.rol = "rol_inventado"
        self.assertEqual(consultas_permitidas(otro), frozenset())


class PoliticaEnApiTests(PoliticasBase):
    def test_recepcionista_recibe_403_en_ingresos(self):
        respuesta = self.api(self.recep).get("/api/analitica/ingresos/")
        self.assertEqual(respuesta.status_code, 403)

    def test_asistente_recibe_403_en_por_servicio(self):
        respuesta = self.api(self.asistente).get("/api/analitica/por-servicio/")
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(self.api(self.asistente).get("/api/analitica/citas-hoy/").status_code, 200)

    def test_doctor_solo_cuenta_su_agenda(self):
        self.cita(self.doctor_propio)
        self.cita(self.otro_doctor)
        datos = self.api(self.usuario_doctor).get("/api/analitica/citas-hoy/").json()
        self.assertEqual(datos["total"], 1)

    def test_doctor_sin_perfil_vinculado_ve_cero(self):
        sin_perfil = Usuario.objects.create_user("doc2", password="x-Clave-2026!", rol="doctor")
        sin_perfil.sedes.set([self.sede])
        self.cita(self.doctor_propio)
        datos = self.api(sin_perfil).get("/api/analitica/citas-hoy/").json()
        self.assertEqual(datos["total"], 0)

    def test_admin_ingresos_devuelve_formato_comun_con_importes(self):
        self.cita(self.otro_doctor, estado=Atencion.Estado.COMPLETADA, precio=500)
        datos = self.api(self.admin).get("/api/analitica/ingresos/").json()
        self.assertEqual(datos["tipo_grafica"], "barras")
        etiquetas = [d["etiqueta"] for d in datos["datos"]]
        self.assertEqual(
            etiquetas, ["Cobrado", "Por cobrar", "Comisión doctores", "Ganancia neta"]
        )
        self.assertEqual(datos["total"], 500.0)

    def test_ingresos_requiere_sesion(self):
        from rest_framework.test import APIClient as Cliente

        self.assertIn(Cliente().get("/api/analitica/ingresos/").status_code, (401, 403))


class AsistentePorRolTests(PoliticasBase):
    def _llamada(self, nombre):
        return {"id": "c1", "type": "function", "function": {"name": nombre, "arguments": "{}"}}

    @patch("analitica.asistente.llm.chat")
    def test_asistente_no_recibe_la_herramienta_ingresos(self, chat):
        chat.return_value = {"role": "assistant", "content": "No tienes acceso a esa información con tu rol."}
        self.api(self.asistente).post("/api/analitica/asistente/", {"pregunta": "¿cuánto se cobró?"}, format="json")
        herramientas = chat.call_args.args[1]
        nombres = {h["function"]["name"] for h in herramientas}
        self.assertNotIn("ingresos", nombres)

    @patch("analitica.asistente.llm.chat")
    def test_si_el_modelo_pide_una_consulta_prohibida_no_hay_grafica(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [self._llamada("ingresos")]},
            {"role": "assistant", "content": "No tienes acceso a esa información con tu rol."},
        ]
        datos = self.api(self.recep).post(
            "/api/analitica/asistente/", {"pregunta": "¿cuánto dinero se hizo?"}, format="json"
        ).json()
        self.assertIsNone(datos["grafica"])
        self.assertIn("No tienes acceso", datos["respuesta"])

    @patch("analitica.asistente.llm.chat")
    def test_admin_con_ingresos_recibe_grafica(self, chat):
        self.cita(self.otro_doctor, estado=Atencion.Estado.COMPLETADA, precio=800)
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [self._llamada("ingresos")]},
            {"role": "assistant", "content": "Se han cobrado L 800.00."},
        ]
        datos = self.api(self.admin).post(
            "/api/analitica/asistente/", {"pregunta": "¿cuánto dinero se ha cobrado?"}, format="json"
        ).json()
        self.assertEqual(datos["grafica"]["total"], 800.0)
        self.assertEqual(datos["respuesta"], "Se han cobrado L 800.00.")

    @patch("analitica.asistente.llm.chat")
    def test_el_prompt_lista_solo_los_modulos_del_rol(self, chat):
        chat.return_value = {"role": "assistant", "content": "ok"}
        self.api(self.asistente).post("/api/analitica/asistente/", {"pregunta": "hola"}, format="json")
        prompt = chat.call_args.args[0][0]["content"]
        self.assertIn("Agenda: citas de hoy", prompt)
        self.assertNotIn("Caja:", prompt)
        self.assertIn("No tienes acceso a esa información", prompt)

    def test_definiciones_del_doctor(self):
        nombres = {d["function"]["name"] for d in _definiciones(self.usuario_doctor)}
        self.assertEqual(nombres, {"citas_hoy", "atendidos_mes", "por_servicio", "por_hora", "consultar_registros", "analisis_estrategico"})

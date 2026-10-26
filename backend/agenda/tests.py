from datetime import date, time

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from sedes.models import LugarExterno, Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario

from .models import Atencion, JornadaExterna


class AlcancePorSedeTests(TestCase):
    """Un recepcionista solo ve y registra en sus sedes. El admin ve todo."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep_a = Usuario.objects.create_user("recep_a", password="x-Clave-2026!", rol="recepcionista")
        cls.recep_a.sedes.set([cls.sede_a])

        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente_a = Paciente.objects.create(nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.paciente_b = Paciente.objects.create(nombres="Beto", apellidos="B", sede_origen=cls.sede_b)
        cls.paciente_visitante = Paciente.objects.create(nombres="Carla", apellidos="C")

        cls.atencion_a = Atencion.objects.create(
            sede=cls.sede_a, doctor=cls.doctor, paciente=cls.paciente_a, tipo_trabajo=cls.tipo,
            fecha=date(2026, 10, 20), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=500,
        )
        cls.atencion_b = Atencion.objects.create(
            sede=cls.sede_b, doctor=cls.doctor, paciente=cls.paciente_visitante, tipo_trabajo=cls.tipo,
            fecha=date(2026, 10, 21), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=500,
        )

    def setUp(self):
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep_a)
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)

    def test_recepcionista_solo_ve_atenciones_de_su_sede(self):
        ids = [a["id"] for a in self.api_recep.get("/api/atenciones/").json()["results"]]
        self.assertEqual(ids, [self.atencion_a.pk])

    def test_admin_ve_todas_las_sedes(self):
        ids = {a["id"] for a in self.api_admin.get("/api/atenciones/").json()["results"]}
        self.assertEqual(ids, {self.atencion_a.pk, self.atencion_b.pk})

    def test_no_puede_registrar_atencion_en_otra_sede(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_b.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sede", respuesta.json())

    def test_puede_registrar_atencion_en_su_sede(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
                "observaciones": "Sin novedades",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_no_puede_atender_paciente_no_visible(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_b.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paciente", respuesta.json())

    def test_tipo_trabajo_es_obligatorio(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "fecha": "2026-10-22", "hora_inicio": "09:00", "hora_fin": "10:00",
                "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipo_trabajo", respuesta.json())

    def test_hora_fin_debe_ser_posterior(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "10:00", "hora_fin": "09:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", respuesta.json())

    def test_pacientes_visibles_solo_por_sede(self):
        ids = {p["id"] for p in self.api_recep.get("/api/pacientes/").json()["results"]}
        # Ana (origen A). Beto no (origen B, sin atención en A). Carla no (solo atendida en B).
        self.assertEqual(ids, {self.paciente_a.pk})

    def test_paciente_atendido_en_sede_propia_es_visible(self):
        Atencion.objects.create(
            sede=self.sede_a, doctor=self.doctor, paciente=self.paciente_visitante,
            tipo_trabajo=self.tipo, fecha=date(2026, 10, 22),
            hora_inicio=time(9), hora_fin=time(10), honorario_doctor=200,
        )
        ids = {p["id"] for p in self.api_recep.get("/api/pacientes/").json()["results"]}
        self.assertIn(self.paciente_visitante.pk, ids)

    def test_sedes_listadas_segun_usuario(self):
        ids = [s["id"] for s in self.api_recep.get("/api/sedes/").json()["results"]]
        self.assertEqual(ids, [self.sede_a.pk])

    def test_no_se_puede_borrar_atencion(self):
        respuesta = self.api_admin.delete(f"/api/atenciones/{self.atencion_a.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class JornadasExternasTests(TestCase):
    """Los trabajos fuera de la clínica son solo del admin y no tienen datos de pacientes."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        cls.recep.sedes.set([cls.sede_a])
        cls.doctora = Doctor.objects.create(tipo="propio", nombres="Marta", apellidos="Ruiz")
        cls.lugar = LugarExterno.objects.create(nombre="Hospital X")
        cls.tipo = TipoTrabajo.objects.create(nombre="Extracción")

    def test_solo_admin_accede_a_jornadas(self):
        recep = APIClient()
        recep.force_login(self.recep)
        self.assertEqual(recep.get("/api/jornadas-externas/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_registra_jornada_sin_datos_de_paciente(self):
        admin = APIClient()
        admin.force_login(self.admin)
        respuesta = admin.post(
            "/api/jornadas-externas/",
            {
                "doctor": self.doctora.pk, "lugar": self.lugar.pk, "tipo_trabajo": self.tipo.pk,
                "fecha": "2026-10-22", "hora_inicio": "08:00", "hora_fin": "12:00",
                "monto_cobrado": "1500", "observaciones": "Cirugía de tercer molar",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("paciente", respuesta.json())
        self.assertEqual(JornadaExterna.objects.count(), 1)

    def test_lugares_externos_disponibles_para_el_admin(self):
        admin = APIClient()
        admin.force_login(self.admin)
        nombres = [l["nombre"] for l in admin.get("/api/lugares-externos/").json()["results"]]
        self.assertEqual(nombres, ["Hospital X"])


class AccesoAnonimoTests(TestCase):
    def test_api_clinica_requiere_sesion(self):
        anonimo = APIClient()
        for ruta in ["/api/atenciones/", "/api/pacientes/", "/api/jornadas-externas/", "/api/sedes/"]:
            with self.subTest(ruta=ruta):
                self.assertIn(
                    anonimo.get(ruta).status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                )

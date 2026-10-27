from datetime import date, time

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from sedes.models import Feriado, HorarioSede, Organizacion, Sede
from users.models import Usuario


class HorariosSedeApiTests(TestCase):
    """Catálogo de horarios y feriados: lectura para todos, cambios solo admin."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.otra_sede = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user(
            "admin", password="x-Clave-2026!", rol="admin"
        )
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede])

    def setUp(self):
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def test_admin_crea_turno(self):
        respuesta = self.api_admin.post(
            "/api/horarios-sede/",
            {
                "sede": self.sede.pk,
                "dia_semana": 0,
                "hora_apertura": "08:30",
                "hora_cierre": "11:30",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["dia_nombre"], "Lunes")
        self.assertEqual(HorarioSede.objects.count(), 1)

    def test_recepcionista_lee_solo_sus_sedes(self):
        HorarioSede.objects.create(
            sede=self.sede, dia_semana=0,
            hora_apertura=time(8, 30), hora_cierre=time(11, 30),
        )
        HorarioSede.objects.create(
            sede=self.otra_sede, dia_semana=0,
            hora_apertura=time(9), hora_cierre=time(12),
        )
        respuesta = self.api_recep.get("/api/horarios-sede/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.json()), 1)
        self.assertEqual(respuesta.json()[0]["sede"], self.sede.pk)

    def test_recepcionista_no_puede_crear_turno(self):
        respuesta = self.api_recep.post(
            "/api/horarios-sede/",
            {
                "sede": self.sede.pk,
                "dia_semana": 0,
                "hora_apertura": "08:30",
                "hora_cierre": "11:30",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_rechaza_turnos_solapados(self):
        HorarioSede.objects.create(
            sede=self.sede, dia_semana=2,
            hora_apertura=time(9), hora_cierre=time(12),
        )
        respuesta = self.api_admin.post(
            "/api/horarios-sede/",
            {
                "sede": self.sede.pk,
                "dia_semana": 2,
                "hora_apertura": "11:00",
                "hora_cierre": "13:00",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_apertura", respuesta.json())

    def test_rechaza_cierre_anterior_a_apertura(self):
        respuesta = self.api_admin.post(
            "/api/horarios-sede/",
            {
                "sede": self.sede.pk,
                "dia_semana": 1,
                "hora_apertura": "12:00",
                "hora_cierre": "09:00",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_cierre", respuesta.json())

    def test_feriado_completo_ignora_horas(self):
        respuesta = self.api_admin.post(
            "/api/feriados/",
            {
                "sede": self.sede.pk,
                "fecha": "2027-01-05",
                "nombre": "Día festivo",
                "todo_el_dia": True,
                "hora_inicio": "09:00",
                "hora_fin": "12:00",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(respuesta.json()["hora_inicio"])
        self.assertIsNone(respuesta.json()["hora_fin"])

    def test_feriado_medio_dia_exige_horas(self):
        respuesta = self.api_admin.post(
            "/api/feriados/",
            {
                "sede": self.sede.pk,
                "fecha": "2027-01-06",
                "nombre": "Capacitación",
                "todo_el_dia": False,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_feriado_medio_dia_valido(self):
        respuesta = self.api_admin.post(
            "/api/feriados/",
            {
                "sede": self.sede.pk,
                "fecha": "2027-01-07",
                "nombre": "Capacitación",
                "todo_el_dia": False,
                "hora_inicio": "09:00",
                "hora_fin": "12:00",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_recepcionista_ve_feriados_globales_y_de_su_sede(self):
        Feriado.objects.create(fecha=date(2027, 1, 10), nombre="Nacional")
        Feriado.objects.create(sede=self.sede, fecha=date(2027, 1, 11), nombre="Local")
        Feriado.objects.create(sede=self.otra_sede, fecha=date(2027, 1, 12), nombre="Ajeno")
        respuesta = self.api_recep.get("/api/feriados/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        nombres = {feriado["nombre"] for feriado in respuesta.json()}
        self.assertEqual(nombres, {"Nacional", "Local"})

    def test_filtro_por_sede_incluye_globales(self):
        Feriado.objects.create(fecha=date(2027, 1, 10), nombre="Nacional")
        Feriado.objects.create(sede=self.sede, fecha=date(2027, 1, 11), nombre="Local")
        Feriado.objects.create(sede=self.otra_sede, fecha=date(2027, 1, 12), nombre="Ajeno")
        respuesta = self.api_admin.get("/api/feriados/", {"sede": self.sede.pk})
        nombres = {feriado["nombre"] for feriado in respuesta.json()}
        self.assertEqual(nombres, {"Nacional", "Local"})

"""Auditoría de permisos por endpoint: sesión obligatoria y rol mínimo (plan §6)."""

from axes.utils import reset
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from sedes.models import Organizacion, Sede

from .models import Usuario

PASSWORD = "Clave-Segura-2026!"

RUTAS_PRIVADAS = [
    "/api/pacientes/",
    "/api/historias-clinicas/",
    "/api/odontogramas/",
    "/api/atenciones/",
    "/api/lista-espera/",
    "/api/doctores/",
    "/api/sedes/",
    "/api/horarios-sede/",
    "/api/feriados/",
    "/api/tipos-trabajo/",
    "/api/especialidades/",
    "/api/pagos/",
    "/api/pagos-doctores/",
    "/api/usuarios/",
    "/api/invitaciones/",
    "/api/jornadas-externas/",
    "/api/lugares-externos/",
    "/api/caja/resumen/",
    "/api/analitica/citas-hoy/",
    "/api/agente/sedes/",
]


class PermisosEndpointsTests(TestCase):
    def setUp(self):
        reset()
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        self.admin = Usuario.objects.create_user(
            "admin", email="admin@clinica.test", password=PASSWORD, rol=Usuario.Rol.ADMIN
        )
        self.recep = Usuario.objects.create_user(
            "recep", email="recep@clinica.test", password=PASSWORD, rol=Usuario.Rol.RECEPCIONISTA
        )
        self.recep.sedes.set([self.sede])
        self.doctor = Usuario.objects.create_user(
            "doctor", email="doctor@clinica.test", password=PASSWORD, rol=Usuario.Rol.DOCTOR
        )
        self.doctor.sedes.set([self.sede])
        self.anonimo = APIClient()
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)
        self.api_doctor = APIClient()
        self.api_doctor.force_login(self.doctor)

    def tearDown(self):
        reset()

    def test_endpoints_privados_exigen_sesion(self):
        for ruta in RUTAS_PRIVADAS:
            with self.subTest(ruta=ruta):
                respuesta = self.anonimo.get(ruta)
                self.assertIn(
                    respuesta.status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                )

    def test_escrituras_sensibles_exigen_sesion(self):
        casos = [
            ("post", "/api/atenciones/"),
            ("post", "/api/historias-clinicas/"),
            ("post", "/api/invitaciones/"),
            ("post", "/api/pagos/"),
            ("patch", f"/api/sedes/{self.sede.pk}/"),
        ]
        for metodo, ruta in casos:
            with self.subTest(metodo=metodo, ruta=ruta):
                respuesta = getattr(self.anonimo, metodo)(ruta, {}, format="json")
                self.assertIn(
                    respuesta.status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                )

    def test_recepcionista_no_entra_a_modulos_de_admin(self):
        for ruta in ("/api/usuarios/", "/api/invitaciones/", "/api/pagos/", "/api/pagos-doctores/"):
            with self.subTest(ruta=ruta):
                self.assertEqual(
                    self.api_recep.get(ruta).status_code, status.HTTP_403_FORBIDDEN
                )
        self.assertEqual(
            self.api_recep.patch(f"/api/sedes/{self.sede.pk}/", {"nombre": "X"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_recepcionista_si_usa_agenda_y_pacientes(self):
        self.assertEqual(self.api_recep.get("/api/pacientes/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.api_recep.get("/api/atenciones/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.api_recep.get("/api/historias-clinicas/").status_code, status.HTTP_200_OK
        )

    def test_doctor_no_modifica_catalogos(self):
        self.assertEqual(
            self.api_doctor.patch(
                "/api/tipos-trabajo/1/", {"nombre": "X"}, format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.api_doctor.post(
                "/api/especialidades/", {"nombre": "X"}, format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.api_doctor.get("/api/atenciones/").status_code, status.HTTP_200_OK)

    def test_endpoints_publicos_controlados(self):
        self.assertEqual(
            self.anonimo.post(
                "/api/auth/login/", {"username": "nadie", "password": "x"}, format="json"
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.anonimo.post(
                "/api/auth/aceptar-invitacion/",
                {"token": "invalido", "username": "x", "password": "x", "nombres": "A", "apellidos": "B"},
                format="json",
            ).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(self.anonimo.get("/api/auth/csrf/").status_code, status.HTTP_200_OK)

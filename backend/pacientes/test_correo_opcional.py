from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from sedes.models import Organizacion, Sede
from users.models import Usuario


class PacienteCorreoOpcionalTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api = APIClient()
        self.api.force_login(admin)

    def test_paciente_se_crea_sin_correo(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Rosa", "apellidos": "Mejía", "sede_origen": self.sede.pk, "direccion": "Col. Centro", "email": ""},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_paciente_se_crea_sin_el_campo_correo(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Rosa", "apellidos": "Mejía", "sede_origen": self.sede.pk, "direccion": "Col. Centro"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

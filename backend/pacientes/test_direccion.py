from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from sedes.models import Organizacion, Sede
from users.models import Usuario


class DireccionObligatoriaTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api = APIClient()
        self.api.force_login(admin)

    def test_paciente_sin_direccion_se_rechaza(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Rosa", "apellidos": "Mejía", "sede_origen": self.sede.pk, "direccion": ""},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("direccion", respuesta.json())

    def test_paciente_con_direccion_se_acepta(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Rosa", "apellidos": "Mejía", "sede_origen": self.sede.pk, "direccion": "Col. Kennedy"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)


class ListadoPersonalTests(TestCase):
    def test_listado_incluye_sedes_de_cada_usuario(self):
        org = Organizacion.objects.create(nombre="Clínica")
        sede = Sede.objects.create(nombre="Centro", organizacion=org)
        admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        recep.sedes.set([sede])
        api = APIClient()
        api.force_login(admin)
        datos = {u["username"]: u for u in api.get("/api/usuarios/").json()["results"]}
        self.assertEqual(datos["recep"]["sedes"], [{"id": sede.pk, "nombre": "Centro"}])
        self.assertEqual(datos["admin"]["sedes"], [])

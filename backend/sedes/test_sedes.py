from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from users.models import Usuario

from .models import Sede


class SedesAPITests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def test_admin_crea_sede_con_telefono_normalizado(self):
        respuesta = self.api_admin.post(
            "/api/sedes/",
            {"nombre": "Sede Centro", "direccion": "Col. Centro", "telefono": "9999-9999"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["telefono"], "+504 9999-9999")
        self.assertEqual(Sede.objects.get(nombre="Sede Centro").organizacion.nombre, "Clínica")

    def test_telefono_con_mas_digitos_se_rechaza(self):
        respuesta = self.api_admin.post(
            "/api/sedes/", {"nombre": "X", "telefono": "9999-99999"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("telefono", respuesta.json())

    def test_telefono_con_menos_digitos_se_rechaza(self):
        respuesta = self.api_admin.post(
            "/api/sedes/", {"nombre": "X", "telefono": "9999-999"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recepcionista_no_puede_crear_sedes(self):
        respuesta = self.api_recep.post("/api/sedes/", {"nombre": "X"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_edita_sede(self):
        sede = Sede.objects.create(nombre="Vieja", organizacion_id=self._org().pk)
        respuesta = self.api_admin.patch(
            f"/api/sedes/{sede.pk}/", {"nombre": "Nueva"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        sede.refresh_from_db()
        self.assertEqual(sede.nombre, "Nueva")

    def test_no_se_borran_sedes(self):
        sede = Sede.objects.create(nombre="Sede", organizacion_id=self._org().pk)
        respuesta = self.api_admin.delete(f"/api/sedes/{sede.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_recepcionista_solo_ve_sus_sedes_activas(self):
        org = self._org()
        propia = Sede.objects.create(nombre="Propia", organizacion_id=org.pk)
        Sede.objects.create(nombre="Ajena", organizacion_id=org.pk)
        self.recep.sedes.set([propia])
        ids = [s["id"] for s in self.api_recep.get("/api/sedes/").json()["results"]]
        self.assertEqual(ids, [propia.pk])

    def _org(self):
        from sedes.models import Organizacion

        return Organizacion.objects.get_or_create(nombre="Clínica")[0]


class TelefonoPacienteTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api = APIClient()
        self.api.force_login(self.admin)
        from sedes.models import Organizacion

        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)

    def test_paciente_guarda_telefono_en_formato_504(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Ana", "apellidos": "López", "sede_origen": self.sede.pk, "direccion": "Col. Centro", "telefono": "99999999"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Paciente.objects.get(pk=respuesta.json()["id"]).telefono, "+504 9999-9999")

    def test_paciente_telefono_invalido_se_rechaza(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "Ana", "apellidos": "López", "sede_origen": self.sede.pk, "direccion": "Col. Centro", "telefono": "12345"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("telefono", respuesta.json())

    def test_paciente_sin_sede_se_rechaza(self):
        respuesta = self.api.post(
            "/api/pacientes/", {"nombres": "Ana", "apellidos": "López"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import Paciente
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede

from .models import Doctor, Usuario


class DoctoresAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep_a = Usuario.objects.create_user("recep_a", password="x-Clave-2026!", rol="recepcionista")
        cls.recep_a.sedes.set([cls.sede_a])
        cls.doc_a = Doctor.objects.create(
            tipo="contratado", nombres="Luis", apellidos="Mejía", observaciones="Tarifa acordada"
        )
        cls.doc_a.sedes.set([cls.sede_a])
        cls.doc_b = Doctor.objects.create(tipo="contratado", nombres="Rosa", apellidos="Paz")
        cls.doc_b.sedes.set([cls.sede_b])

    def setUp(self):
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep_a)

    # --- Escritura solo admin ---------------------------------------------

    def test_admin_crea_doctor_contratado_con_sedes(self):
        respuesta = self.api_admin.post(
            "/api/doctores/",
            {
                "tipo": "contratado", "nombres": "Ana", "apellidos": "López",
                "sedes": [self.sede_a.pk, self.sede_b.pk],
                "observaciones": "Contrato por sesión",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        nuevo = Doctor.objects.get(nombres="Ana")
        self.assertEqual(nuevo.sedes.count(), 2)

    def test_recepcionista_no_puede_crear_doctores(self):
        respuesta = self.api_recep.post(
            "/api/doctores/",
            {"tipo": "contratado", "nombres": "X", "apellidos": "Y", "sedes": [self.sede_a.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_recepcionista_no_puede_editar_doctores(self):
        respuesta = self.api_recep.patch(
            f"/api/doctores/{self.doc_a.pk}/", {"telefono": "+504 9999-0000"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_se_pueden_borrar_doctores(self):
        respuesta = self.api_admin.delete(f"/api/doctores/{self.doc_a.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Doctor.objects.filter(pk=self.doc_a.pk).exists())

    def test_contratado_no_puede_tener_cuenta(self):
        usuario = Usuario.objects.create_user("otro", password="x-Clave-2026!", rol="doctor")
        respuesta = self.api_admin.post(
            "/api/doctores/",
            {
                "tipo": "contratado", "nombres": "Z", "apellidos": "Z",
                "usuario": usuario.pk, "sedes": [self.sede_a.pk],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("usuario", respuesta.json())

    def test_admin_desactiva_doctor(self):
        respuesta = self.api_admin.patch(
            f"/api/doctores/{self.doc_a.pk}/", {"activo": False}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.doc_a.refresh_from_db()
        self.assertFalse(self.doc_a.activo)

    # --- Lectura por sede ----------------------------------------------------

    def test_recepcionista_solo_ve_doctores_de_su_sede(self):
        ids = {d["id"] for d in self.api_recep.get("/api/doctores/").json()["results"]}
        self.assertEqual(ids, {self.doc_a.pk})

    def test_admin_ve_todos_los_doctores(self):
        ids = {d["id"] for d in self.api_admin.get("/api/doctores/").json()["results"]}
        self.assertEqual(ids, {self.doc_a.pk, self.doc_b.pk})

    def test_no_admin_no_ve_campos_administrativos(self):
        datos = self.api_recep.get(f"/api/doctores/{self.doc_a.pk}/").json()
        self.assertNotIn("observaciones", datos)
        self.assertNotIn("usuario", datos)
        admin = self.api_admin.get(f"/api/doctores/{self.doc_a.pk}/").json()
        self.assertIn("observaciones", admin)

    # --- Reglas de atención -------------------------------------------------

    def _datos_atencion(self, doctor, sede):
        paciente = Paciente.objects.create(direccion="Col. Centro", nombres="P", apellidos="Q", sede_origen=self.sede_a)
        tipo = TipoTrabajo.objects.get_or_create(nombre="Limpieza")[0]
        return {
            "sede": sede.pk, "doctor": doctor.pk, "paciente": paciente.pk,
            "tipo_trabajo": tipo.pk,
            "fecha": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
        }

    def test_doctor_no_puede_atender_en_sede_no_asignada(self):
        respuesta = self.api_admin.post(
            "/api/atenciones/", self._datos_atencion(self.doc_a, self.sede_b), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())

    def test_doctor_desactivado_no_puede_atender(self):
        self.doc_a.activo = False
        self.doc_a.save(update_fields=["activo"])
        respuesta = self.api_recep.post(
            "/api/atenciones/", self._datos_atencion(self.doc_a, self.sede_a), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_doctor_asignado_si_puede_atender(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/", self._datos_atencion(self.doc_a, self.sede_a), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Atencion.objects.filter(doctor=self.doc_a).count(), 1)


class TiposTrabajoAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        cls.activo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.inactivo = TipoTrabajo.objects.create(nombre="Retirado", activo=False)

    def setUp(self):
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def test_admin_crea_tipo_de_trabajo(self):
        respuesta = self.api_admin.post(
            "/api/tipos-trabajo/", {"nombre": "Ortodoncia", "descripcion": "Brackets"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_recepcionista_no_puede_crear_tipos(self):
        respuesta = self.api_recep.post("/api/tipos-trabajo/", {"nombre": "X"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_recepcionista_solo_ve_tipos_activos(self):
        nombres = [t["nombre"] for t in self.api_recep.get("/api/tipos-trabajo/").json()["results"]]
        self.assertEqual(nombres, ["Limpieza"])

    def test_admin_ve_tipos_inactivos_y_puede_desactivar(self):
        ids = {t["id"] for t in self.api_admin.get("/api/tipos-trabajo/").json()["results"]}
        self.assertIn(self.inactivo.pk, ids)
        respuesta = self.api_admin.patch(
            f"/api/tipos-trabajo/{self.activo.pk}/", {"activo": False}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_no_se_borran_tipos(self):
        respuesta = self.api_admin.delete(f"/api/tipos-trabajo/{self.activo.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

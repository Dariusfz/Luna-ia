from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

from .models import Atencion


class AtencionesGestionTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.sede_a])
        self.luis = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.luis.sedes.set([self.sede_a])
        self.rosa = Doctor.objects.create(tipo="contratado", nombres="Rosa", apellidos="Paz")
        self.rosa.sedes.set([self.sede_b])
        self.paciente = Paciente.objects.create(
            nombres="Ana", apellidos="López", sede_origen=self.sede_a, direccion="Col. Centro"
        )
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.recep_api = APIClient()
        self.recep_api.force_login(self.recep)
        self.admin_api = APIClient()
        self.admin_api.force_login(self.admin)

    def _datos(self, **extra):
        datos = {
            "sede": self.sede_a.pk,
            "doctor": self.luis.pk,
            "paciente": self.paciente.pk,
            "tipo_trabajo": self.tipo.pk,
            "fecha": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
            "honorario_doctor": "300",
        }
        datos.update(extra)
        return datos

    def test_registra_atencion_con_nombres_legibles(self):
        respuesta = self.recep_api.post("/api/atenciones/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        datos = respuesta.json()
        self.assertEqual(datos["sede_nombre"], "Centro")
        self.assertEqual(datos["doctor_nombre"], "Luis Mejía")
        self.assertEqual(datos["doctor_tipo"], "contratado")
        self.assertEqual(datos["paciente_nombre"], "Ana López")
        self.assertEqual(datos["tipo_trabajo_nombre"], "Limpieza")
        self.assertEqual(datos["estado"], "pendiente")

    def test_honorario_negativo_se_rechaza(self):
        respuesta = self.recep_api.post("/api/atenciones/", self._datos(honorario_doctor="-5"), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("honorario_doctor", respuesta.json())

    def test_honorario_mayor_al_limite_se_rechaza(self):
        respuesta = self.recep_api.post(
            "/api/atenciones/", self._datos(honorario_doctor="500000.01"), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("honorario_doctor", respuesta.json())

    def test_paciente_inactivo_no_se_puede_atender(self):
        self.paciente.activo = False
        self.paciente.save()
        respuesta = self.recep_api.post("/api/atenciones/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paciente", respuesta.json())

    def test_tipo_inactivo_no_se_puede_usar(self):
        self.tipo.activo = False
        self.tipo.save()
        respuesta = self.recep_api.post("/api/atenciones/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipo_trabajo", respuesta.json())

    def test_doctor_sin_esa_sede_se_rechaza(self):
        respuesta = self.admin_api.post(
            "/api/atenciones/", self._datos(doctor=self.rosa.pk), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())

    def test_edita_atencion(self):
        atencion = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 22), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=300,
        )
        respuesta = self.recep_api.patch(
            f"/api/atenciones/{atencion.pk}/", {"honorario_doctor": "350", "observaciones": "Ajuste"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        atencion.refresh_from_db()
        self.assertEqual(str(atencion.honorario_doctor), "350.00")
        self.assertEqual(atencion.observaciones, "Ajuste")

    def test_filtra_por_sede_doctor_y_fechas(self):
        otra = Atencion.objects.create(
            sede=self.sede_b, doctor=self.rosa, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 25), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=200,
        )
        mia = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 20), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=300,
        )

        def ids(url):
            return {a["id"] for a in self.admin_api.get(url).json()["results"]}

        self.assertEqual(ids(f"/api/atenciones/?sede={self.sede_b.pk}"), {otra.pk})
        self.assertEqual(ids(f"/api/atenciones/?doctor={self.luis.pk}"), {mia.pk})
        self.assertEqual(ids("/api/atenciones/?desde=2026-10-21"), {otra.pk})
        self.assertEqual(ids("/api/atenciones/?hasta=2026-10-21"), {mia.pk})

    def test_no_permite_completar_una_cita_futura(self):
        futura = timezone.localdate() + timedelta(days=1)
        atencion = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=futura, hora_inicio=time(9), hora_fin=time(10), honorario_doctor=0,
        )
        respuesta = self.recep_api.patch(
            f"/api/atenciones/{atencion.pk}/", {"estado": "completada"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", respuesta.json())

    def test_filtra_por_uno_o_varios_estados(self):
        pendiente = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 26), hora_inicio=time(9), hora_fin=time(10),
            honorario_doctor=0, estado="pendiente",
        )
        completada = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 20), hora_inicio=time(9), hora_fin=time(10),
            honorario_doctor=300, estado="completada",
        )
        cancelada = Atencion.objects.create(
            sede=self.sede_a, doctor=self.luis, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=date(2026, 10, 27), hora_inicio=time(9), hora_fin=time(10),
            honorario_doctor=0, estado="cancelada",
        )

        def ids(url):
            return {a["id"] for a in self.admin_api.get(url).json()["results"]}

        self.assertEqual(ids("/api/atenciones/?estado=pendiente"), {pendiente.pk})
        self.assertEqual(
            ids("/api/atenciones/?estado=pendiente,completada"),
            {pendiente.pk, completada.pk},
        )
        self.assertNotIn(cancelada.pk, ids("/api/atenciones/?estado=pendiente,completada"))
        self.assertEqual(ids("/api/atenciones/?estado=inventado"), set())

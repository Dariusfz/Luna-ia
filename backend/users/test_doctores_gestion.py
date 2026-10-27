from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from servicios.models import Especialidad, TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario


class DoctoresGestionTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.ortodoncia = Especialidad.objects.create(nombre="Ortodoncia")
        self.endodoncia = Especialidad.objects.create(nombre="Endodoncia")
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.sede_a])
        self.ana = Doctor.objects.create(tipo="propio", nombres="Ana", apellidos="López")
        self.ana.especialidades.set([self.ortodoncia])
        self.ana.sedes.set([self.sede_a])
        self.luis = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.luis.sedes.set([self.sede_b])
        self.api = APIClient()
        self.api.force_login(self.admin)

    def _ids(self, url, cliente=None):
        cliente = cliente or self.api
        return {d["id"] for d in cliente.get(url).json()["results"]}

    def test_filtra_por_tipo(self):
        self.assertEqual(self._ids("/api/doctores/?tipo=contratado"), {self.luis.pk})

    def test_filtra_por_texto_y_especialidad(self):
        self.assertEqual(self._ids("/api/doctores/?q=ortodon"), {self.ana.pk})
        self.assertEqual(self._ids("/api/doctores/?q=mej"), {self.luis.pk})

    def test_filtra_por_sede_y_estado(self):
        self.luis.activo = False
        self.luis.save()
        self.assertEqual(self._ids("/api/doctores/?sede=%d" % self.sede_a.pk), {self.ana.pk})
        self.assertEqual(self._ids("/api/doctores/?activo=false"), {self.luis.pk})

    def test_especialidades_se_eligen_del_catalogo_y_muestran_nombres(self):
        respuesta = self.api.patch(
            f"/api/doctores/{self.luis.pk}/",
            {"especialidades": [self.endodoncia.pk, self.ortodoncia.pk], "sedes": [self.sede_a.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(respuesta.json()["especialidades_nombres"]),
            {"Endodoncia", "Ortodoncia"},
        )
        self.luis.refresh_from_db()
        self.assertEqual(
            set(self.luis.especialidades.values_list("nombre", flat=True)),
            {"Endodoncia", "Ortodoncia"},
        )
        self.assertEqual(list(self.luis.sedes.all()), [self.sede_a])

    def test_puede_crear_doctor_con_varias_especialidades(self):
        respuesta = self.api.post(
            "/api/doctores/",
            {
                "tipo": "contratado",
                "nombres": "Carla",
                "apellidos": "Núñez",
                "especialidades": [self.ortodoncia.pk, self.endodoncia.pk],
                "sedes": [self.sede_a.pk],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(respuesta.json()["especialidades"]), 2)

    def test_especialidad_inactiva_no_se_puede_asignar(self):
        self.endodoncia.activo = False
        self.endodoncia.save()
        respuesta = self.api.patch(
            f"/api/doctores/{self.luis.pk}/", {"especialidades": [self.endodoncia.pk]}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("especialidades", respuesta.json())

    def test_desactiva_doctor(self):
        self.api.patch(f"/api/doctores/{self.ana.pk}/", {"activo": False}, format="json")
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.activo)

    def test_telefono_de_doctor_se_normaliza(self):
        respuesta = self.api.patch(
            f"/api/doctores/{self.ana.pk}/", {"telefono": "88887777"}, format="json"
        )
        self.assertEqual(respuesta.json()["telefono"], "+504 8888-7777")

    def test_recepcionista_solo_ve_doctores_de_su_sede(self):
        recep_api = APIClient()
        recep_api.force_login(self.recep)
        self.assertEqual(self._ids("/api/doctores/?activo=todos", recep_api), {self.ana.pk})


class EspecialidadesTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.ortodoncia = Especialidad.objects.create(nombre="Ortodoncia")
        self.retirada = Especialidad.objects.create(nombre="Retirada", activo=False)
        self.api = APIClient()
        self.api.force_login(self.admin)

    def test_admin_crea_especialidad(self):
        respuesta = self.api.post("/api/especialidades/", {"nombre": "Cirugía oral"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_recepcionista_no_crea_especialidades(self):
        recep_api = APIClient()
        recep_api.force_login(self.recep)
        respuesta = recep_api.post("/api/especialidades/", {"nombre": "X"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_recepcionista_solo_ve_activas(self):
        recep_api = APIClient()
        recep_api.force_login(self.recep)
        nombres = [e["nombre"] for e in recep_api.get("/api/especialidades/").json()["results"]]
        self.assertEqual(nombres, ["Ortodoncia"])

    def test_admin_desactiva_especialidad(self):
        self.api.patch(f"/api/especialidades/{self.ortodoncia.pk}/", {"activo": False}, format="json")
        self.ortodoncia.refresh_from_db()
        self.assertFalse(self.ortodoncia.activo)

    def test_nombre_duplicado_muestra_error_en_campo(self):
        respuesta = self.api.post("/api/especialidades/", {"nombre": "Ortodoncia"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", respuesta.json())


class TiposTrabajoGestionTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.limpieza = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.retirado = TipoTrabajo.objects.create(nombre="Retirado", activo=False)
        self.api = APIClient()
        self.api.force_login(self.admin)

    def test_admin_edita_y_desactiva_tipo(self):
        respuesta = self.api.patch(
            f"/api/tipos-trabajo/{self.limpieza.pk}/",
            {"descripcion": "Profilaxis", "activo": False},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.limpieza.refresh_from_db()
        self.assertFalse(self.limpieza.activo)

    def test_precio_se_guarda_y_se_muestra(self):
        respuesta = self.api.post(
            "/api/tipos-trabajo/", {"nombre": "Extracción", "precio": "850.50"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["precio"], "850.50")

    def test_precio_negativo_se_rechaza(self):
        respuesta = self.api.post(
            "/api/tipos-trabajo/", {"nombre": "Negativo", "precio": "-10"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("precio", respuesta.json())

    def test_filtra_tipos_por_estado(self):
        ids = {t["id"] for t in self.api.get("/api/tipos-trabajo/?activo=false").json()["results"]}
        self.assertEqual(ids, {self.retirado.pk})

    def test_nombre_duplicado_muestra_error_en_campo(self):
        respuesta = self.api.post("/api/tipos-trabajo/", {"nombre": "Limpieza"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("nombre", respuesta.json())

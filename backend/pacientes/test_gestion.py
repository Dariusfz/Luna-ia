from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from sedes.models import Organizacion, Sede
from users.models import Usuario


class GestionPacientesTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.sede_a])
        self.ana = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="López", sede_origen=self.sede_a)
        self.beto = Paciente.objects.create(direccion="Col. Centro", 
            nombres="Beto", apellidos="Ramírez", sede_origen=self.sede_b, telefono="+504 9999-0000"
        )
        self.api = APIClient()
        self.api.force_login(self.admin)

    def _ids(self, url):
        return {p["id"] for p in self.api.get(url).json()["results"]}

    # --- Edición y estado ----------------------------------------------------

    def test_edita_paciente(self):
        respuesta = self.api.patch(f"/api/pacientes/{self.ana.pk}/", {"telefono": "88887777"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.ana.refresh_from_db()
        self.assertEqual(self.ana.telefono, "+504 8888-7777")

    def test_no_se_borra_paciente(self):
        respuesta = self.api.delete(f"/api/pacientes/{self.ana.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_desactiva_y_reactiva_paciente(self):
        self.api.patch(f"/api/pacientes/{self.ana.pk}/", {"activo": False}, format="json")
        self.ana.refresh_from_db()
        self.assertFalse(self.ana.activo)
        self.api.patch(f"/api/pacientes/{self.ana.pk}/", {"activo": True}, format="json")
        self.ana.refresh_from_db()
        self.assertTrue(self.ana.activo)

    # --- Filtros -------------------------------------------------------------

    def test_por_defecto_solo_activos(self):
        self.beto.activo = False
        self.beto.save()
        self.assertEqual(self._ids("/api/pacientes/"), {self.ana.pk})

    def test_filtra_inactivos_y_todos(self):
        self.beto.activo = False
        self.beto.save()
        self.assertEqual(self._ids("/api/pacientes/?activo=false"), {self.beto.pk})
        self.assertEqual(self._ids("/api/pacientes/?activo=todos"), {self.ana.pk, self.beto.pk})

    def test_filtra_por_sede(self):
        self.assertEqual(self._ids(f"/api/pacientes/?sede={self.sede_b.pk}"), {self.beto.pk})

    def test_sede_no_numerica_no_rompe(self):
        respuesta = self.api.get("/api/pacientes/?sede=abc")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_busqueda_por_texto_y_telefono(self):
        self.assertEqual(self._ids("/api/pacientes/?q=ram"), {self.beto.pk})
        self.assertEqual(self._ids("/api/pacientes/?q=9999"), {self.beto.pk})

    # --- Validación de fecha de nacimiento -----------------------------------

    def test_fecha_con_anio_de_mas_de_cuatro_digitos_se_rechaza(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "C", "apellidos": "D", "sede_origen": self.sede_a.pk, "direccion": "Col. Centro", "fecha_nacimiento": "20261-01-01"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_nacimiento", respuesta.json())

    def test_fecha_futura_se_rechaza(self):
        manana = date.today().replace(year=date.today().year + 1).isoformat()
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "C", "apellidos": "D", "sede_origen": self.sede_a.pk, "direccion": "Col. Centro", "fecha_nacimiento": manana},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha_nacimiento", respuesta.json())

    def test_fecha_anterior_a_1900_se_rechaza(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "C", "apellidos": "D", "sede_origen": self.sede_a.pk, "direccion": "Col. Centro", "fecha_nacimiento": "1800-05-05"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_fecha_valida_se_acepta(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            {"nombres": "C", "apellidos": "D", "sede_origen": self.sede_a.pk, "direccion": "Col. Centro", "fecha_nacimiento": "1950-03-15"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)


class DuplicadosPacienteTests(TestCase):
    """Un paciente sin DNI ni teléfono no debe poder registrarse dos veces."""

    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api = APIClient()
        self.api.force_login(self.admin)
        self.existente = Paciente.objects.create(
            direccion="Col. Centro",
            nombres="Ana",
            apellidos="López",
            fecha_nacimiento=date(1990, 5, 10),
            sede_origen=self.sede,
        )

    def _datos(self, **cambios):
        datos = {
            "nombres": "Ana",
            "apellidos": "López",
            "sede_origen": self.sede.pk,
            "direccion": "Col. Centro",
            "fecha_nacimiento": "1990-05-10",
        }
        datos.update(cambios)
        return datos

    def test_no_duplica_sin_dni_ni_telefono(self):
        respuesta = self.api.post("/api/pacientes/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duplicado", respuesta.json())
        self.assertEqual(Paciente.objects.count(), 1)

    def test_detecta_el_duplicado_aunque_cambien_tildes_y_mayusculas(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            self._datos(nombres="ANA", apellidos="LOPEZ"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Paciente.objects.count(), 1)

    def test_sin_fecha_de_nacimiento_tambien_bloquea(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            self._datos(fecha_nacimiento=None),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("duplicado", respuesta.json())

    def test_permite_homonimo_si_el_admin_lo_confirma(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            self._datos(confirmar_duplicado=True),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Paciente.objects.count(), 2)

    def test_permite_homonimos_con_fechas_de_nacimiento_distintas(self):
        respuesta = self.api.post(
            "/api/pacientes/",
            self._datos(fecha_nacimiento="1995-01-02"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_identidad_repetida_da_un_error_claro(self):
        self.existente.identidad = "0801199012345"
        self.existente.save()
        respuesta = self.api.post(
            "/api/pacientes/",
            self._datos(nombres="Otra", apellidos="Persona", identidad="0801199012345"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("identidad", respuesta.json())

    def test_editar_el_mismo_paciente_no_lo_marca_como_duplicado(self):
        respuesta = self.api.patch(
            f"/api/pacientes/{self.existente.pk}/",
            {"nombres": "Ana", "apellidos": "López"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


class GestionPersonalTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.sede_a])
        self.api = APIClient()
        self.api.force_login(self.admin)

    def test_admin_cambia_rol_y_sedes(self):
        respuesta = self.api.patch(
            f"/api/usuarios/{self.recep.pk}/",
            {"rol": "asistente", "sedes": [self.sede_b.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.recep.refresh_from_db()
        self.assertEqual(self.recep.rol, "asistente")
        self.assertEqual(list(self.recep.sedes.all()), [self.sede_b])

    def test_desactiva_usuario_y_cierra_su_sesion(self):
        sesion = APIClient()
        sesion.force_login(self.recep)
        self.assertEqual(sesion.get("/api/auth/me/").status_code, status.HTTP_200_OK)

        self.api.patch(f"/api/usuarios/{self.recep.pk}/", {"is_active": False}, format="json")
        self.recep.refresh_from_db()
        self.assertFalse(self.recep.is_active)
        self.assertEqual(sesion.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_no_puede_desactivarse_a_si_mismo(self):
        respuesta = self.api.patch(f"/api/usuarios/{self.admin.pk}/", {"is_active": False}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_rol_no_admin_sin_sede_se_rechaza(self):
        respuesta = self.api.patch(
            f"/api/usuarios/{self.recep.pk}/", {"sedes": []}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtra_personal_por_estado_y_rol(self):
        self.recep.is_active = False
        self.recep.save()
        ids = {u["id"] for u in self.api.get("/api/usuarios/?activo=false").json()["results"]}
        self.assertEqual(ids, {self.recep.pk})
        ids = {u["id"] for u in self.api.get("/api/usuarios/?rol=admin").json()["results"]}
        self.assertEqual(ids, {self.admin.pk})

    def test_no_admin_no_puede_editar_personal(self):
        recep_api = APIClient()
        recep_api.force_login(self.recep)
        respuesta = recep_api.patch(f"/api/usuarios/{self.recep.pk}/", {"rol": "admin"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

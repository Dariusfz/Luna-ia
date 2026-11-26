import os
import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import HistoriaClinica, Paciente
from sedes.models import Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario

from .models import Documento

URL = "/api/documentos/"


def archivo_jpg(nombre="radiografia.jpg", contenido=b"\xff\xd8\xff" + b"0" * 200):
    return SimpleUploadedFile(nombre, contenido, content_type="image/jpeg")


@override_settings(PRIVATE_MEDIA_ROOT=tempfile.mkdtemp())
class DocumentosTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org, direccion="A")
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org, direccion="B")
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        self.recep.sedes.set([self.sede_a])
        self.paciente_a = Paciente.objects.create(
            nombres="Ana", apellidos="López", direccion="Col. Centro",
            sede_origen=self.sede_a, fecha_nacimiento=date(1990, 5, 10),
        )
        self.paciente_b = Paciente.objects.create(
            nombres="Beto", apellidos="Ramírez", direccion="Col. Norte",
            sede_origen=self.sede_b,
        )
        self.doctor = Doctor.objects.create(
            tipo="contratado", nombres="Luis", apellidos="Mejía"
        )
        self.doctor.sedes.set([self.sede_a, self.sede_b])
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.atencion = Atencion.objects.create(
            sede=self.sede_a, doctor=self.doctor, paciente=self.paciente_a,
            tipo_trabajo=self.tipo, fecha=date(2026, 11, 25),
            hora_inicio="09:00", hora_fin="09:20",
        )
        self.historia = HistoriaClinica.objects.create(
            paciente=self.paciente_a, sede=self.sede_a, doctor=self.doctor,
            fecha=date(2026, 11, 25), motivo_consulta="Revisión",
        )
        self.atencion_b = Atencion.objects.create(
            sede=self.sede_b, doctor=self.doctor, paciente=self.paciente_b,
            tipo_trabajo=self.tipo, fecha=date(2026, 11, 26),
            hora_inicio="10:00", hora_fin="10:20",
        )
        self.historia_b = HistoriaClinica.objects.create(
            paciente=self.paciente_b, sede=self.sede_b, doctor=self.doctor,
            fecha=date(2026, 11, 26),
        )
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def subir(self, api, paciente=None, sede=None, **extra):
        datos = {
            "paciente": (paciente or self.paciente_a).pk,
            "sede": (sede or self.sede_a).pk,
            "tipo": "radiografia",
            "titulo": "Radiografía panorámica",
            "archivo": archivo_jpg(),
        }
        datos.update(extra)
        return api.post(URL, datos, format="multipart")

    def test_sube_documento_y_guarda_quien_lo_subio(self):
        respuesta = self.subir(self.api_admin)
        self.assertEqual(respuesta.status_code, 201)
        documento = Documento.objects.get()
        self.assertEqual(documento.subido_por, self.admin)
        self.assertEqual(documento.paciente, self.paciente_a)
        self.assertTrue(documento.archivo.storage.exists(documento.archivo.name))
        self.assertTrue(respuesta.json()["es_imagen"])

    def test_recepcion_solo_ve_los_documentos_de_su_sede(self):
        self.subir(self.api_admin, self.paciente_a, self.sede_a)
        self.subir(self.api_admin, self.paciente_b, self.sede_b)
        datos = self.api_recep.get(URL).json()
        self.assertEqual(datos["count"], 1)
        self.assertEqual(datos["results"][0]["paciente"], self.paciente_a.pk)

    def test_no_puede_subir_a_una_sede_ajena(self):
        respuesta = self.subir(self.api_recep, self.paciente_b, self.sede_b)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("paciente", respuesta.json())

    def test_descarga_el_archivo_con_sesion(self):
        self.subir(self.api_admin)
        documento = Documento.objects.get()
        respuesta = self.api_admin.get(f"/api/documentos/{documento.pk}/archivo/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "image/jpeg")
        self.assertIn("inline", respuesta["Content-Disposition"])
        self.assertGreater(len(b"".join(respuesta.streaming_content)), 0)

    def test_anonimo_no_descarga(self):
        self.subir(self.api_admin)
        documento = Documento.objects.get()
        respuesta = APIClient().get(f"/api/documentos/{documento.pk}/archivo/")
        self.assertIn(respuesta.status_code, (401, 403))

    def test_solo_admin_elimina(self):
        self.subir(self.api_admin)
        documento = Documento.objects.get()
        ruta = documento.archivo.path
        self.assertEqual(self.api_recep.delete(f"{URL}{documento.pk}/").status_code, 403)
        self.assertEqual(self.api_admin.delete(f"{URL}{documento.pk}/").status_code, 204)
        self.assertFalse(Documento.objects.exists())
        self.assertFalse(os.path.exists(ruta))

    def test_rechaza_extensiones_no_permitidas(self):
        respuesta = self.subir(
            self.api_admin,
            archivo=SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream"),
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("archivo", respuesta.json())

    def test_vincula_atencion_e_historia_del_mismo_paciente(self):
        respuesta = self.subir(
            self.api_admin, atencion=self.atencion.pk, historia=self.historia.pk
        )
        self.assertEqual(respuesta.status_code, 201)
        datos = respuesta.json()
        self.assertEqual(datos["atencion"], self.atencion.pk)
        self.assertEqual(datos["historia"], self.historia.pk)
        self.assertIn("Limpieza", datos["atencion_resumen"])
        self.assertIn("Revisión", datos["historia_resumen"])

    def test_rechaza_atencion_de_otro_paciente(self):
        respuesta = self.subir(self.api_recep, atencion=self.atencion_b.pk)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("atencion", respuesta.json())

    def test_rechaza_historia_de_otra_sede(self):
        respuesta = self.subir(self.api_recep, historia=self.historia_b.pk)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("historia", respuesta.json())

    def test_filtra_por_atencion(self):
        self.subir(self.api_admin, atencion=self.atencion.pk)
        self.subir(self.api_admin)
        datos = self.api_admin.get(URL, {"atencion": self.atencion.pk}).json()
        self.assertEqual(datos["count"], 1)

    @override_settings(DOCUMENTOS_TAMANO_MAXIMO_MB=0)
    def test_rechaza_archivos_demasiado_grandes(self):
        respuesta = self.subir(self.api_admin)
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("archivo", respuesta.json())

    def test_filtra_por_paciente_y_tipo(self):
        self.subir(self.api_admin, tipo="radiografia")
        self.subir(self.api_admin, tipo="consentimiento", titulo="Consentimiento informado")
        datos = self.api_admin.get(URL, {"tipo": "consentimiento"}).json()
        self.assertEqual(datos["count"], 1)
        self.assertEqual(datos["results"][0]["tipo"], "consentimiento")

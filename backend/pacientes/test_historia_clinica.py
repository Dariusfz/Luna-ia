from datetime import date, time

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import HallazgoDental, HistoriaClinica, Odontograma, Paciente
from sedes.models import Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario


class HistoriaClinicaBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="Centro", organizacion=org)
        self.sede_b = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        self.recep.sedes.set([self.sede_a])
        self.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.doctor.sedes.set([self.sede_a, self.sede_b])
        self.doctor_solo_b = Doctor.objects.create(
            tipo="contratado", nombres="Solo", apellidos="Norte"
        )
        self.doctor_solo_b.sedes.set([self.sede_b])
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        self.ana = Paciente.objects.create(
            direccion="Col. Centro", nombres="Ana", apellidos="López", sede_origen=self.sede_a
        )
        self.beto = Paciente.objects.create(
            direccion="Col. Norte", nombres="Beto", apellidos="Ramírez", sede_origen=self.sede_b
        )
        self.api = APIClient()
        self.api.force_login(self.admin)

    def datos_historia(self, **cambios):
        datos = {
            "paciente": self.ana.pk,
            "sede": self.sede_a.pk,
            "doctor": self.doctor.pk,
            "fecha": "2026-11-20",
            "motivo_consulta": "Dolor en la muela",
            "diagnostico": "Caries oclusal",
        }
        datos.update(cambios)
        return datos


class HistoriaClinicaTests(HistoriaClinicaBase):
    def test_admin_crea_historia(self):
        respuesta = self.api.post("/api/historias-clinicas/", self.datos_historia(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["paciente_nombre"], "Ana López")
        self.assertEqual(HistoriaClinica.objects.count(), 1)

    def test_recepcionista_no_crea_en_otra_sede(self):
        self.api.force_login(self.recep)
        respuesta = self.api.post(
            "/api/historias-clinicas/",
            self.datos_historia(sede=self.sede_b.pk),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sede", respuesta.json())

    def test_recepcionista_no_ve_historias_de_otra_sede(self):
        HistoriaClinica.objects.create(
            paciente=self.beto, sede=self.sede_b, doctor=self.doctor
        )
        self.api.force_login(self.recep)
        respuesta = self.api.get("/api/historias-clinicas/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.json()["results"], [])

    def test_no_crea_historia_de_paciente_ajeno(self):
        self.api.force_login(self.recep)
        respuesta = self.api.post(
            "/api/historias-clinicas/",
            self.datos_historia(paciente=self.beto.pk),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paciente", respuesta.json())

    def test_rechaza_doctor_que_no_pertenece_a_la_sede(self):
        respuesta = self.api.post(
            "/api/historias-clinicas/",
            self.datos_historia(doctor=self.doctor_solo_b.pk),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())

    def test_rechaza_cita_de_otro_paciente(self):
        cita = Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.doctor,
            paciente=self.beto,
            tipo_trabajo=self.tipo,
            fecha=date(2026, 11, 20),
            hora_inicio=time(9, 0),
            hora_fin=time(9, 30),
        )
        respuesta = self.api.post(
            "/api/historias-clinicas/", self.datos_historia(atencion=cita.pk), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("atencion", respuesta.json())

    def test_no_se_borra(self):
        historia = HistoriaClinica.objects.create(
            paciente=self.ana, sede=self.sede_a, doctor=self.doctor
        )
        respuesta = self.api.delete(f"/api/historias-clinicas/{historia.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_historial_registra_la_creacion(self):
        respuesta = self.api.post("/api/historias-clinicas/", self.datos_historia(), format="json")
        historia_id = respuesta.json()["id"]
        historial = self.api.get(f"/api/historias-clinicas/{historia_id}/historial/")
        self.assertEqual(historial.status_code, status.HTTP_200_OK)
        self.assertEqual(historial.json()[0]["tipo"], "+")


class OdontogramaTests(HistoriaClinicaBase):
    def test_crea_odontograma_con_hallazgos(self):
        respuesta = self.api.post(
            "/api/odontogramas/",
            {
                "paciente": self.ana.pk,
                "sede": self.sede_a.pk,
                "doctor": self.doctor.pk,
                "fecha": "2026-11-20",
                "hallazgos": [
                    {"diente": 16, "cara": "oclusal", "estado": "caries"},
                    {"diente": 11, "estado": "corona"},
                ],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(respuesta.json()["hallazgos"]), 2)
        self.assertEqual(HallazgoDental.objects.count(), 2)

    def test_rechaza_diente_fuera_de_fdi(self):
        respuesta = self.api.post(
            "/api/odontogramas/",
            {
                "paciente": self.ana.pk,
                "sede": self.sede_a.pk,
                "hallazgos": [{"diente": 99, "estado": "caries"}],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechaza_hallazgo_repetido(self):
        respuesta = self.api.post(
            "/api/odontogramas/",
            {
                "paciente": self.ana.pk,
                "sede": self.sede_a.pk,
                "hallazgos": [
                    {"diente": 16, "cara": "oclusal", "estado": "caries"},
                    {"diente": 16, "cara": "oclusal", "estado": "obturado"},
                ],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hallazgos", respuesta.json())

    def test_rechaza_doctor_que_no_pertenece_a_la_sede(self):
        respuesta = self.api.post(
            "/api/odontogramas/",
            {
                "paciente": self.ana.pk,
                "sede": self.sede_a.pk,
                "doctor": self.doctor_solo_b.pk,
                "hallazgos": [{"diente": 16, "estado": "caries"}],
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())

    def test_editar_reemplaza_hallazgos(self):
        respuesta = self.api.post(
            "/api/odontogramas/",
            {
                "paciente": self.ana.pk,
                "sede": self.sede_a.pk,
                "hallazgos": [{"diente": 16, "estado": "caries"}],
            },
            format="json",
        )
        odontograma_id = respuesta.json()["id"]
        self.api.patch(
            f"/api/odontogramas/{odontograma_id}/",
            {"hallazgos": [{"diente": 21, "estado": "obturado"}]},
            format="json",
        )
        odontograma = Odontograma.objects.get(pk=odontograma_id)
        self.assertEqual([h.diente for h in odontograma.hallazgos.all()], [21])

from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from sedes.models import Feriado, HorarioSede, LugarExterno, Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario

from .models import Atencion, JornadaExterna, ListaEspera


class AlcancePorSedeTests(TestCase):
    """Un recepcionista solo ve y registra en sus sedes. El admin ve todo."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep_a = Usuario.objects.create_user("recep_a", password="x-Clave-2026!", rol="recepcionista")
        cls.recep_a.sedes.set([cls.sede_a])

        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente_a = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.paciente_b = Paciente.objects.create(direccion="Col. Centro", nombres="Beto", apellidos="B", sede_origen=cls.sede_b)
        cls.paciente_visitante = Paciente.objects.create(direccion="Col. Centro", nombres="Carla", apellidos="C")

        cls.atencion_a = Atencion.objects.create(
            sede=cls.sede_a, doctor=cls.doctor, paciente=cls.paciente_a, tipo_trabajo=cls.tipo,
            fecha=date(2026, 10, 20), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=500,
        )
        cls.atencion_b = Atencion.objects.create(
            sede=cls.sede_b, doctor=cls.doctor, paciente=cls.paciente_visitante, tipo_trabajo=cls.tipo,
            fecha=date(2026, 10, 21), hora_inicio=time(9), hora_fin=time(10), honorario_doctor=500,
        )

    def setUp(self):
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep_a)
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)

    def test_recepcionista_solo_ve_atenciones_de_su_sede(self):
        ids = [a["id"] for a in self.api_recep.get("/api/atenciones/").json()["results"]]
        self.assertEqual(ids, [self.atencion_a.pk])

    def test_admin_ve_todas_las_sedes(self):
        ids = {a["id"] for a in self.api_admin.get("/api/atenciones/").json()["results"]}
        self.assertEqual(ids, {self.atencion_a.pk, self.atencion_b.pk})

    def test_no_puede_registrar_atencion_en_otra_sede(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_b.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sede", respuesta.json())

    def test_puede_registrar_atencion_en_su_sede(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk,
                "fecha": (timezone.localdate() + timedelta(days=30)).isoformat(),
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
                "observaciones": "Sin novedades",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_no_puede_atender_paciente_no_visible(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_b.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "09:00", "hora_fin": "10:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paciente", respuesta.json())

    def test_tipo_trabajo_es_obligatorio(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "fecha": "2026-10-22", "hora_inicio": "09:00", "hora_fin": "10:00",
                "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipos_trabajo", respuesta.json())

    def test_hora_fin_debe_ser_posterior(self):
        respuesta = self.api_recep.post(
            "/api/atenciones/",
            {
                "sede": self.sede_a.pk, "doctor": self.doctor.pk, "paciente": self.paciente_a.pk,
                "tipo_trabajo": self.tipo.pk, "fecha": "2026-10-22",
                "hora_inicio": "10:00", "hora_fin": "09:00", "honorario_doctor": "300",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_fin", respuesta.json())

    def test_pacientes_visibles_solo_por_sede(self):
        ids = {p["id"] for p in self.api_recep.get("/api/pacientes/").json()["results"]}
        # Ana (origen A). Beto no (origen B, sin atención en A). Carla no (solo atendida en B).
        self.assertEqual(ids, {self.paciente_a.pk})

    def test_paciente_atendido_en_sede_propia_es_visible(self):
        Atencion.objects.create(
            sede=self.sede_a, doctor=self.doctor, paciente=self.paciente_visitante,
            tipo_trabajo=self.tipo, fecha=date(2026, 10, 22),
            hora_inicio=time(9), hora_fin=time(10), honorario_doctor=200,
        )
        ids = {p["id"] for p in self.api_recep.get("/api/pacientes/").json()["results"]}
        self.assertIn(self.paciente_visitante.pk, ids)

    def test_sedes_listadas_segun_usuario(self):
        ids = [s["id"] for s in self.api_recep.get("/api/sedes/").json()["results"]]
        self.assertEqual(ids, [self.sede_a.pk])

    def test_no_se_puede_borrar_atencion(self):
        respuesta = self.api_admin.delete(f"/api/atenciones/{self.atencion_a.pk}/")
        self.assertEqual(respuesta.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class JornadasExternasTests(TestCase):
    """Los trabajos fuera de la clínica son solo del admin y no tienen datos de pacientes."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        cls.recep.sedes.set([cls.sede_a])
        cls.doctora = Doctor.objects.create(tipo="propio", nombres="Marta", apellidos="Ruiz")
        cls.lugar = LugarExterno.objects.create(nombre="Hospital X")
        cls.tipo = TipoTrabajo.objects.create(nombre="Extracción")

    def test_solo_admin_accede_a_jornadas(self):
        recep = APIClient()
        recep.force_login(self.recep)
        self.assertEqual(recep.get("/api/jornadas-externas/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_registra_jornada_sin_datos_de_paciente(self):
        admin = APIClient()
        admin.force_login(self.admin)
        respuesta = admin.post(
            "/api/jornadas-externas/",
            {
                "doctor": self.doctora.pk, "lugar": self.lugar.pk, "tipo_trabajo": self.tipo.pk,
                "fecha": "2026-10-22", "hora_inicio": "08:00", "hora_fin": "12:00",
                "monto_cobrado": "1500", "observaciones": "Cirugía de tercer molar",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("paciente", respuesta.json())
        self.assertEqual(JornadaExterna.objects.count(), 1)

    def test_lugares_externos_disponibles_para_el_admin(self):
        admin = APIClient()
        admin.force_login(self.admin)
        nombres = [l["nombre"] for l in admin.get("/api/lugares-externos/").json()["results"]]
        self.assertEqual(nombres, ["Hospital X"])


class AccesoAnonimoTests(TestCase):
    def test_api_clinica_requiere_sesion(self):
        anonimo = APIClient()
        for ruta in ["/api/atenciones/", "/api/pacientes/", "/api/jornadas-externas/", "/api/sedes/"]:
            with self.subTest(ruta=ruta):
                self.assertIn(
                    anonimo.get(ruta).status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                )


class ChoquesDeAgendaTests(TestCase):
    """Un doctor y un paciente no pueden tener dos citas activas solapadas."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede_a])

        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.otro_doctor = Doctor.objects.create(tipo="propio", nombres="Marta", apellidos="Ruiz")
        cls.otro_doctor.sedes.set([cls.sede_a])
        cls.doctor_solo_b = Doctor.objects.create(
            tipo="contratado", nombres="Pedro", apellidos="Soto"
        )
        cls.doctor_solo_b.sedes.set([cls.sede_b])

        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.paciente_b = Paciente.objects.create(direccion="Col. Centro", 
            nombres="Beto", apellidos="B", sede_origen=cls.sede_a
        )
        cls.paciente_c = Paciente.objects.create(direccion="Col. Centro", 
            nombres="Carla", apellidos="C", sede_origen=cls.sede_a
        )

        # Fecha futura relativa: las citas pasadas no se pueden crear desde el panel.
        cls.fecha = timezone.localdate() + timedelta(days=30)
        cls.atencion = Atencion.objects.create(
            sede=cls.sede_a,
            doctor=cls.doctor,
            paciente=cls.paciente,
            tipo_trabajo=cls.tipo,
            fecha=cls.fecha,
            hora_inicio=time(9),
            hora_fin=time(10),
            honorario_doctor=500,
        )

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.recep)

    def _datos(self, **cambios):
        datos = {
            "sede": self.sede_a.pk,
            "doctor": self.doctor.pk,
            "paciente": self.paciente_b.pk,
            "tipo_trabajo": self.tipo.pk,
            "fecha": self.fecha.isoformat(),
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
            "honorario_doctor": "300",
        }
        datos.update(cambios)
        return datos

    def test_doctor_no_puede_tener_dos_citas_solapadas_ni_en_otra_sede(self):
        api_admin = APIClient()
        api_admin.force_login(self.admin)
        respuesta = api_admin.post(
            "/api/atenciones/",
            self._datos(
                sede=self.sede_b.pk,
                paciente=self.paciente_b.pk,
                hora_inicio="09:30",
                hora_fin="10:30",
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_citas_contiguas_son_validas(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(paciente=self.paciente_b.pk, hora_inicio="10:00", hora_fin="11:00"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_cita_cancelada_no_bloquea_el_horario(self):
        Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.doctor,
            paciente=self.paciente_b,
            tipo_trabajo=self.tipo,
            estado=Atencion.Estado.CANCELADA,
            fecha=self.fecha,
            hora_inicio=time(11),
            hora_fin=time(12),
            honorario_doctor=0,
        )
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(paciente=self.paciente_c.pk, hora_inicio="11:00", hora_fin="12:00"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_paciente_no_puede_estar_en_dos_citas_solapadas(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                doctor=self.otro_doctor.pk,
                paciente=self.paciente.pk,
                hora_inicio="09:30",
                hora_fin="10:30",
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_editar_la_misma_cita_no_choca_consigo_misma(self):
        respuesta = self.api.patch(
            f"/api/atenciones/{self.atencion.pk}/",
            {"observaciones": "Sin novedades"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_cancelar_una_cita_no_valida_choques(self):
        respuesta = self.api.patch(
            f"/api/atenciones/{self.atencion.pk}/",
            {"estado": Atencion.Estado.CANCELADA},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_cita_nueva_sin_estado_queda_pendiente(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(paciente=self.paciente_b.pk, hora_inicio="10:00", hora_fin="11:00"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["estado"], Atencion.Estado.PENDIENTE)

    def test_cita_nueva_no_permite_otro_estado(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                paciente=self.paciente_b.pk,
                hora_inicio="10:00",
                hora_fin="11:00",
                estado=Atencion.Estado.CANCELADA,
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", respuesta.json())

    def test_no_permite_crear_cita_en_fecha_pasada(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                doctor=self.otro_doctor.pk,
                paciente=self.paciente_b.pk,
                fecha="2020-01-01",
                hora_inicio="10:00",
                hora_fin="11:00",
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha", respuesta.json())

    def test_permite_crear_cita_para_hoy(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                doctor=self.otro_doctor.pk,
                paciente=self.paciente_b.pk,
                fecha=timezone.localdate().isoformat(),
                hora_inicio="23:00",
                hora_fin="23:30",
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_permite_editar_una_cita_con_fecha_pasada(self):
        pasada = Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.otro_doctor,
            paciente=self.paciente_c,
            tipo_trabajo=self.tipo,
            fecha=date(2020, 1, 1),
            hora_inicio=time(9),
            hora_fin=time(10),
            honorario_doctor=0,
        )
        respuesta = self.api.patch(
            f"/api/atenciones/{pasada.pk}/",
            {"observaciones": "Corrección"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


class DisponibilidadTests(TestCase):
    """Consulta de horarios ocupados por sede, doctor y fecha."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede_a])
        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.otro_doctor = Doctor.objects.create(tipo="propio", nombres="Marta", apellidos="Ruiz")
        cls.otro_doctor.sedes.set([cls.sede_a])
        cls.doctor_solo_b = Doctor.objects.create(
            tipo="contratado", nombres="Pedro", apellidos="Soto"
        )
        cls.doctor_solo_b.sedes.set([cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.fecha = date(2026, 11, 2)
        Atencion.objects.create(
            sede=cls.sede_a,
            doctor=cls.doctor,
            paciente=cls.paciente,
            tipo_trabajo=cls.tipo,
            fecha=cls.fecha,
            hora_inicio=time(9),
            hora_fin=time(10),
            honorario_doctor=500,
        )

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.recep)

    def _consultar(self, **params):
        base = {"sede": self.sede_a.pk, "fecha": self.fecha.isoformat()}
        base.update(params)
        return self.api.get("/api/atenciones/disponibilidad/", base)

    def test_lista_ocupados_y_detecta_choque(self):
        respuesta = self._consultar(
            doctor=self.doctor.pk, hora_inicio="09:30", hora_fin="10:00"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        datos = respuesta.json()
        self.assertEqual(datos["sede"]["id"], self.sede_a.pk)
        self.assertEqual(datos["fecha"], self.fecha.isoformat())
        self.assertEqual(len(datos["doctores"]), 1)
        doctor = datos["doctores"][0]
        self.assertFalse(doctor["disponible"])
        self.assertEqual(doctor["ocupados"][0]["hora_inicio"], "09:00")
        self.assertEqual(doctor["ocupados"][0]["hora_fin"], "10:00")

    def test_horario_libre(self):
        respuesta = self._consultar(
            doctor=self.doctor.pk, hora_inicio="10:00", hora_fin="11:00"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertTrue(respuesta.json()["doctores"][0]["disponible"])

    def test_sin_doctor_lista_todos_los_de_la_sede(self):
        respuesta = self._consultar()
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        doctores = {d["doctor"]: d for d in respuesta.json()["doctores"]}
        self.assertEqual(set(doctores), {self.doctor.pk, self.otro_doctor.pk})
        self.assertEqual(doctores[self.doctor.pk]["ocupados"][0]["hora_inicio"], "09:00")
        self.assertEqual(doctores[self.otro_doctor.pk]["ocupados"], [])

    def test_no_permite_consultar_una_sede_ajena(self):
        respuesta = self._consultar(sede=self.sede_b.pk)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sede", respuesta.json())

    def test_rechaza_doctor_que_no_atiende_en_la_sede(self):
        respuesta = self._consultar(doctor=self.doctor_solo_b.pk)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())

    def test_rechaza_fecha_invalida(self):
        respuesta = self.api.get(
            "/api/atenciones/disponibilidad/",
            {"sede": self.sede_a.pk, "fecha": "02-11-2026"},
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha", respuesta.json())

    def test_rechaza_rango_incompleto(self):
        respuesta = self._consultar(hora_inicio="09:00")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())


class HorarioSedeTests(TestCase):
    """Valida citas contra el horario semanal y los feriados de la sede."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_sin_horario = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede, cls.sede_sin_horario])
        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede, cls.sede_sin_horario])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede)

        for dia in (0, 1):
            HorarioSede.objects.create(
                sede=cls.sede, dia_semana=dia,
                hora_apertura=time(8, 30), hora_cierre=time(11, 30),
            )
        for dia in (2, 3, 4, 5):
            for apertura, cierre in ((time(9), time(12)), (time(13), time(16, 30))):
                HorarioSede.objects.create(
                    sede=cls.sede, dia_semana=dia,
                    hora_apertura=apertura, hora_cierre=cierre,
                )

        cls.lunes = date(2027, 1, 4)
        cls.martes = date(2027, 1, 5)
        cls.miercoles = date(2027, 1, 6)
        cls.jueves = date(2027, 1, 7)
        cls.domingo = date(2027, 1, 3)

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.recep)

    def _datos(self, **cambios):
        datos = {
            "sede": self.sede.pk,
            "doctor": self.doctor.pk,
            "paciente": self.paciente.pk,
            "tipo_trabajo": self.tipo.pk,
            "fecha": self.lunes.isoformat(),
            "hora_inicio": "08:30",
            "hora_fin": "08:50",
            "honorario_doctor": "300",
        }
        datos.update(cambios)
        return datos

    def test_permite_cita_dentro_del_horario(self):
        respuesta = self.api.post("/api/atenciones/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_rechaza_cita_en_dia_cerrado(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(fecha=self.domingo.isoformat(), hora_inicio="09:00", hora_fin="09:20"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_rechaza_cita_fuera_del_horario(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(hora_inicio="11:20", hora_fin="11:40"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_rechaza_cita_en_hora_de_almuerzo(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                fecha=self.miercoles.isoformat(), hora_inicio="12:00", hora_fin="12:20"
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())

    def test_rechaza_cita_que_cruza_el_almuerzo(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                fecha=self.miercoles.isoformat(), hora_inicio="11:50", hora_fin="13:10"
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rechaza_cita_en_feriado_completo(self):
        Feriado.objects.create(sede=self.sede, fecha=self.martes, nombre="Día festivo")
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                fecha=self.martes.isoformat(), hora_inicio="09:00", hora_fin="09:20"
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("feriado", respuesta.json()["hora_inicio"][0].lower())

    def test_feriado_global_aplica_a_todas_las_sedes(self):
        Feriado.objects.create(sede=None, fecha=self.lunes, nombre="Feriado nacional")
        respuesta = self.api.post("/api/atenciones/", self._datos(), format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feriado_de_medio_dia_bloquea_solo_su_rango(self):
        Feriado.objects.create(
            sede=self.sede, fecha=self.jueves, nombre="Capacitación",
            todo_el_dia=False, hora_inicio=time(9), hora_fin=time(12),
        )
        bloqueada = self.api.post(
            "/api/atenciones/",
            self._datos(
                fecha=self.jueves.isoformat(), hora_inicio="09:00", hora_fin="09:20"
            ),
            format="json",
        )
        self.assertEqual(bloqueada.status_code, status.HTTP_400_BAD_REQUEST)
        libre = self.api.post(
            "/api/atenciones/",
            self._datos(
                fecha=self.jueves.isoformat(), hora_inicio="13:00", hora_fin="13:20"
            ),
            format="json",
        )
        self.assertEqual(libre.status_code, status.HTTP_201_CREATED)

    def test_sede_sin_horario_configurado_no_restringe(self):
        respuesta = self.api.post(
            "/api/atenciones/",
            self._datos(
                sede=self.sede_sin_horario.pk,
                fecha=self.domingo.isoformat(),
                hora_inicio="23:00",
                hora_fin="23:20",
            ),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

    def test_cambiar_fecha_a_dia_cerrado_rechaza(self):
        respuesta = self.api.post("/api/atenciones/", self._datos(), format="json")
        cita = respuesta.json()
        cambio = self.api.patch(
            f"/api/atenciones/{cita['id']}/",
            {"fecha": self.domingo.isoformat()},
            format="json",
        )
        self.assertEqual(cambio.status_code, status.HTTP_400_BAD_REQUEST)

    def test_editar_observaciones_no_revalida_horario(self):
        cita = Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=self.paciente,
            tipo_trabajo=self.tipo, fecha=self.domingo,
            hora_inicio=time(9), hora_fin=time(9, 20), honorario_doctor=0,
        )
        respuesta = self.api.patch(
            f"/api/atenciones/{cita.pk}/", {"observaciones": "Corrección"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def _consultar(self, **params):
        base = {"sede": self.sede.pk, "fecha": self.lunes.isoformat(), "doctor": self.doctor.pk}
        base.update(params)
        return self.api.get("/api/atenciones/disponibilidad/", base)

    def test_disponibilidad_devuelve_huecos_cada_20_minutos(self):
        datos = self._consultar().json()
        self.assertTrue(datos["horario_configurado"])
        self.assertTrue(datos["abierta"])
        self.assertEqual(datos["duracion"], 20)
        huecos = datos["doctores"][0]["huecos"]
        self.assertEqual(huecos[0], "08:30")
        self.assertEqual(huecos[-1], "11:10")
        self.assertEqual(len(huecos), 9)

    def test_disponibilidad_excluye_huecos_ocupados(self):
        Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=self.paciente,
            tipo_trabajo=self.tipo, fecha=self.lunes,
            hora_inicio=time(8, 30), hora_fin=time(8, 50), honorario_doctor=0,
        )
        huecos = self._consultar().json()["doctores"][0]["huecos"]
        self.assertNotIn("08:30", huecos)
        self.assertIn("08:50", huecos)

    def test_disponibilidad_duracion_personalizada(self):
        datos = self._consultar(duracion=30).json()
        self.assertEqual(datos["duracion"], 30)
        huecos = datos["doctores"][0]["huecos"]
        self.assertEqual(huecos[0], "08:30")
        self.assertIn("09:00", huecos)
        self.assertEqual(huecos[-1], "11:00")

    def test_disponibilidad_rechaza_duracion_invalida(self):
        for duracion in ("1", "241", "abc"):
            with self.subTest(duracion=duracion):
                respuesta = self._consultar(duracion=duracion)
                self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("duracion", respuesta.json())

    def test_disponibilidad_dia_cerrado(self):
        datos = self._consultar(fecha=self.domingo.isoformat()).json()
        self.assertFalse(datos["abierta"])
        self.assertIn("no abre", datos["motivo"])
        self.assertEqual(datos["doctores"][0]["huecos"], [])

    def test_disponibilidad_feriado_completo(self):
        Feriado.objects.create(sede=self.sede, fecha=self.martes, nombre="Día festivo")
        datos = self._consultar(fecha=self.martes.isoformat()).json()
        self.assertFalse(datos["abierta"])
        self.assertEqual(datos["feriados"][0]["nombre"], "Día festivo")

    def test_disponibilidad_feriado_medio_dia_muestra_rango_abierto(self):
        Feriado.objects.create(
            sede=self.sede, fecha=self.jueves, nombre="Capacitación",
            todo_el_dia=False, hora_inicio=time(9), hora_fin=time(12),
        )
        datos = self._consultar(fecha=self.jueves.isoformat()).json()
        self.assertTrue(datos["abierta"])
        self.assertEqual(
            datos["abiertos"], [{"hora_inicio": "13:00", "hora_fin": "16:30"}]
        )
        self.assertTrue(all(hora >= "13:00" for hora in datos["doctores"][0]["huecos"]))

    def test_disponibilidad_sede_sin_horario_no_calcula_huecos(self):
        datos = self._consultar(sede=self.sede_sin_horario.pk).json()
        self.assertFalse(datos["horario_configurado"])
        self.assertTrue(datos["abierta"])
        self.assertNotIn("huecos", datos["doctores"][0])


class ListaEsperaTests(TestCase):
    """Pacientes en espera por sede y conversión controlada a cita."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede_a])
        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.doctor_b = Doctor.objects.create(tipo="contratado", nombres="Pedro", apellidos="Soto")
        cls.doctor_b.sedes.set([cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.paciente_b = Paciente.objects.create(direccion="Col. Centro", 
            nombres="Beto", apellidos="B", sede_origen=cls.sede_b
        )
        cls.fecha = date(2027, 2, 1)

        cls.espera = ListaEspera.objects.create(
            sede=cls.sede_a,
            paciente=cls.paciente,
            doctor=cls.doctor,
            tipo_trabajo=cls.tipo,
            prioridad=ListaEspera.Prioridad.ALTA,
            motivo="Prefiere por la mañana",
        )
        ListaEspera.objects.create(
            sede=cls.sede_b,
            paciente=cls.paciente_b,
            prioridad=ListaEspera.Prioridad.BAJA,
        )

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.recep)
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)

    def _datos(self, **cambios):
        datos = {
            "sede": self.sede_a.pk,
            "paciente": self.paciente.pk,
            "doctor": self.doctor.pk,
            "tipo_trabajo": self.tipo.pk,
            "prioridad": ListaEspera.Prioridad.NORMAL,
            "motivo": "Busca cupo",
        }
        datos.update(cambios)
        return datos

    def _agendar(self, **cambios):
        datos = {
            "fecha": self.fecha.isoformat(),
            "hora_inicio": "09:00",
            "hora_fin": "09:20",
        }
        datos.update(cambios)
        return self.api.post(
            f"/api/lista-espera/{self.espera.pk}/agendar/", datos, format="json"
        )

    def test_recepcionista_solo_ve_su_sede(self):
        respuesta = self.api.get("/api/lista-espera/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in respuesta.json()["results"]]
        self.assertEqual(ids, [self.espera.pk])

    def test_admin_ve_todas_las_sedes(self):
        respuesta = self.api_admin.get("/api/lista-espera/")
        self.assertEqual(respuesta.json()["count"], 2)

    def test_crea_espera_en_su_sede(self):
        respuesta = self.api.post(
            "/api/lista-espera/", self._datos(paciente=self.paciente.pk), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["estado"], ListaEspera.Estado.ESPERANDO)
        self.assertEqual(respuesta.json()["paciente_nombre"], "Ana A")

    def test_no_crea_espera_en_sede_ajena(self):
        respuesta = self.api.post(
            "/api/lista-espera/", self._datos(sede=self.sede_b.pk), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sede", respuesta.json())

    def test_no_crea_para_paciente_de_otra_sede(self):
        respuesta = self.api.post(
            "/api/lista-espera/", self._datos(paciente=self.paciente_b.pk), format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("paciente", respuesta.json())

    def test_espera_nueva_no_nace_agendada(self):
        respuesta = self.api.post(
            "/api/lista-espera/",
            self._datos(estado=ListaEspera.Estado.AGENDADO),
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("estado", respuesta.json())

    def test_marca_contactado(self):
        respuesta = self.api.patch(
            f"/api/lista-espera/{self.espera.pk}/",
            {"estado": ListaEspera.Estado.CONTACTADO},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.espera.refresh_from_db()
        self.assertEqual(self.espera.estado, ListaEspera.Estado.CONTACTADO)

    def test_filtra_por_estado_prioridad_y_texto(self):
        self.assertEqual(
            self.api.get("/api/lista-espera/?estado=esperando").json()["count"], 1
        )
        self.assertEqual(
            self.api.get(f"/api/lista-espera/?prioridad={ListaEspera.Prioridad.ALTA}").json()[
                "count"
            ],
            1,
        )
        self.assertEqual(self.api.get("/api/lista-espera/?q=ana").json()["count"], 1)
        self.assertEqual(self.api.get("/api/lista-espera/?q=zzz").json()["count"], 0)

    def test_agendar_convierte_la_espera_en_cita(self):
        respuesta = self._agendar()
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        datos = respuesta.json()
        self.assertEqual(datos["estado"], ListaEspera.Estado.AGENDADO)
        self.assertEqual(datos["atencion_fecha"], self.fecha.isoformat())
        self.espera.refresh_from_db()
        self.assertIsNotNone(self.espera.atencion_id)
        self.assertEqual(self.espera.atencion.estado, Atencion.Estado.PENDIENTE)

    def test_agendar_usa_doctor_y_tipo_preferidos(self):
        respuesta = self._agendar()
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.espera.refresh_from_db()
        self.assertEqual(self.espera.atencion.doctor, self.doctor)
        self.assertEqual(self.espera.atencion.tipo_trabajo, self.tipo)

    def test_agendar_exige_doctor_y_tipo_si_no_hay_preferencia(self):
        espera = ListaEspera.objects.create(sede=self.sede_a, paciente=self.paciente)
        respuesta = self.api.post(
            f"/api/lista-espera/{espera.pk}/agendar/",
            {"fecha": self.fecha.isoformat(), "hora_inicio": "09:00", "hora_fin": "09:20"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", respuesta.json())

    def test_agendar_dos_veces_se_rechaza(self):
        self.assertEqual(self._agendar().status_code, status.HTTP_201_CREATED)
        segunda = self._agendar(hora_inicio="09:20", hora_fin="09:40")
        self.assertEqual(segunda.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", segunda.json())

    def test_agendar_espera_cancelada_se_rechaza(self):
        self.espera.estado = ListaEspera.Estado.CANCELADO
        self.espera.save(update_fields=["estado"])
        respuesta = self._agendar()
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", respuesta.json())

    def test_agendar_doctor_de_otra_sede_se_rechaza(self):
        respuesta = self._agendar(doctor=self.doctor_b.pk)
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("doctor", respuesta.json())
        self.espera.refresh_from_db()
        self.assertEqual(self.espera.estado, ListaEspera.Estado.ESPERANDO)

    def test_agendar_respeta_el_horario_de_la_sede(self):
        HorarioSede.objects.create(
            sede=self.sede_a,
            dia_semana=self.fecha.weekday(),
            hora_apertura=time(9),
            hora_cierre=time(12),
        )
        respuesta = self._agendar(hora_inicio="13:00", hora_fin="13:20")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())
        self.assertEqual(Atencion.objects.filter(paciente=self.paciente).count(), 0)
        self.espera.refresh_from_db()
        self.assertEqual(self.espera.estado, ListaEspera.Estado.ESPERANDO)

    def test_agendar_respeta_feriado(self):
        Feriado.objects.create(sede=self.sede_a, fecha=self.fecha, nombre="Feriado")
        respuesta = self._agendar()
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("hora_inicio", respuesta.json())


class OrigenAtencionTests(TestCase):
    """La cita guarda el canal de creación y un historial de cambios."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.recep = Usuario.objects.create_user(
            "recep",
            password="x-Clave-2026!",
            rol="recepcionista",
            first_name="Rosa",
            last_name="Pérez",
        )
        cls.recep.sedes.set([cls.sede_a])
        cls.otro = Usuario.objects.create_user(
            "otro", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza")
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", nombres="Ana", apellidos="A", sede_origen=cls.sede_a)
        cls.fecha = timezone.localdate() + timedelta(days=30)

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.recep)

    def _datos(self, **cambios):
        datos = {
            "sede": self.sede_a.pk,
            "doctor": self.doctor.pk,
            "paciente": self.paciente.pk,
            "tipo_trabajo": self.tipo.pk,
            "fecha": self.fecha.isoformat(),
            "hora_inicio": "09:00",
            "hora_fin": "10:00",
            "honorario_doctor": "300",
        }
        datos.update(cambios)
        return datos

    def _crear(self, **cambios):
        return self.api.post("/api/atenciones/", self._datos(**cambios), format="json")

    def test_creacion_desde_panel_registra_origen_y_usuario(self):
        respuesta = self._crear()
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        datos = respuesta.json()
        self.assertEqual(datos["origen"], Atencion.Origen.PANEL)
        self.assertEqual(datos["origen_nombre"], "Panel")
        self.assertEqual(datos["creado_por"], self.recep.pk)
        self.assertEqual(datos["creado_por_nombre"], "Rosa Pérez")
        atencion = Atencion.objects.get(pk=datos["id"])
        self.assertEqual(atencion.origen, Atencion.Origen.PANEL)
        self.assertEqual(atencion.creado_por, self.recep)

    def test_origen_y_creado_por_son_solo_lectura(self):
        respuesta = self._crear(
            origen=Atencion.Origen.AGENTE_WHATSAPP,
            creado_por=self.otro.pk,
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["origen"], Atencion.Origen.PANEL)
        self.assertEqual(respuesta.json()["creado_por"], self.recep.pk)

    def test_filtra_por_origen(self):
        panel = self._crear().json()
        agente = Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.doctor,
            paciente=self.paciente,
            tipo_trabajo=self.tipo,
            fecha=self.fecha,
            hora_inicio=time(10),
            hora_fin=time(11),
            origen=Atencion.Origen.AGENTE_WHATSAPP,
        )
        respuesta = self.api.get("/api/atenciones/?origen=agente_whatsapp")
        ids = [item["id"] for item in respuesta.json()["results"]]
        self.assertEqual(ids, [agente.pk])
        self.assertNotIn(panel["id"], ids)

    def test_historial_registra_creacion_y_cambio(self):
        creada = self._crear().json()
        cambio = self.api.patch(
            f"/api/atenciones/{creada['id']}/",
            {"estado": Atencion.Estado.CONFIRMADA},
            format="json",
        )
        self.assertEqual(cambio.status_code, status.HTTP_200_OK)

        respuesta = self.api.get(f"/api/atenciones/{creada['id']}/historial/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        registros = respuesta.json()
        self.assertEqual(len(registros), 2)
        self.assertEqual(registros[0]["tipo"], "~")
        self.assertEqual(registros[0]["tipo_nombre"], "Actualizada")
        self.assertEqual(registros[0]["usuario"], self.recep.username)
        self.assertEqual(registros[0]["usuario_nombre"], "Rosa Pérez")
        self.assertTrue(any(cambio["campo"] == "estado" for cambio in registros[0]["cambios"]))
        self.assertEqual(registros[1]["tipo"], "+")
        self.assertEqual(registros[1]["tipo_nombre"], "Creada")
        self.assertEqual(registros[1]["usuario"], self.recep.username)

    def test_historial_no_muestra_citas_de_otra_sede(self):
        atencion_b = Atencion.objects.create(
            sede=self.sede_b,
            doctor=self.doctor,
            paciente=self.paciente,
            tipo_trabajo=self.tipo,
            fecha=self.fecha,
            hora_inicio=time(9),
            hora_fin=time(10),
        )
        respuesta = self.api.get(f"/api/atenciones/{atencion_b.pk}/historial/")
        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

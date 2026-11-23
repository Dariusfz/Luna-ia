from datetime import date, time, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agenda.models import Atencion, AtencionTrabajo
from pacientes.models import Paciente
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

RUTAS = [
    "/api/analitica/citas-hoy/",
    "/api/analitica/atendidos-mes/",
    "/api/analitica/por-servicio/",
    "/api/analitica/por-hora/",
    "/api/analitica/por-sede/",
]


class AnaliticaBase(TestCase):
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
        self.paciente = Paciente.objects.create(
            nombres="Ana", apellidos="López", sede_origen=self.sede_a, direccion="Col. Centro"
        )
        self.limpieza = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.extraccion = TipoTrabajo.objects.create(nombre="Extracción", precio=800)
        self.hoy = timezone.localdate()
        self.admin_api = APIClient()
        self.admin_api.force_login(self.admin)
        self.recep_api = APIClient()
        self.recep_api.force_login(self.recep)

    def crear(self, sede, fecha, hora=time(9, 0), estado=Atencion.Estado.PENDIENTE, trabajos=None):
        atencion = Atencion.objects.create(
            sede=sede,
            doctor=self.doctor,
            paciente=self.paciente,
            tipo_trabajo=(trabajos or [self.limpieza])[0],
            estado=estado,
            fecha=fecha,
            hora_inicio=hora,
            hora_fin=time(hora.hour, hora.minute + 20) if hora.minute < 40 else time(hora.hour + 1, 0),
        )
        for orden, tipo in enumerate(trabajos or [self.limpieza]):
            AtencionTrabajo.objects.create(atencion=atencion, tipo_trabajo=tipo, orden=orden)
        return atencion


class FormatoYPermisosTests(AnaliticaBase):
    def test_requiere_sesion(self):
        for ruta in RUTAS:
            respuesta = APIClient().get(ruta)
            self.assertIn(respuesta.status_code, (401, 403), ruta)

    def test_formato_comun_en_todas_las_rutas(self):
        for ruta in RUTAS:
            datos = self.admin_api.get(ruta).json()
            self.assertEqual(
                set(datos), {"titulo", "tipo_grafica", "ejes", "datos", "total", "filtros"}, ruta
            )
            self.assertEqual(
                datos["total"], sum(d["valor"] for d in datos["datos"]), ruta
            )

    def test_fechas_invalidas_devuelven_400(self):
        respuesta = self.admin_api.get("/api/analitica/por-servicio/?desde=ayer")
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.admin_api.get("/api/analitica/por-sede/?desde=2026-05-10&hasta=2026-01-01")
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.admin_api.get("/api/analitica/atendidos-mes/?mes=2026-13")
        self.assertEqual(respuesta.status_code, 400)

    def test_rango_demasiado_grande_devuelve_400(self):
        respuesta = self.admin_api.get(
            "/api/analitica/por-hora/?desde=2020-01-01&hasta=2026-01-01"
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_sede_no_numerica_devuelve_400(self):
        respuesta = self.admin_api.get("/api/analitica/citas-hoy/?sede=abc")
        self.assertEqual(respuesta.status_code, 400)


class FiltradoPorSedeTests(AnaliticaBase):
    def setUp(self):
        super().setUp()
        self.crear(self.sede_a, self.hoy, hora=time(9, 0))
        self.crear(self.sede_b, self.hoy, hora=time(10, 0))

    def test_admin_ve_consolidado(self):
        datos = self.admin_api.get("/api/analitica/citas-hoy/").json()
        self.assertEqual(datos["total"], 2)

    def test_recepcionista_solo_ve_sus_sedes(self):
        datos = self.recep_api.get("/api/analitica/citas-hoy/").json()
        self.assertEqual(datos["total"], 1)

    def test_recepcionista_no_puede_ver_otra_sede_con_parametro(self):
        datos = self.recep_api.get(f"/api/analitica/citas-hoy/?sede={self.sede_b.pk}").json()
        self.assertEqual(datos["total"], 0)

    def test_por_sede_no_revela_sedes_ajenas(self):
        datos = self.recep_api.get("/api/analitica/por-sede/").json()
        self.assertEqual([d["etiqueta"] for d in datos["datos"]], ["Centro"])


class CitasHoyTests(AnaliticaBase):
    def test_cuenta_por_estado_incluyendo_canceladas(self):
        self.crear(self.sede_a, self.hoy, estado=Atencion.Estado.PENDIENTE)
        self.crear(self.sede_a, self.hoy, hora=time(11, 0), estado=Atencion.Estado.CANCELADA)
        self.crear(self.sede_a, self.hoy - timedelta(days=1), estado=Atencion.Estado.COMPLETADA)
        datos = self.admin_api.get("/api/analitica/citas-hoy/").json()
        valores = {d["etiqueta"]: d["valor"] for d in datos["datos"]}
        self.assertEqual(valores["Pendiente"], 1)
        self.assertEqual(valores["Cancelada"], 1)
        self.assertEqual(valores["Completada"], 0)
        self.assertEqual(datos["total"], 2)


class AtendidosMesTests(AnaliticaBase):
    def test_solo_cuenta_completadas_del_mes_indicado(self):
        self.crear(self.sede_a, date(2026, 3, 5), estado=Atencion.Estado.COMPLETADA)
        self.crear(self.sede_a, date(2026, 3, 6), estado=Atencion.Estado.PENDIENTE)
        self.crear(self.sede_a, date(2026, 4, 1), estado=Atencion.Estado.COMPLETADA)
        datos = self.admin_api.get("/api/analitica/atendidos-mes/?mes=2026-03").json()
        self.assertEqual(datos["total"], 1)
        self.assertEqual(len(datos["datos"]), 31)
        self.assertEqual(datos["tipo_grafica"], "linea")

    def test_rango_de_varios_meses_cubre_todos_los_dias(self):
        self.crear(self.sede_a, date(2026, 3, 5), estado=Atencion.Estado.COMPLETADA)
        self.crear(self.sede_a, date(2026, 4, 1), estado=Atencion.Estado.COMPLETADA)
        datos = self.admin_api.get(
            "/api/analitica/atendidos-mes/?desde=2026-03-01&hasta=2026-04-30"
        ).json()
        self.assertEqual(datos["total"], 2)
        self.assertEqual(len(datos["datos"]), 61)
        self.assertEqual(datos["filtros"]["desde"], "2026-03-01")
        self.assertEqual(datos["filtros"]["hasta"], "2026-04-30")


class PorServicioTests(AnaliticaBase):
    def test_una_cita_con_dos_trabajos_cuenta_en_ambos(self):
        self.crear(
            self.sede_a,
            self.hoy,
            trabajos=[self.limpieza, self.extraccion],
        )
        self.crear(self.sede_a, self.hoy, hora=time(11, 0), trabajos=[self.limpieza])
        datos = self.admin_api.get("/api/analitica/por-servicio/").json()
        valores = {d["etiqueta"]: d["valor"] for d in datos["datos"]}
        self.assertEqual(valores, {"Limpieza": 2, "Extracción": 1})

    def test_excluye_canceladas(self):
        self.crear(self.sede_a, self.hoy, estado=Atencion.Estado.CANCELADA)
        datos = self.admin_api.get("/api/analitica/por-servicio/").json()
        self.assertEqual(datos["datos"], [])


class PorHoraTests(AnaliticaBase):
    def test_agrupa_por_hora_de_inicio(self):
        self.crear(self.sede_a, self.hoy, hora=time(9, 0))
        self.crear(self.sede_a, self.hoy, hora=time(9, 20))
        self.crear(self.sede_a, self.hoy, hora=time(15, 0))
        datos = self.admin_api.get("/api/analitica/por-hora/").json()
        self.assertEqual(
            [(d["etiqueta"], d["valor"]) for d in datos["datos"]],
            [("09:00", 2), ("15:00", 1)],
        )


class PorSedeTests(AnaliticaBase):
    def test_admin_ve_ambas_sedes(self):
        self.crear(self.sede_a, self.hoy)
        self.crear(self.sede_b, self.hoy, hora=time(10, 0))
        datos = self.admin_api.get("/api/analitica/por-sede/").json()
        self.assertEqual(datos["total"], 2)
        self.assertEqual(len(datos["datos"]), 2)

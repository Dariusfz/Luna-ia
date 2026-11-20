from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from agenda.models import Atencion, AtencionTrabajo
from pacientes.models import Paciente
from pagos.models import MetodoPago, Pago
from servicios.models import TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

from . import estrategia


class ProyeccionTests(TestCase):
    def test_serie_creciente_proyecta_el_siguiente_valor(self):
        resultado = estrategia.proyectar([10, 20, 30])
        self.assertEqual(resultado["estimado_proximo_mes"], 40)
        self.assertEqual(resultado["tendencia"], "al alza")

    def test_serie_decreciente_es_a_la_baja(self):
        self.assertEqual(estrategia.proyectar([30, 20, 10])["tendencia"], "a la baja")

    def test_serie_plana_es_estable(self):
        self.assertEqual(estrategia.proyectar([5, 5, 5])["tendencia"], "estable")

    def test_proyeccion_nunca_es_negativa(self):
        self.assertEqual(estrategia.proyectar([10, 5, 0])["estimado_proximo_mes"], 0)

    def test_con_un_solo_valor_no_hay_proyeccion(self):
        self.assertIsNone(estrategia.proyectar([7]))

    def test_meses_se_acotan(self):
        self.assertEqual(estrategia._meses(1), estrategia.MESES_MINIMO)
        self.assertEqual(estrategia._meses(99), estrategia.MESES_MAXIMO)
        self.assertEqual(estrategia._meses("abc"), estrategia.MESES_DEFECTO)


class AnalisisBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="Centro", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.sede])
        self.usuario_doctor = Usuario.objects.create_user("doc", password="x-Clave-2026!", rol="doctor")
        self.usuario_doctor.sedes.set([self.sede])
        self.doctor = Doctor.objects.create(tipo="propio", nombres="Ana", apellidos="Doc", usuario=self.usuario_doctor)
        self.doctor.sedes.set([self.sede])
        self.otro = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.otro.sedes.set([self.sede])
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.paciente = Paciente.objects.create(
            nombres="Carlos", apellidos="Pérez", sede_origen=self.sede, direccion="Col. Centro",
        )

    def cita(self, doctor, estado=Atencion.Estado.PENDIENTE, tipo=None):
        hoy = timezone.localdate()
        atencion = Atencion.objects.create(
            sede=self.sede, doctor=doctor, paciente=self.paciente, tipo_trabajo=tipo or self.tipo,
            estado=estado, fecha=hoy, hora_inicio=time(9, 0), hora_fin=time(9, 20),
        )
        AtencionTrabajo.objects.create(atencion=atencion, tipo_trabajo=tipo or self.tipo)
        return atencion


class AlcanceAnalisisTests(AnalisisBase):
    def test_admin_recibe_finanzas(self):
        _, datos = estrategia.ejecutar(self.admin, {})
        self.assertIn("finanzas", datos["secciones"])
        self.assertIn("citas_y_atenciones", datos["secciones"])

    def test_recepcionista_no_recibe_finanzas(self):
        _, datos = estrategia.ejecutar(self.recep, {})
        self.assertNotIn("finanzas", datos["secciones"])
        self.assertIn("tratamientos", datos["secciones"])

    def test_doctor_solo_cuenta_sus_citas(self):
        self.cita(self.doctor)
        self.cita(self.otro)
        _, datos = estrategia.ejecutar(self.usuario_doctor, {})
        mes_actual = datos["secciones"]["citas_y_atenciones"]["citas_por_mes"][-1]
        self.assertEqual(mes_actual["citas"], 1)

    def test_no_expone_ids_ni_datos_clinicos(self):
        self.cita(self.doctor)
        _, datos = estrategia.ejecutar(self.admin, {})
        texto = str(datos)
        self.assertNotIn("'id'", texto)
        self.assertNotIn("paciente_id", texto)

    def test_sin_acceso_devuelve_403(self):
        usuario = Usuario.objects.create_user("sin", password="x-Clave-2026!", rol="recepcionista")
        usuario.rol = "rol_inventado"
        codigo, _ = estrategia.ejecutar(usuario, {})
        self.assertEqual(codigo, 403)


class ContenidoAnalisisTests(AnalisisBase):
    def test_tratamiento_nuevo_aparece_como_creciente(self):
        self.cita(self.doctor, tipo=TipoTrabajo.objects.create(nombre="Ortodoncia", precio=900))
        _, datos = estrategia.ejecutar(self.admin, {"meses": 6})
        trat = {t["tratamiento"]: t for t in datos["secciones"]["tratamientos"]["mas_solicitados"]}
        self.assertEqual(trat["Ortodoncia"]["tendencia"], "crece")
        self.assertEqual(trat["Ortodoncia"]["citas"], 1)

    def test_cancelaciones_se_calculan(self):
        self.cita(self.doctor)
        self.cita(self.doctor, estado=Atencion.Estado.CANCELADA)
        _, datos = estrategia.ejecutar(self.admin, {})
        self.assertEqual(datos["secciones"]["citas_y_atenciones"]["tasa_cancelacion_pct"], 50.0)

    def test_finanzas_suma_cobros_del_periodo(self):
        atencion = self.cita(self.doctor, estado=Atencion.Estado.COMPLETADA)
        Pago.objects.create(
            atencion=atencion, monto=250, metodo=MetodoPago.choices[0][0],
            fecha=timezone.localdate() - timedelta(days=1),
        )
        _, datos = estrategia.ejecutar(self.admin, {"meses": 3})
        self.assertEqual(datos["secciones"]["finanzas"]["total_cobrado_periodo"], 250.0)

    def test_respuesta_declara_el_periodo_y_la_nota(self):
        _, datos = estrategia.ejecutar(self.admin, {"meses": 4})
        self.assertEqual(datos["periodo"]["meses"], 4)
        self.assertEqual(len(datos["secciones"]["citas_y_atenciones"]["citas_por_mes"]), 4)
        self.assertIn("estimaciones", datos["nota"])

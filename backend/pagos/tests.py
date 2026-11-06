from datetime import time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import Paciente
from sedes.models import Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario

from .models import Pago, PagoDoctor


class CajaTests(TestCase):
    """Cobros por cita, pagos a doctores y resumen de caja solo para admin."""

    @classmethod
    def setUpTestData(cls):
        org = Organizacion.objects.create(nombre="Clínica")
        cls.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        cls.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        cls.admin = Usuario.objects.create_user(
            "admin", password="x-Clave-2026!", rol="admin", first_name="Ada", last_name="Admin"
        )
        cls.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        cls.recep.sedes.set([cls.sede_a])
        cls.doctor = Doctor.objects.create(
            tipo="contratado", nombres="Luis", apellidos="Mejía"
        )
        cls.doctor.sedes.set([cls.sede_a, cls.sede_b])
        cls.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=1200)
        cls.paciente = Paciente.objects.create(direccion="Col. Centro", 
            nombres="Ana", apellidos="López", sede_origen=cls.sede_a
        )
        cls.hoy = timezone.localdate()
        cls.atencion = Atencion.objects.create(
            sede=cls.sede_a,
            doctor=cls.doctor,
            paciente=cls.paciente,
            tipo_trabajo=cls.tipo,
            fecha=cls.hoy,
            hora_inicio=time(9),
            hora_fin=time(10),
            estado=Atencion.Estado.COMPLETADA,
            precio_paciente=1000,
            honorario_doctor=400,
        )
        cls.atencion_b = Atencion.objects.create(
            sede=cls.sede_b,
            doctor=cls.doctor,
            paciente=cls.paciente,
            tipo_trabajo=cls.tipo,
            fecha=cls.hoy,
            hora_inicio=time(11),
            hora_fin=time(12),
            estado=Atencion.Estado.COMPLETADA,
            precio_paciente=500,
            honorario_doctor=100,
        )

    def setUp(self):
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def _pago(self, monto, **cambios):
        datos = {
            "atencion": self.atencion.pk,
            "monto": monto,
            "metodo": "efectivo",
            "fecha": self.hoy.isoformat(),
        }
        datos.update(cambios)
        return self.api_admin.post("/api/pagos/", datos, format="json")

    def _pago_doctor(self, monto, **cambios):
        datos = {
            "atencion": self.atencion.pk,
            "monto": monto,
            "metodo": "transferencia",
            "fecha": self.hoy.isoformat(),
        }
        datos.update(cambios)
        return self.api_admin.post("/api/pagos-doctores/", datos, format="json")

    def test_recepcionista_no_puede_ver_ni_registrar_caja(self):
        self.assertEqual(self.api_recep.get("/api/pagos/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.api_recep.get("/api/pagos-doctores/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.api_recep.get("/api/caja/resumen/").status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(self.api_recep.post("/api/pagos/", {}, format="json").status_code, 403)

    def test_abonos_parciales_actualizan_saldo(self):
        primero = self._pago("300")
        self.assertEqual(primero.status_code, status.HTTP_201_CREATED)
        self.assertEqual(primero.json()["total_pagado"], "300.00")
        self.assertEqual(primero.json()["saldo_pendiente"], "700.00")
        self.assertEqual(primero.json()["registrado_por"], self.admin.pk)
        self.assertEqual(primero.json()["metodo_nombre"], "Efectivo")

        segundo = self._pago("700", metodo="tarjeta")
        self.assertEqual(segundo.status_code, status.HTTP_201_CREATED)
        self.assertEqual(segundo.json()["total_pagado"], "1000.00")
        self.assertEqual(segundo.json()["saldo_pendiente"], "0.00")
        self.assertEqual(Pago.objects.filter(atencion=self.atencion).count(), 2)

    def test_rechaza_abono_mayor_al_saldo(self):
        self._pago("800")
        respuesta = self._pago("300")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("monto", respuesta.json())

    def test_rechaza_cobro_de_cita_cancelada(self):
        self.atencion.estado = Atencion.Estado.CANCELADA
        self.atencion.save(update_fields=["estado"])
        respuesta = self._pago("100")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("atencion", respuesta.json())

    def test_rechaza_cobro_sin_precio_definido(self):
        self.atencion.precio_paciente = Decimal("0")
        self.atencion.save(update_fields=["precio_paciente"])
        respuesta = self._pago("100")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("atencion", respuesta.json())

    def test_rechaza_fecha_futura(self):
        manana = self.hoy + timedelta(days=1)
        respuesta = self._pago("100", fecha=manana.isoformat())
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("fecha", respuesta.json())

    def test_pago_a_doctor_actualiza_saldo(self):
        respuesta = self._pago_doctor("150")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.json()["doctor"], self.doctor.pk)
        self.assertEqual(respuesta.json()["total_pagado"], "150.00")
        self.assertEqual(respuesta.json()["saldo_pendiente"], "250.00")
        self.assertEqual(PagoDoctor.objects.get().doctor, self.doctor)

    def test_rechaza_pago_mayor_al_honorario(self):
        self._pago_doctor("300")
        respuesta = self._pago_doctor("150")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("monto", respuesta.json())

    def test_resumen_por_dia_y_sede(self):
        self._pago("300")
        self._pago_doctor("100")
        self.api_admin.post(
            "/api/pagos/",
            {
                "atencion": self.atencion_b.pk,
                "monto": "200",
                "metodo": "efectivo",
                "fecha": self.hoy.isoformat(),
            },
            format="json",
        )

        respuesta = self.api_admin.get(
            f"/api/caja/resumen/?desde={self.hoy}&hasta={self.hoy}&sede={self.sede_a.pk}"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        datos = respuesta.json()
        self.assertEqual(datos["cobrado"], "1000.00")
        self.assertEqual(datos["por_cobrar"], "0.00")
        self.assertEqual(datos["comision_doctores"], "400.00")
        self.assertEqual(datos["ganancia"], "600.00")
        self.assertEqual(datos["abonos_caja"], "300.00")
        self.assertEqual(datos["pagado_doctores"], "100.00")
        self.assertEqual(datos["cantidad_cobros"], 1)
        self.assertEqual(datos["cantidad_abonos"], 1)
        self.assertEqual(datos["por_dia"][0]["fecha"], self.hoy.isoformat())
        self.assertEqual(datos["por_dia"][0]["cobrado"], "1000.00")
        self.assertEqual(datos["por_dia"][0]["comision_doctores"], "400.00")

        consolidado = self.api_admin.get(
            f"/api/caja/resumen/?desde={self.hoy}&hasta={self.hoy}"
        ).json()
        self.assertEqual(consolidado["cobrado"], "1500.00")
        self.assertEqual(consolidado["comision_doctores"], "500.00")
        self.assertEqual(consolidado["ganancia"], "1000.00")
        self.assertEqual(consolidado["cantidad_cobros"], 2)
        self.assertEqual(consolidado["abonos_caja"], "500.00")
        self.assertEqual(consolidado["pagado_doctores"], "100.00")

    def test_resumen_cuenta_pendientes_y_abonos(self):
        pendiente = Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.doctor,
            paciente=self.paciente,
            tipo_trabajo=self.tipo,
            fecha=self.hoy,
            hora_inicio=time(13),
            hora_fin=time(14),
            estado=Atencion.Estado.PENDIENTE,
            precio_paciente=600,
            honorario_doctor=0,
        )
        self.api_admin.post(
            "/api/pagos/",
            {
                "atencion": pendiente.pk,
                "monto": "200",
                "metodo": "efectivo",
                "fecha": self.hoy.isoformat(),
            },
            format="json",
        )

        datos = self.api_admin.get(
            f"/api/caja/resumen/?desde={self.hoy}&hasta={self.hoy}&sede={self.sede_a.pk}"
        ).json()
        self.assertEqual(datos["cobrado"], "1000.00")
        self.assertEqual(datos["por_cobrar"], "400.00")
        self.assertEqual(datos["comision_doctores"], "400.00")
        self.assertEqual(datos["abonos_caja"], "200.00")
        self.assertEqual(datos["cantidad_cobros"], 1)

    def test_resumen_incluye_rango_de_fechas(self):
        ayer = self.hoy - timedelta(days=1)
        Atencion.objects.create(
            sede=self.sede_a,
            doctor=self.doctor,
            paciente=self.paciente,
            tipo_trabajo=self.tipo,
            fecha=ayer,
            hora_inicio=time(9),
            hora_fin=time(10),
            estado=Atencion.Estado.COMPLETADA,
            precio_paciente=700,
            honorario_doctor=100,
        )
        self.api_admin.post(
            "/api/pagos/",
            {
                "atencion": self.atencion.pk,
                "monto": "250",
                "metodo": "efectivo",
                "fecha": ayer.isoformat(),
            },
            format="json",
        )
        self._pago("300")

        respuesta = self.api_admin.get(
            f"/api/caja/resumen/?desde={ayer}&hasta={self.hoy}&sede={self.sede_a.pk}"
        ).json()
        self.assertEqual(respuesta["cobrado"], "1700.00")
        self.assertEqual(respuesta["comision_doctores"], "500.00")
        self.assertEqual(respuesta["ganancia"], "1200.00")
        self.assertEqual(respuesta["abonos_caja"], "550.00")
        self.assertEqual(respuesta["cantidad_cobros"], 2)
        self.assertEqual(len(respuesta["por_dia"]), 2)
        self.assertEqual(respuesta["por_dia"][0]["fecha"], ayer.isoformat())
        self.assertEqual(respuesta["por_dia"][0]["cobrado"], "700.00")

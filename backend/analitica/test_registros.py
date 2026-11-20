from datetime import date, time
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import Paciente
from pagos.models import MetodoPago, Pago
from servicios.models import Especialidad, TipoTrabajo
from sedes.models import Organizacion, Sede
from users.models import Doctor, Usuario

from . import registros
from .asistente import _definiciones

URL = "/api/analitica/asistente/"


class RegistrosBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.centro = Sede.objects.create(nombre="Centro", organizacion=org)
        self.norte = Sede.objects.create(nombre="Norte", organizacion=org)
        self.admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.recep = Usuario.objects.create_user("recep", password="x-Clave-2026!", rol="recepcionista")
        self.recep.sedes.set([self.centro])
        self.usuario_doctor = Usuario.objects.create_user("doc", password="x-Clave-2026!", rol="doctor")
        self.usuario_doctor.sedes.set([self.centro])
        self.doctor = Doctor.objects.create(
            tipo="propio", nombres="Ana", apellidos="Doc", usuario=self.usuario_doctor
        )
        self.doctor.sedes.set([self.centro])
        self.otro_doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.otro_doctor.sedes.set([self.centro])
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.carlos = Paciente.objects.create(
            nombres="Carlos", apellidos="Pérez", sede_origen=self.centro,
            direccion="Col. Centro", telefono="+504 9999-0001",
            identidad="0801199012345", alergias="penicilina",
        )
        self.carlos2 = Paciente.objects.create(
            nombres="Carlos Andrés", apellidos="Lara", sede_origen=self.centro, direccion="Col. Centro",
        )
        self.ana = Paciente.objects.create(
            nombres="Ana", apellidos="Gómez", sede_origen=self.norte, direccion="Col. Norte",
        )
        Especialidad.objects.create(nombre="Ortodoncia")
        Especialidad.objects.create(nombre="Endodoncia", activo=False)
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)
        self.api_doctor = APIClient()
        self.api_doctor.force_login(self.usuario_doctor)

    def cita(self, doctor, paciente, origen=Atencion.Origen.PANEL, sede=None, estado=None):
        return Atencion.objects.create(
            sede=sede or self.centro,
            doctor=doctor,
            paciente=paciente,
            tipo_trabajo=self.tipo,
            estado=estado or Atencion.Estado.PENDIENTE,
            origen=origen,
            fecha=timezone.localdate(),
            hora_inicio=time(9, 0),
            hora_fin=time(9, 20),
        )

    def consultar(self, api, argumentos):
        return api.post(URL, {"pregunta": "consulta"}, format="json")

    def ejecutar(self, usuario, argumentos):
        return registros.ejecutar(usuario, argumentos)


class AlcanceAdminTests(RegistrosBase):
    def test_admin_cuenta_pacientes_por_nombre(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "filtros": {"nombre": "Carlos"}})
        self.assertEqual(codigo, 200)
        self.assertEqual(datos["total"], 2)
        nombres = sorted(r["nombre"] for r in datos["registros"])
        self.assertEqual(nombres, ["Carlos Andrés Lara", "Carlos Pérez"])

    def test_admin_cuenta_especialidades_incluye_inactivas(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "especialidades"})
        self.assertEqual(datos["total"], 2)
        codigo, datos = self.ejecutar(
            self.admin, {"entidad": "especialidades", "agrupar_por": "activo"}
        )
        valores = {g["valor"]: g["cantidad"] for g in datos["grupos"]}
        self.assertEqual(valores, {"Activas": 1, "Inactivas": 1})

    def test_admin_cuenta_citas_del_agente_whatsapp(self):
        self.cita(self.doctor, self.carlos, origen=Atencion.Origen.AGENTE_WHATSAPP)
        self.cita(self.doctor, self.ana, origen=Atencion.Origen.AGENTE_WHATSAPP)
        self.cita(self.doctor, self.ana, origen=Atencion.Origen.PANEL)
        codigo, datos = self.ejecutar(
            self.admin, {"entidad": "atenciones", "filtros": {"origen": "agente_whatsapp"}}
        )
        self.assertEqual(datos["total"], 2)

    def test_origen_acepta_la_etiqueta_en_español(self):
        self.cita(self.doctor, self.carlos, origen=Atencion.Origen.AGENTE_WHATSAPP)
        codigo, datos = self.ejecutar(
            self.admin, {"entidad": "atenciones", "filtros": {"origen": "Agente WhatsApp"}}
        )
        self.assertEqual(datos["total"], 1)

    def test_admin_suma_pagos(self):
        atencion = self.cita(self.doctor, self.carlos)
        metodo = MetodoPago.choices[0][0]
        Pago.objects.create(atencion=atencion, monto=300, metodo=metodo, fecha=timezone.localdate())
        Pago.objects.create(atencion=atencion, monto=200, metodo=metodo, fecha=timezone.localdate())
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pagos"})
        self.assertEqual(datos["suma_total"], "500.00")
        self.assertEqual(datos["total"], 2)

    def test_admin_ve_personal(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "personal", "filtros": {"rol": "recepcionista"}})
        self.assertEqual(datos["total"], 1)
        self.assertEqual(datos["registros"][0]["usuario"], "recep")


class AlcanceRolTests(RegistrosBase):
    def test_recepcionista_no_puede_ver_pagos_ni_personal(self):
        for entidad in ("pagos", "pagos_doctores", "jornadas_externas", "personal"):
            codigo, datos = self.ejecutar(self.recep, {"entidad": entidad})
            self.assertEqual(codigo, 403, entidad)

    def test_recepcionista_solo_ve_pacientes_de_sus_sedes(self):
        codigo, datos = self.ejecutar(self.recep, {"entidad": "pacientes"})
        nombres = {r["nombre"] for r in datos["registros"]}
        self.assertIn("Carlos Pérez", nombres)
        self.assertNotIn("Ana Gómez", nombres)

    def test_recepcionista_no_ve_citas_de_otra_sede(self):
        self.cita(self.doctor, self.ana, sede=self.norte)
        codigo, datos = self.ejecutar(self.recep, {"entidad": "atenciones"})
        self.assertEqual(datos["total"], 0)

    def test_doctor_solo_ve_pacientes_con_citas_suyas(self):
        self.cita(self.doctor, self.carlos)
        self.cita(self.otro_doctor, self.carlos2)
        codigo, datos = self.ejecutar(self.usuario_doctor, {"entidad": "pacientes"})
        nombres = {r["nombre"] for r in datos["registros"]}
        self.assertEqual(nombres, {"Carlos Pérez"})

    def test_doctor_solo_ve_sus_propias_citas(self):
        self.cita(self.doctor, self.carlos)
        self.cita(self.otro_doctor, self.carlos2)
        codigo, datos = self.ejecutar(self.usuario_doctor, {"entidad": "atenciones"})
        self.assertEqual(datos["total"], 1)

    def test_doctor_no_ve_pagos_ni_lista_de_espera(self):
        self.assertEqual(self.ejecutar(self.usuario_doctor, {"entidad": "pagos"})[0], 403)
        self.assertEqual(self.ejecutar(self.usuario_doctor, {"entidad": "lista_espera"})[0], 403)

    def test_definiciones_segun_rol(self):
        def nombres_entidades(usuario):
            for definicion in _definiciones(usuario):
                if definicion["function"]["name"] == "consultar_registros":
                    return set(definicion["function"]["parameters"]["properties"]["entidad"]["enum"])
            return set()

        self.assertEqual(nombres_entidades(self.recep), {
            "pacientes", "doctores", "especialidades", "tipos_trabajo", "sedes", "atenciones", "lista_espera",
        })
        self.assertNotIn("pagos", nombres_entidades(self.recep))
        self.assertEqual(nombres_entidades(self.admin), set(registros.ENTIDADES))


class SeguridadYFormatoTests(RegistrosBase):
    def test_no_expone_datos_clinicos_ni_identificadores(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "filtros": {"nombre": "Carlos Pérez"}})
        registro = datos["registros"][0]
        for campo in ("identidad", "alergias", "direccion", "email", "id", "pk"):
            self.assertNotIn(campo, registro)
        self.assertNotIn("penicilina", str(datos))

    def test_filtro_desconocido_devuelve_400_con_opciones(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "filtros": {"dni": "123"}})
        self.assertEqual(codigo, 400)
        self.assertIn("nombre", datos["error"])

    def test_valor_de_opcion_invalido_devuelve_400(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "atenciones", "filtros": {"estado": "volando"}})
        self.assertEqual(codigo, 400)

    def test_acepta_desde_y_hasta_como_alias_de_fecha(self):
        self.cita(self.doctor, self.carlos, origen=Atencion.Origen.AGENTE_WHATSAPP)
        codigo, datos = self.ejecutar(
            self.admin,
            {"entidad": "atenciones", "filtros": {"origen": "agente_whatsapp", "desde": "2020-01-01", "hasta": "2099-12-31"}},
        )
        self.assertEqual(codigo, 200)
        self.assertEqual(datos["total"], 1)

    def test_filtro_mes_cuenta_el_mes_completo(self):
        hoy = timezone.localdate()
        self.cita(self.doctor, self.carlos, origen=Atencion.Origen.AGENTE_WHATSAPP)
        futura = self.cita(self.doctor, self.ana, origen=Atencion.Origen.AGENTE_WHATSAPP)
        Atencion.objects.filter(pk=futura.pk).update(fecha=hoy.replace(day=28))
        codigo, datos = self.ejecutar(
            self.admin,
            {"entidad": "atenciones", "filtros": {"origen": "agente_whatsapp", "mes": hoy.strftime("%Y-%m")}},
        )
        self.assertEqual(datos["total"], 2)

    def test_mes_con_formato_invalido_devuelve_400(self):
        codigo, _ = self.ejecutar(self.admin, {"entidad": "atenciones", "filtros": {"mes": "2026-13"}})
        self.assertEqual(codigo, 400)

    def test_filtros_como_texto_json(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "filtros": '{"nombre": "Carlos"}'})
        self.assertEqual(codigo, 200)
        self.assertEqual(datos["total"], 2)

    def test_fecha_invalida_devuelve_400(self):
        codigo, _ = self.ejecutar(self.admin, {"entidad": "pagos", "filtros": {"desde": "ayer"}})
        self.assertEqual(codigo, 400)

    def test_entidad_inexistente_devuelve_400(self):
        codigo, _ = self.ejecutar(self.admin, {"entidad": "usuarios_sql"})
        self.assertEqual(codigo, 400)

    def test_limite_se_acota(self):
        for i in range(60):
            Paciente.objects.create(nombres=f"P{i}", apellidos="X", sede_origen=self.centro, direccion="d")
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "limite": 999})
        self.assertEqual(datos["mostrando"], registros.LIMITE_MAXIMO)
        self.assertGreater(datos["total"], datos["mostrando"])

    def test_agrupar_por_campo_no_permitido_devuelve_400(self):
        codigo, _ = self.ejecutar(self.admin, {"entidad": "pacientes", "agrupar_por": "identidad"})
        self.assertEqual(codigo, 400)

    def test_busqueda_sin_resultados(self):
        codigo, datos = self.ejecutar(self.admin, {"entidad": "pacientes", "filtros": {"nombre": "Zzzz"}})
        self.assertEqual(datos["total"], 0)
        self.assertEqual(datos["registros"], [])


class AsistenteRegistrosTests(RegistrosBase):
    @patch("analitica.asistente.llm.chat")
    def test_respuesta_con_registros_no_genera_grafica(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "consultar_registros",
                             "arguments": '{"entidad": "pacientes", "filtros": {"nombre": "Carlos"}}'},
            }]},
            {"role": "assistant", "content": "Hay 2 pacientes llamados Carlos."},
        ]
        datos = self.api_admin.post(URL, {"pregunta": "cuántos Carlos hay"}, format="json").json()
        self.assertIsNone(datos["grafica"])
        self.assertEqual(datos["respuesta"], "Hay 2 pacientes llamados Carlos.")
        resultado_enviado = chat.call_args.args[0][-1]["content"]
        self.assertIn("Carlos", resultado_enviado)

    @patch("analitica.asistente.llm.chat")
    def test_recepcionista_no_puede_forzar_pagos(self, chat):
        chat.side_effect = [
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "consultar_registros", "arguments": '{"entidad": "pagos"}'},
            }]},
            {"role": "assistant", "content": "No tienes acceso a esa información con tu rol."},
        ]
        datos = self.api_recep.post(URL, {"pregunta": "cuánto se pagó"}, format="json").json()
        self.assertIsNone(datos["grafica"])
        self.assertIn("No tienes acceso", datos["respuesta"])
        resultado_enviado = chat.call_args.args[0][-1]["content"]
        self.assertIn("error", resultado_enviado)

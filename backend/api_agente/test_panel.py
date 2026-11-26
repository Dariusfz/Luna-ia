from datetime import date

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from agenda.models import Atencion
from pacientes.models import Paciente
from sedes.models import Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor, Usuario

from .cifrado import cifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp

URL_LISTA = "/api/agente/panel/conversaciones/"
URL_RESUMEN = "/api/agente/panel/resumen/"


def url_detalle(pk):
    return f"/api/agente/panel/conversaciones/{pk}/"


def url_actualizar(pk):
    return f"/api/agente/panel/conversaciones/{pk}/actualizar/"


@override_settings(ADMIN_WHATSAPP_AVISOS=False)
class PanelBase(TestCase):
    def setUp(self):
        self.org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(
            nombre="San Pedro", organizacion=self.org, direccion="Centro"
        )
        self.otra_sede = Sede.objects.create(
            nombre="Tegucigalpa", organizacion=self.org, direccion="Centro"
        )
        self.admin = Usuario.objects.create_user(
            "admin", password="x-Clave-2026!", rol="admin"
        )
        self.recep = Usuario.objects.create_user(
            "recep", password="x-Clave-2026!", rol="recepcionista"
        )
        self.recep.sedes.set([self.sede])
        self.doctor = Usuario.objects.create_user(
            "doctor", password="x-Clave-2026!", rol="doctor"
        )
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)
        self.api_doctor = APIClient()
        self.api_doctor.force_login(self.doctor)

        self.paciente = Paciente.objects.create(
            nombres="Ana",
            apellidos="López",
            telefono="+504 9999-9999",
            direccion="Col. Kennedy",
            sede_origen=self.sede,
            fecha_nacimiento=date(1990, 5, 10),
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            telefono="+50499999999", paciente=self.paciente, sede=self.sede
        )
        self.mensaje_paciente = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=cifrar("Quiero una cita"),
        )
        self.mensaje_agente = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.AGENTE,
            contenido_cifrado=cifrar("Claro, ¿qué día te viene bien?"),
        )

    def crear_conversacion(self, telefono, sede=None):
        return ConversacionWhatsApp.objects.create(telefono=telefono, sede=sede)


class PermisosTests(PanelBase):
    def test_requiere_sesion(self):
        self.assertIn(APIClient().get(URL_LISTA).status_code, (401, 403))

    def test_doctor_no_accede(self):
        self.assertEqual(self.api_doctor.get(URL_LISTA).status_code, 403)
        self.assertEqual(self.api_doctor.get(URL_RESUMEN).status_code, 403)

    def test_admin_ve_todas_las_sedes(self):
        self.crear_conversacion("+50488888888", self.otra_sede)
        datos = self.api_admin.get(URL_LISTA).json()
        self.assertEqual(datos["count"], 2)

    def test_recepcionista_solo_sus_sedes_y_sin_sede(self):
        de_otra = self.crear_conversacion("+50488888888", self.otra_sede)
        sin_sede = self.crear_conversacion("+50477777777")
        datos = self.api_recep.get(URL_LISTA).json()
        ids = {fila["id"] for fila in datos["results"]}
        self.assertIn(self.conversacion.pk, ids)
        self.assertIn(sin_sede.pk, ids)
        self.assertNotIn(de_otra.pk, ids)

    def test_recepcionista_no_puede_editar_conversacion_de_otra_sede(self):
        de_otra = self.crear_conversacion("+50488888888", self.otra_sede)
        respuesta = self.api_recep.patch(
            url_actualizar(de_otra.pk), {"agente_activo": False}, format="json"
        )
        self.assertEqual(respuesta.status_code, 404)


class ListaTests(PanelBase):
    def test_ultimo_mensaje_descifrado_y_total(self):
        fila = self.api_admin.get(URL_LISTA).json()["results"][0]
        self.assertEqual(fila["telefono"], "+50499999999")
        self.assertEqual(fila["paciente_nombre"], "Ana López")
        self.assertEqual(fila["sede_nombre"], "San Pedro")
        self.assertEqual(fila["total_mensajes"], 2)
        self.assertEqual(fila["ultimo_mensaje"], "Claro, ¿qué día te viene bien?")
        self.assertEqual(fila["ultimo_rol"], "agente")

    def test_buscar_por_telefono_y_por_paciente(self):
        self.crear_conversacion("+50488888888", self.sede)
        self.assertEqual(
            self.api_admin.get(URL_LISTA, {"q": "8888"}).json()["count"], 1
        )
        self.assertEqual(
            self.api_admin.get(URL_LISTA, {"q": "Ana"}).json()["count"], 1
        )

    def test_filtrar_por_agente_pausado(self):
        self.conversacion.agente_activo = False
        self.conversacion.save(update_fields=["agente_activo"])
        self.crear_conversacion("+50488888888", self.sede)
        datos = self.api_admin.get(URL_LISTA, {"agente_activo": "false"}).json()
        self.assertEqual(datos["count"], 1)
        self.assertEqual(datos["results"][0]["id"], self.conversacion.pk)


class DetalleTests(PanelBase):
    def test_detalle_descifra_los_mensajes_en_orden(self):
        datos = self.api_admin.get(url_detalle(self.conversacion.pk)).json()
        self.assertEqual(
            [m["texto"] for m in datos["mensajes"]],
            ["Quiero una cita", "Claro, ¿qué día te viene bien?"],
        )
        self.assertEqual(
            [m["rol"] for m in datos["mensajes"]], ["paciente", "agente"]
        )

    def test_no_expone_el_contenido_cifrado(self):
        datos = self.api_admin.get(url_detalle(self.conversacion.pk)).json()
        self.assertNotIn("contenido_cifrado", datos["mensajes"][0])


class PausaTests(PanelBase):
    def test_pausar_y_reactivar(self):
        respuesta = self.api_admin.patch(
            url_actualizar(self.conversacion.pk),
            {"agente_activo": False},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.conversacion.refresh_from_db()
        self.assertFalse(self.conversacion.agente_activo)

        self.api_admin.patch(
            url_actualizar(self.conversacion.pk),
            {"agente_activo": True},
            format="json",
        )
        self.conversacion.refresh_from_db()
        self.assertTrue(self.conversacion.agente_activo)

    def test_solo_cambia_agente_activo(self):
        respuesta = self.api_admin.patch(
            url_actualizar(self.conversacion.pk),
            {"agente_activo": False, "telefono": "+50400000000"},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.telefono, "+50499999999")


class EliminarTests(PanelBase):
    def test_admin_elimina_conversacion_y_sus_mensajes(self):
        pk = self.conversacion.pk
        respuesta = self.api_admin.delete(url_detalle(pk))
        self.assertEqual(respuesta.status_code, 204)
        self.assertFalse(ConversacionWhatsApp.objects.filter(pk=pk).exists())
        self.assertFalse(MensajeWhatsApp.objects.filter(conversacion_id=pk).exists())

    def test_recepcionista_no_puede_eliminar(self):
        respuesta = self.api_recep.delete(url_detalle(self.conversacion.pk))
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(ConversacionWhatsApp.objects.filter(pk=self.conversacion.pk).exists())

    def test_conversacion_inexistente_devuelve_404(self):
        self.assertEqual(self.api_admin.delete(url_detalle(999999)).status_code, 404)


class ResumenTests(PanelBase):
    def test_cuenta_conversaciones_y_mensajes(self):
        datos = self.api_admin.get(URL_RESUMEN).json()
        self.assertEqual(datos["conversaciones"]["total"], 1)
        self.assertEqual(datos["conversaciones"]["activas"], 1)
        self.assertEqual(datos["conversaciones"]["pausadas"], 0)
        self.assertEqual(datos["mensajes"]["hoy"], 2)
        self.assertEqual(datos["mensajes"]["paciente_hoy"], 1)
        self.assertEqual(datos["mensajes"]["agente_hoy"], 1)
        self.assertEqual(len(datos["mensajes_por_dia"]), 14)

    def test_cuenta_citas_creadas_por_el_agente(self):
        doctor = Doctor.objects.create(
            tipo="contratado", nombres="Luis", apellidos="Mejía"
        )
        doctor.sedes.set([self.sede])
        tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        Atencion.objects.create(
            sede=self.sede,
            doctor=doctor,
            paciente=self.paciente,
            tipo_trabajo=tipo,
            fecha=date.today(),
            hora_inicio="10:00",
            hora_fin="10:20",
            origen=Atencion.Origen.AGENTE_WHATSAPP,
        )
        datos = self.api_admin.get(URL_RESUMEN).json()
        self.assertEqual(datos["citas"]["agente_mes"], 1)
        self.assertEqual(datos["citas"]["total_mes"], 1)
        self.assertEqual(datos["citas"]["porcentaje_agente"], 100.0)

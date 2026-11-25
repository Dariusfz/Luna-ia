from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from agenda.models import Atencion
from pacientes.models import Paciente
from sedes.models import Organizacion, Sede
from servicios.models import TipoTrabajo
from users.models import Doctor

from . import agente, herramientas, notificaciones
from .cifrado import cifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp

TELEFONO = "+50499999999"


class GestionDeCitasBase(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede = Sede.objects.create(nombre="San Pedro", organizacion=org, direccion="Centro")
        self.doctor = Doctor.objects.create(tipo="contratado", nombres="Luis", apellidos="Mejía")
        self.doctor.sedes.set([self.sede])
        self.tipo = TipoTrabajo.objects.create(nombre="Limpieza", precio=500)
        self.paciente = Paciente.objects.create(
            nombres="Ana", apellidos="López", telefono="+504 9999-9999",
            direccion="Col. Kennedy", sede_origen=self.sede,
            fecha_nacimiento=date(1990, 5, 10),
        )
        self.conversacion = ConversacionWhatsApp.objects.create(
            telefono=TELEFONO, paciente=self.paciente
        )
        self.cita = Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio="10:00", hora_fin="10:20",
        )

    def mensaje(self, contenido):
        return MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=cifrar(contenido),
        )

    def herramientas(self):
        return herramientas.Herramientas(self.conversacion)

    def _borrador_creado_antes(self):
        """En Windows timezone.now() tiene resolución de ~15 ms: se atrasa el borrador
        para que el mensaje de confirmación siempre sea posterior."""
        self.conversacion.refresh_from_db()
        self.conversacion.borrador["creado"] = (
            timezone.now() - timedelta(seconds=1)
        ).isoformat()
        self.conversacion.save(update_fields=["borrador"])


class CancelarCitaTests(GestionDeCitasBase):
    def test_cancelacion_requiere_confirmacion_y_cambia_el_estado(self):
        self.mensaje("quiero cancelar mi cita")
        resultado = self.herramientas().preparar_cancelacion_cita({"cita_id": self.cita.pk})
        self.assertIn("pendiente_confirmacion", resultado)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Atencion.Estado.PENDIENTE)

        self._borrador_creado_antes()
        self.mensaje("sí, confirmo")
        self.herramientas().confirmar_accion({})
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Atencion.Estado.CANCELADA)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.borrador, {})

    def test_un_si_sin_tilde_confirma_sin_llamar_al_modelo(self):
        self.mensaje("quiero cancelar mi cita")
        self.herramientas().preparar_cancelacion_cita({"cita_id": self.cita.pk})
        self.mensaje("si")

        with patch("api_agente.llm.chat") as chat:
            respuesta = agente.responder(self.conversacion)

        chat.assert_not_called()
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, Atencion.Estado.CANCELADA)
        self.assertIn("cancelé", respuesta)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.borrador, {})

    def test_no_se_puede_cancelar_una_cita_de_otro_paciente(self):
        otro = Paciente.objects.create(
            nombres="Otro", apellidos="Paciente", telefono="+504 8888-8888",
            direccion="X", sede_origen=self.sede,
        )
        ajena = Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=otro, tipo_trabajo=self.tipo,
            fecha=timezone.localdate() + timedelta(days=2),
            hora_inicio="09:00", hora_fin="09:20",
        )
        with self.assertRaises(herramientas.ErrorHerramienta):
            self.herramientas().preparar_cancelacion_cita({"cita_id": ajena.pk})


class ModificarCitaTests(GestionDeCitasBase):
    def test_modificacion_cambia_la_hora_tras_confirmar(self):
        self.mensaje("quiero cambiar mi cita a las 11")
        resultado = self.herramientas().preparar_modificacion_cita(
            {"cita_id": self.cita.pk, "hora_inicio": "11:00"}
        )
        self.assertIn("pendiente_confirmacion", resultado)
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.hora_inicio.strftime("%H:%M"), "10:00")

        self._borrador_creado_antes()
        self.mensaje("sí")
        self.herramientas().confirmar_accion({})
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.hora_inicio.strftime("%H:%M"), "11:00")
        self.assertEqual(self.cita.hora_fin.strftime("%H:%M"), "11:20")

    def test_modificacion_sin_cambios_se_rechaza(self):
        self.mensaje("cambiar la cita")
        with self.assertRaises(herramientas.ErrorHerramienta):
            self.herramientas().preparar_modificacion_cita({"cita_id": self.cita.pk})

    def test_modificacion_de_cita_ajena_se_rechaza(self):
        otro = Paciente.objects.create(
            nombres="Otro", apellidos="Paciente", telefono="+504 8888-8888",
            direccion="X", sede_origen=self.sede,
        )
        ajena = Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=otro, tipo_trabajo=self.tipo,
            fecha=timezone.localdate() + timedelta(days=2),
            hora_inicio="09:00", hora_fin="09:20",
        )
        with self.assertRaises(herramientas.ErrorHerramienta):
            self.herramientas().preparar_modificacion_cita(
                {"cita_id": ajena.pk, "hora_inicio": "11:00"}
            )

    def test_no_se_puede_modificar_una_cita_pasada(self):
        pasada = Atencion.objects.create(
            sede=self.sede, doctor=self.doctor, paciente=self.paciente, tipo_trabajo=self.tipo,
            fecha=timezone.localdate() - timedelta(days=1),
            hora_inicio="09:00", hora_fin="09:20",
        )
        with self.assertRaises(herramientas.ErrorHerramienta):
            self.herramientas().preparar_modificacion_cita(
                {"cita_id": pasada.pk, "hora_inicio": "11:00"}
            )


    def test_preguntar_por_su_cita_selecciona_el_unico_paciente_del_numero(self):
        self.conversacion.paciente = None
        self.conversacion.save(update_fields=["paciente"])
        resultado = self.herramientas().listar_mis_citas({})
        self.assertEqual(resultado[0]["fecha"], self.cita.fecha.isoformat())
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.paciente, self.paciente)


class PrepararCitaTests(GestionDeCitasBase):
    def test_palabras_cortas_no_activan_un_tratamiento_que_no_se_pidio(self):
        # "este" (de "el que esté disponible") no debe activar "estéticos".
        self.assertFalse(
            herramientas._tratamiento_mencionado(
                ["el que esté disponible"], "Colocación de brackets autoligados estéticos"
            )
        )
        self.assertFalse(
            herramientas._tratamiento_mencionado(["quiero una endodoncia"], "Control de ortodoncia")
        )
        # Los errores de escritura siguen tolerándose.
        self.assertTrue(herramientas._tratamiento_mencionado(["quiero una estraccion"], "Extraccion"))

    def test_una_mencion_vieja_no_valida_el_id_que_manda_el_modelo(self):
        brackets = TipoTrabajo.objects.create(
            nombre="Colocación de brackets superiores (Convencionales)", precio=3250
        )
        endodoncia = TipoTrabajo.objects.create(nombre="Endodoncia", precio=800)
        self.mensaje("hola, quisiera brackets")
        for relleno in (
            "una consulta", "para mi hijo", "en San Pedro", "el lunes", "a las 8",
            "por favor", "gracias", "bueno", "dale", "perfecto", "listo", "de acuerdo",
        ):
            self.mensaje(relleno)
        self.mensaje("mejor quiero una endodoncia")

        resultado = self.herramientas().preparar_cita({
            "sede_id": self.sede.pk, "doctor_id": self.doctor.pk,
            "tipo_trabajo_id": brackets.pk,
            "fecha": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hora_inicio": "08:30",
        })

        self.assertIn("Endodoncia", resultado["pendiente_confirmacion"])
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.borrador["datos"]["tipo_trabajo"], endodoncia.pk)

    def test_confirmacion_dice_el_tratamiento_que_se_guardo(self):
        endodoncia = TipoTrabajo.objects.create(nombre="Endodoncia", precio=800)
        self.mensaje("quiero una endodoncia")
        self.herramientas().preparar_cita({
            "sede_id": self.sede.pk, "doctor_id": self.doctor.pk,
            "tipo_trabajo_id": endodoncia.pk,
            "fecha": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hora_inicio": "08:30",
        })
        self.mensaje("si")

        with patch("api_agente.llm.chat") as chat:
            respuesta = agente.responder(self.conversacion)

        chat.assert_not_called()
        self.assertIn("Endodoncia", respuesta)
        self.assertIn(self.sede.nombre, respuesta)
        self.assertIn("quedó agendada", respuesta)

    def test_usa_el_tratamiento_mencionado_al_inicio_del_flujo(self):
        extraccion = TipoTrabajo.objects.create(nombre="Extraccion", precio=800)
        self.mensaje("quiero una extraccion")
        self.mensaje("en San Pedro")
        self.mensaje("el lunes a las 8 y media")
        # Este cuarto mensaje deja "extraccion" fuera de los últimos 3.
        self.mensaje("si")

        resultado = self.herramientas().preparar_cita({
            "sede_id": self.sede.pk, "doctor_id": self.doctor.pk,
            "tipo_trabajo_id": extraccion.pk,
            "fecha": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hora_inicio": "08:30",
        })

        self.assertIn("pendiente_confirmacion", resultado)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.borrador["datos"]["tipo_trabajo"], extraccion.pk)


class FamiliaresTests(GestionDeCitasBase):
    DATOS_PADRE = {
        "nombres": "Carlos Alberto",
        "apellidos": "Garcia",
        "fecha_nacimiento": "1980-03-02",
        "identidad": "0801198012345",
    }

    def _mencionar_datos_padre(self):
        self.mensaje(
            "se llama Carlos Alberto Garcia, nacio el 2 de marzo de 1980, id 0801-1980-12345"
        )

    def test_permite_registrar_un_familiar_con_el_mismo_numero(self):
        self.mensaje("quiero una cita para mi papa")
        self._mencionar_datos_padre()

        resultado = self.herramientas().preparar_paciente(
            {**self.DATOS_PADRE, "sede_id": self.sede.pk}
        )
        self.assertIn("pendiente_confirmacion", resultado)

        self.mensaje("si")
        self.herramientas().confirmar_accion({})

        padre = Paciente.objects.get(identidad="0801198012345")
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.paciente, padre)
        self.assertNotEqual(padre, self.paciente)

    def test_la_cita_usa_al_familiar_registrado_y_no_al_paciente_original(self):
        self.mensaje("quiero una cita para mi papa")
        self._mencionar_datos_padre()
        self.herramientas().preparar_paciente({**self.DATOS_PADRE, "sede_id": self.sede.pk})
        self.mensaje("si")
        self.herramientas().confirmar_accion({})
        padre = Paciente.objects.get(identidad="0801198012345")

        self.mensaje("quiere una limpieza el 18 de noviembre a las 10")
        resultado = self.herramientas().preparar_cita({
            "sede_id": self.sede.pk, "doctor_id": self.doctor.pk,
            "tipo_trabajo_id": self.tipo.pk,
            "fecha": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "hora_inicio": "10:00",
        })
        self.assertIn("pendiente_confirmacion", resultado)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.borrador["datos"]["paciente"], padre.pk)

        self.mensaje("si")
        self.herramientas().confirmar_accion({})
        cita = Atencion.objects.exclude(pk=self.cita.pk).get()
        self.assertEqual(cita.paciente, padre)

    def test_no_permite_preparar_cita_con_un_alta_de_paciente_pendiente(self):
        self.mensaje("quiero una cita para mi papa")
        self._mencionar_datos_padre()
        self.herramientas().preparar_paciente({**self.DATOS_PADRE, "sede_id": self.sede.pk})

        self.mensaje("quiere una limpieza")
        with self.assertRaises(herramientas.ErrorHerramienta) as ctx:
            self.herramientas().preparar_cita({
                "sede_id": self.sede.pk, "doctor_id": self.doctor.pk,
                "tipo_trabajo_id": self.tipo.pk,
                "fecha": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "hora_inicio": "10:00",
            })
        self.assertIn("alta de paciente pendiente", str(ctx.exception))

    def test_rechaza_dni_de_prueba(self):
        with self.assertRaises(herramientas.ErrorHerramienta):
            herramientas._identidad("0000-0000-00003")

    def test_acepta_dni_cuyo_anio_es_del_tramite(self):
        # Nació en 1990 pero el DNI se emitió en 2000 por cambio de nombre.
        self.assertEqual(herramientas._identidad("0801200012345"), "0801200012345")


class NotificacionesTests(GestionDeCitasBase):
    @override_settings(ADMIN_WHATSAPP="+50488888888", NOTIFICACIONES_WHATSAPP=True)
    @patch("api_agente.notificaciones.evolution.enviar_texto", return_value=None)
    def test_aviso_de_cita_creada_incluye_los_datos_relevantes(self, enviar):
        self.cita.refresh_from_db()
        notificaciones.notificar_cita_creada(self.cita)
        enviar.assert_called_once()
        destino, texto = enviar.call_args.args
        self.assertEqual(destino, "+50488888888")
        self.assertIn("Ana López", texto)
        self.assertIn("años", texto)
        self.assertIn("Limpieza", texto)
        self.assertIn("San Pedro", texto)
        self.assertIn("Luis Mejía", texto)
        esperado = (
            f"{notificaciones.DIAS_SEMANA[self.cita.fecha.weekday()]} "
            f"{self.cita.fecha.strftime('%d/%m/%Y')}"
        )
        self.assertIn(esperado, texto)

    @override_settings(ADMIN_WHATSAPP="+50488888888", NOTIFICACIONES_WHATSAPP=True)
    @patch("api_agente.notificaciones.evolution.enviar_texto", return_value=None)
    def test_aviso_de_cancelacion_incluye_dia_de_la_semana(self, enviar):
        self.cita.refresh_from_db()
        notificaciones.notificar_cita_cancelada(self.cita)
        texto = enviar.call_args.args[1]
        self.assertIn("cancelada", texto)
        self.assertIn(notificaciones.DIAS_SEMANA[self.cita.fecha.weekday()], texto)
        self.assertIn(self.cita.fecha.strftime("%d/%m/%Y"), texto)

    @override_settings(ADMIN_WHATSAPP="+50488888888", NOTIFICACIONES_WHATSAPP=True)
    @patch("api_agente.notificaciones.evolution.enviar_texto", return_value=None)
    def test_aviso_de_modificacion_incluye_dia_y_cambios(self, enviar):
        self.cita.refresh_from_db()
        notificaciones.notificar_cita_modificada(self.cita, "hora 11:00")
        texto = enviar.call_args.args[1]
        self.assertIn("modificada", texto)
        self.assertIn(notificaciones.DIAS_SEMANA[self.cita.fecha.weekday()], texto)
        self.assertIn("Cambios: hora 11:00", texto)

    @override_settings(ADMIN_WHATSAPP="", NOTIFICACIONES_WHATSAPP=True)
    def test_sin_numero_configurado_no_envia_nada(self):
        self.cita.refresh_from_db()
        with patch("api_agente.notificaciones.evolution.enviar_texto") as enviar:
            notificaciones.notificar_cita_creada(self.cita)
        enviar.assert_not_called()

    @override_settings(ADMIN_WHATSAPP="+50488888888", NOTIFICACIONES_WHATSAPP=True)
    @patch("api_agente.notificaciones.evolution.enviar_texto", return_value="wamid-aviso")
    def test_el_aviso_enviado_se_guarda_como_sistema(self, enviar):
        self.cita.refresh_from_db()
        notificaciones.notificar_cita_creada(self.cita)
        conversacion = ConversacionWhatsApp.objects.get(telefono="+50488888888")
        mensaje = conversacion.mensajes.get(wa_message_id="wamid-aviso")
        self.assertEqual(mensaje.rol, MensajeWhatsApp.Rol.SISTEMA)

    @override_settings(ADMIN_WHATSAPP="+50488888888")
    @patch("api_agente.notificaciones._enviar")
    def test_solicitar_revision_avisa_al_administrador(self, enviar):
        self.herramientas().solicitar_revision_administrador({"motivo": "Ortodoncia"})
        enviar.assert_called_once()
        self.assertIn("Ortodoncia", enviar.call_args.args[0])

    @patch("api_agente.herramientas.notificaciones.notificar_cita_creada")
    def test_confirmar_cita_avisa_al_administrador(self, notificar):
        datos = {
            "tipo": "cita",
            "datos": {
                "sede": self.sede.pk, "doctor": self.doctor.pk, "paciente": self.paciente.pk,
                "tipo_trabajo": self.tipo.pk,
                "fecha": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "hora_inicio": "12:00", "hora_fin": "12:20", "honorario_doctor": "0",
            },
            "resumen": "Cita de prueba",
            "creado": (timezone.now() - timedelta(seconds=1)).isoformat(),
        }
        self.conversacion.borrador = datos
        self.conversacion.estado = ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        self.conversacion.save()
        self.mensaje("sí, confirmo")

        self.herramientas().confirmar_accion({})
        notificar.assert_called_once()
        self.assertEqual(notificar.call_args.args[0].paciente, self.paciente)

    @patch("api_agente.herramientas.notificaciones.notificar_cita_cancelada")
    def test_confirmar_cancelacion_avisa_al_administrador(self, notificar):
        self.mensaje("quiero cancelar mi cita")
        self.herramientas().preparar_cancelacion_cita({"cita_id": self.cita.pk})
        self.mensaje("si")

        self.herramientas().confirmar_accion({})
        notificar.assert_called_once()
        self.assertEqual(notificar.call_args.args[0].pk, self.cita.pk)

    @patch("api_agente.herramientas.notificaciones.notificar_cita_modificada")
    def test_confirmar_modificacion_avisa_al_administrador(self, notificar):
        self.mensaje("cambiar mi cita a las 11")
        self.herramientas().preparar_modificacion_cita(
            {"cita_id": self.cita.pk, "hora_inicio": "11:00"}
        )
        self.mensaje("si")

        self.herramientas().confirmar_accion({})
        notificar.assert_called_once()
        self.assertEqual(notificar.call_args.args[0].pk, self.cita.pk)

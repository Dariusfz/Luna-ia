from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from pacientes.models import Paciente
from sedes.models import Organizacion, Sede
from users.models import Usuario

from .cifrado import cifrar, descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp, TokenServicio

URL_SEDES = "/api/agente/sedes/"


class TokenServicioTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(nombre="San Pedro", organizacion=org, direccion="Col. Centro")
        self.sede_b = Sede.objects.create(nombre="Kennedy", organizacion=org, direccion="Col. Kennedy")
        self.sede_inactiva = Sede.objects.create(
            nombre="Cerrada", organizacion=org, activa=False
        )
        self.token = TokenServicio.crear("agente-test")
        self.api = APIClient()

    def _con_token(self, token):
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_el_token_se_guarda_hasheado(self):
        self.assertFalse(TokenServicio.objects.filter(token_hash=self.token).exists())
        self.assertTrue(
            TokenServicio.objects.filter(token_hash=TokenServicio.hash_token(self.token)).exists()
        )

    def test_token_valido_lista_sedes_activas(self):
        self._con_token(self.token)
        respuesta = self.api.get(URL_SEDES)
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        nombres = [s["nombre"] for s in respuesta.json()]
        self.assertEqual(nombres, ["Kennedy", "San Pedro"])
        self.assertNotIn("Cerrada", nombres)

    def test_registra_el_ultimo_uso(self):
        self._con_token(self.token)
        self.api.get(URL_SEDES)
        servicio = TokenServicio.objects.get(nombre="agente-test")
        self.assertIsNotNone(servicio.ultimo_uso)

    def test_token_inexistente_se_rechaza(self):
        self._con_token("token-que-no-existe")
        self.assertEqual(self.api.get(URL_SEDES).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_revocado_se_rechaza(self):
        TokenServicio.objects.filter(nombre="agente-test").update(activo=False)
        self._con_token(self.token)
        self.assertEqual(self.api.get(URL_SEDES).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sin_cabecera_se_rechaza(self):
        self.assertEqual(self.api.get(URL_SEDES).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sesion_de_usuario_no_sirve_para_el_agente(self):
        admin = Usuario.objects.create_user("admin", password="x-Clave-2026!", rol="admin")
        self.api.force_login(admin)
        self.assertEqual(self.api.get(URL_SEDES).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_se_puede_crear_token_con_nombre_repetido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TokenServicio.crear("agente-test")


class MensajeWhatsAppTests(TestCase):
    def setUp(self):
        self.conversacion = ConversacionWhatsApp.objects.create(telefono="+50499999999")

    def test_el_contenido_se_guarda_cifrado(self):
        texto = "Quiero cita mañana en San Pedro"
        mensaje = MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=cifrar(texto),
        )
        mensaje.refresh_from_db()
        self.assertNotIn(texto.encode("utf-8"), bytes(mensaje.contenido_cifrado))
        self.assertEqual(descifrar(mensaje.contenido_cifrado), texto)

    def test_wa_message_id_es_unico_para_evitar_duplicados(self):
        MensajeWhatsApp.objects.create(
            conversacion=self.conversacion,
            rol=MensajeWhatsApp.Rol.PACIENTE,
            wa_message_id="ABC123",
            contenido_cifrado=cifrar("hola"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            MensajeWhatsApp.objects.create(
                conversacion=self.conversacion,
                rol=MensajeWhatsApp.Rol.PACIENTE,
                wa_message_id="ABC123",
                contenido_cifrado=cifrar("hola otra vez"),
            )

    def test_mensajes_sin_id_de_whatsapp_no_chocan(self):
        for _ in range(2):
            MensajeWhatsApp.objects.create(
                conversacion=self.conversacion,
                rol=MensajeWhatsApp.Rol.AGENTE,
                contenido_cifrado=cifrar("respuesta"),
            )
        self.assertEqual(self.conversacion.mensajes.count(), 2)

    def test_el_telefono_de_la_conversacion_es_unico(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConversacionWhatsApp.objects.create(telefono="+50499999999")


class PacienteDesdeAgenteTests(TestCase):
    """Un paciente creado por WhatsApp necesita dirección: se rechaza si falta."""

    def test_paciente_sin_direccion_no_se_puede_guardar(self):
        org = Organizacion.objects.create(nombre="Clínica")
        sede = Sede.objects.create(nombre="San Pedro", organizacion=org)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Paciente.objects.create(nombres="Ana", apellidos="Mejía", sede_origen=sede, direccion="")

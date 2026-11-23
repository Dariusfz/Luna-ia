import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from sedes.models import Organizacion, Sede

from .models import Invitacion, Usuario

PASSWORD = "Clave-Segura-2026!"


def crear_usuario(username, rol, sedes=(), password=PASSWORD):
    usuario = Usuario.objects.create_user(
        username=username, email=f"{username}@clinica.test", password=password, rol=rol
    )
    usuario.sedes.set(sedes)
    return usuario


@override_settings(FRONTEND_URL="http://frontend.test")
class InvitacionesTests(TestCase):
    def setUp(self):
        org = Organizacion.objects.create(nombre="Clínica")
        self.sede_a = Sede.objects.create(organizacion=org, nombre="Sede A")
        self.sede_b = Sede.objects.create(organizacion=org, nombre="Sede B")
        self.admin = crear_usuario("admin", Usuario.Rol.ADMIN)
        self.recepcion = crear_usuario("recep", Usuario.Rol.RECEPCIONISTA, [self.sede_a])
        self.client_admin = APIClient()
        self.client_admin.force_login(self.admin)
        self.client_recep = APIClient()
        self.client_recep.force_login(self.recepcion)

    def _token_del_correo(self):
        cuerpo = mail.outbox[-1].body
        return re.search(r"token=([\w\-]+)", cuerpo).group(1)

    def test_admin_puede_invitar_y_se_envia_correo(self):
        respuesta = self.client_admin.post(
            "/api/invitaciones/",
            {"email": "nueva@clinica.test", "rol": "recepcionista", "sedes": [self.sede_a.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["nueva@clinica.test"])
        # La respuesta nunca debe incluir el token
        self.assertNotIn("token", respuesta.json())

    @patch("users.invitaciones.send_mail", side_effect=RuntimeError("SMTP caído"))
    def test_si_el_correo_falla_no_deja_invitacion(self, _):
        respuesta = self.client_admin.post(
            "/api/invitaciones/",
            {"email": "falla@clinica.test", "rol": "asistente", "sedes": [self.sede_a.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Invitacion.objects.filter(email="falla@clinica.test").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_no_admin_no_puede_invitar(self):
        respuesta = self.client_recep.post(
            "/api/invitaciones/",
            {"email": "x@clinica.test", "rol": "asistente", "sedes": [self.sede_a.pk]},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(len(mail.outbox), 0)

    def test_rol_no_admin_requiere_sede(self):
        respuesta = self.client_admin.post(
            "/api/invitaciones/",
            {"email": "x@clinica.test", "rol": "asistente", "sedes": []},
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_aceptar_invitacion_crea_usuario_con_sedes_y_no_se_reutiliza(self):
        self.client_admin.post(
            "/api/invitaciones/",
            {"email": "nueva@clinica.test", "rol": "asistente", "sedes": [self.sede_b.pk]},
            format="json",
        )
        token = self._token_del_correo()
        datos = {
            "token": token,
            "username": "nueva",
            "nombres": "Ana",
            "apellidos": "Pérez",
            "password": PASSWORD,
        }
        anonimo = APIClient()
        respuesta = anonimo.post("/api/auth/aceptar-invitacion/", datos, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)

        usuario = Usuario.objects.get(username="nueva")
        self.assertEqual(usuario.email, "nueva@clinica.test")
        self.assertEqual(usuario.rol, "asistente")
        self.assertEqual(list(usuario.sedes.all()), [self.sede_b])
        self.assertTrue(usuario.check_password(PASSWORD))

        # Segundo uso del mismo enlace debe fallar
        datos["username"] = "otra"
        segunda = anonimo.post("/api/auth/aceptar-invitacion/", datos, format="json")
        self.assertEqual(segunda.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invitacion_expirada_no_se_acepta(self):
        token = "token-de-prueba-expirado"
        invitacion = Invitacion.objects.create(
            email="vieja@clinica.test",
            rol="asistente",
            token_hash=Invitacion.hash_token(token),
            expira=timezone.now() - timedelta(minutes=1),
        )
        invitacion.sedes.set([self.sede_a])
        respuesta = APIClient().post(
            "/api/auth/aceptar-invitacion/",
            {
                "token": token,
                "username": "vieja",
                "nombres": "V",
                "apellidos": "V",
                "password": PASSWORD,
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Usuario.objects.filter(username="vieja").exists())

    def test_el_token_se_guarda_hasheado(self):
        self.client_admin.post(
            "/api/invitaciones/",
            {"email": "hash@clinica.test", "rol": "asistente", "sedes": [self.sede_a.pk]},
            format="json",
        )
        token = self._token_del_correo()
        self.assertFalse(Invitacion.objects.filter(token_hash=token).exists())
        self.assertTrue(
            Invitacion.objects.filter(token_hash=Invitacion.hash_token(token)).exists()
        )


class LoginTests(TestCase):
    def setUp(self):
        self.usuario = crear_usuario("doc", Usuario.Rol.RECEPCIONISTA)
        self.client = APIClient()

    def test_login_correcto_y_me(self):
        respuesta = self.client.post(
            "/api/auth/login/", {"username": "doc", "password": PASSWORD}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.json()["username"], "doc")
        self.assertFalse(me.json()["es_admin"])

    def test_login_incorrecto_mensaje_generico(self):
        respuesta = self.client.post(
            "/api/auth/login/", {"username": "doc", "password": "mal"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(respuesta.json()["detail"], "Usuario o contraseña incorrectos.")

    def test_me_sin_sesion_rechazado(self):
        respuesta = APIClient().get("/api/auth/me/")
        self.assertIn(respuesta.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

import re
from datetime import timedelta

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .mfa import preparar_dispositivo
from .models import CodigoRecuperacion, DispositivoTOTP, RecuperacionContrasena, Usuario

PASSWORD = "Clave-Segura-2026!"
NUEVA = "Nueva-Clave-2027!"


@override_settings(FRONTEND_URL="http://frontend.test")
class RecuperacionContrasenaTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            "recep", email="recep@clinica.test", password=PASSWORD, rol="recepcionista"
        )
        self.anonimo = APIClient()

    def _solicitar(self, email):
        return self.anonimo.post("/api/auth/recuperar/", {"email": email}, format="json")

    def _token_del_correo(self):
        return re.search(r"token=([\w\-]+)", mail.outbox[-1].body).group(1)

    def test_solicitud_envia_enlace_a_cuenta_existente(self):
        respuesta = self._solicitar("recep@clinica.test")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["recep@clinica.test"])
        self.assertIn("http://frontend.test/recuperar/confirmar?token=", mail.outbox[0].body)

    def test_respuesta_igual_si_el_correo_no_existe(self):
        existente = self._solicitar("recep@clinica.test").json()
        inexistente = self._solicitar("nadie@clinica.test").json()
        self.assertEqual(existente, inexistente)
        self.assertEqual(len(mail.outbox), 1)  # solo el correo de la cuenta real

    def test_el_token_se_guarda_hasheado(self):
        self._solicitar("recep@clinica.test")
        token = self._token_del_correo()
        self.assertFalse(RecuperacionContrasena.objects.filter(token_hash=token).exists())
        self.assertTrue(
            RecuperacionContrasena.objects.filter(token_hash=RecuperacionContrasena.hash_token(token)).exists()
        )

    def test_confirmar_cambia_la_contrasena_y_el_enlace_queda_usado(self):
        self._solicitar("recep@clinica.test")
        token = self._token_del_correo()
        respuesta = self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": token, "password": NUEVA}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(NUEVA))
        self.assertFalse(self.usuario.check_password(PASSWORD))

        reutilizado = self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": token, "password": "Otra-Clave-2028!"}, format="json"
        )
        self.assertEqual(reutilizado.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enlace_expirado_no_sirve(self):
        RecuperacionContrasena.objects.create(
            usuario=self.usuario,
            token_hash=RecuperacionContrasena.hash_token("token-viejo"),
            expira=timezone.now() - timedelta(minutes=1),
        )
        respuesta = self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": "token-viejo", "password": NUEVA}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(PASSWORD))

    def test_contrasena_debil_se_rechaza(self):
        self._solicitar("recep@clinica.test")
        token = self._token_del_correo()
        respuesta = self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": token, "password": "123"}, format="json"
        )
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", respuesta.json())

    def test_recuperar_cierra_las_sesiones_abiertas(self):
        sesion = APIClient()
        sesion.force_login(self.usuario)
        self.assertEqual(sesion.get("/api/auth/me/").status_code, status.HTTP_200_OK)

        self._solicitar("recep@clinica.test")
        token = self._token_del_correo()
        self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": token, "password": NUEVA}, format="json"
        )
        self.assertEqual(sesion.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_sigue_pidiendo_2fa_tras_recuperar(self):
        admin = Usuario.objects.create_user("admin", email="admin@clinica.test", password=PASSWORD, rol="admin")
        self.anonimo.post("/api/auth/recuperar/", {"email": "admin@clinica.test"}, format="json")
        token = self._token_del_correo()
        self.anonimo.post(
            "/api/auth/recuperar/confirmar/", {"token": token, "password": NUEVA}, format="json"
        )
        respuesta = self.anonimo.post(
            "/api/auth/login/", {"username": "admin", "password": NUEVA}, format="json"
        )
        self.assertEqual(respuesta.json()["paso"], "configurar_2fa")
        self.assertEqual(admin.pk, Usuario.objects.get(username="admin").pk)


class RestablecerDosFactoresTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user("admin", email="admin@clinica.test", password=PASSWORD, rol="admin")
        self.recep = Usuario.objects.create_user("recep", email="recep@clinica.test", password=PASSWORD, rol="recepcionista")
        self.doctor = Usuario.objects.create_user("doctora", email="doc@clinica.test", password=PASSWORD, rol="doctor")
        for usuario in (self.admin, self.doctor):
            dispositivo, _, _ = preparar_dispositivo(usuario)
            dispositivo.confirmado = True
            dispositivo.save(update_fields=["confirmado"])
            CodigoRecuperacion.objects.create(usuario=usuario, hash_codigo="x" * 64)
        self.api_admin = APIClient()
        self.api_admin.force_login(self.admin)
        self.api_recep = APIClient()
        self.api_recep.force_login(self.recep)

    def test_admin_lista_personal_con_estado_2fa(self):
        datos = {u["username"]: u for u in self.api_admin.get("/api/usuarios/").json()["results"]}
        self.assertTrue(datos["doctora"]["tiene_2fa"])
        self.assertFalse(datos["recep"]["tiene_2fa"])

    def test_no_admin_no_lista_personal(self):
        self.assertEqual(self.api_recep.get("/api/usuarios/").status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_restablece_2fa_del_doctor(self):
        respuesta = self.api_admin.post(f"/api/usuarios/{self.doctor.pk}/restablecer-2fa/")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertFalse(DispositivoTOTP.objects.filter(usuario=self.doctor).exists())
        self.assertFalse(CodigoRecuperacion.objects.filter(usuario=self.doctor).exists())

        # Al volver a entrar debe configurar un autenticador nuevo
        anonimo = APIClient()
        paso = anonimo.post(
            "/api/auth/login/", {"username": "doctora", "password": PASSWORD}, format="json"
        ).json()["paso"]
        self.assertEqual(paso, "configurar_2fa")

    def test_restablecer_cierra_sesiones_del_usuario(self):
        sesion_doctor = APIClient()
        sesion_doctor.force_login(self.doctor)
        self.assertEqual(sesion_doctor.get("/api/auth/me/").status_code, status.HTTP_200_OK)

        self.api_admin.post(f"/api/usuarios/{self.doctor.pk}/restablecer-2fa/")
        self.assertEqual(sesion_doctor.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

    def test_no_admin_no_puede_restablecer_2fa(self):
        respuesta = self.api_recep.post(f"/api/usuarios/{self.doctor.pk}/restablecer-2fa/")
        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(DispositivoTOTP.objects.filter(usuario=self.doctor).exists())

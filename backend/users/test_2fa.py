import time
from unittest.mock import patch

import pyotp
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import CodigoRecuperacion, DispositivoTOTP, Usuario

PASSWORD = "Clave-Segura-2026!"
UN_PASO = 30  # segundos de un paso TOTP


class Autenticacion2FATests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_user(
            "admin", email="admin@clinica.test", password=PASSWORD, rol=Usuario.Rol.ADMIN
        )
        self.doctor = Usuario.objects.create_user(
            "doctora", email="doc@clinica.test", password=PASSWORD, rol=Usuario.Rol.DOCTOR
        )
        self.recep = Usuario.objects.create_user(
            "recep", email="rec@clinica.test", password=PASSWORD, rol=Usuario.Rol.RECEPCIONISTA
        )
        self.api = APIClient()

    def _login(self, username):
        return self.api.post(
            "/api/auth/login/", {"username": username, "password": PASSWORD}, format="json"
        )

    def _configurar_y_confirmar(self, username, instante=None):
        """Recorre el primer ingreso: login -> configurar -> confirmar con un código real.

        La hora se fija (y se simula en el servidor) para que el código generado y su
        verificación caigan siempre en el mismo paso TOTP de 30 s. Sin esto, el test
        falla de forma intermitente cuando la confirmación cruza el límite del paso.
        """
        self.assertEqual(self._login(username).json()["paso"], "configurar_2fa")
        secreto = self.api.post("/api/auth/2fa/configurar/").json()["secreto"]
        if instante is None:
            instante = time.time()
        codigo = pyotp.TOTP(secreto).at(instante)
        with patch("users.mfa._ahora", return_value=instante):
            respuesta = self.api.post("/api/auth/2fa/confirmar/", {"codigo": codigo}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        return secreto, respuesta.json()["codigos_recuperacion"]

    def _cerrar_sesion(self):
        self.api.post("/api/auth/logout/")

    # --- Obligatoriedad -----------------------------------------------------

    def test_recepcionista_entra_sin_2fa(self):
        respuesta = self._login("recep")
        self.assertEqual(respuesta.json()["paso"], "completo")
        self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_200_OK)

    def test_admin_y_doctor_requieren_2fa(self):
        for usuario in ("admin", "doctora"):
            with self.subTest(usuario=usuario):
                self.assertEqual(self._login(usuario).json()["paso"], "configurar_2fa")
                # Sin verificar el segundo factor no hay sesión.
                self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)
                self._cerrar_sesion()

    def test_superusuario_requiere_2fa(self):
        Usuario.objects.create_superuser("root", "root@clinica.test", PASSWORD)
        self.assertEqual(self._login("root").json()["paso"], "configurar_2fa")

    # --- Configuración ------------------------------------------------------

    def test_configurar_y_confirmar_inicia_sesion_y_entrega_codigos(self):
        _, codigos = self._configurar_y_confirmar("admin")
        self.assertEqual(len(codigos), 10)
        self.assertEqual(self.api.get("/api/auth/me/").json()["username"], "admin")

    def test_el_secreto_se_guarda_cifrado(self):
        secreto, _ = self._configurar_y_confirmar("admin")
        dispositivo = DispositivoTOTP.objects.get(usuario=self.admin)
        self.assertTrue(dispositivo.confirmado)
        self.assertNotEqual(dispositivo.secreto_cifrado, secreto)
        self.assertNotIn(secreto, dispositivo.secreto_cifrado)

    def test_codigos_de_recuperacion_se_guardan_como_hash(self):
        _, codigos = self._configurar_y_confirmar("admin")
        self.assertFalse(
            CodigoRecuperacion.objects.filter(hash_codigo__in=codigos).exists()
        )
        self.assertEqual(CodigoRecuperacion.objects.filter(usuario=self.admin).count(), 10)

    def test_confirmar_con_codigo_incorrecto_no_inicia_sesion(self):
        self._login("admin")
        self.api.post("/api/auth/2fa/configurar/")
        respuesta = self.api.post("/api/auth/2fa/confirmar/", {"codigo": "000000"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

    def test_no_se_puede_configurar_dos_veces(self):
        self._configurar_y_confirmar("admin")
        self._cerrar_sesion()
        self._login("admin")
        respuesta = self.api.post("/api/auth/2fa/configurar/")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Verificación en cada ingreso ---------------------------------------

    def _codigo_dentro_de(self, secreto, segundos):
        """Código válido dentro de `segundos`, y el reloj simulado para verificarlo."""
        instante = time.time() + segundos
        return pyotp.TOTP(secreto).at(instante), instante

    def test_ingreso_con_totp_correcto(self):
        secreto, _ = self._configurar_y_confirmar("admin")
        self._cerrar_sesion()

        self._login("admin")
        malo = self.api.post("/api/auth/2fa/verificar/", {"codigo": "000000"}, format="json")
        self.assertEqual(malo.status_code, status.HTTP_400_BAD_REQUEST)
        self._cerrar_sesion()

        # Un paso más tarde (30 s) el código nuevo sí es válido
        codigo, instante = self._codigo_dentro_de(secreto, UN_PASO)
        self._login("admin")
        with patch("users.mfa._ahora", return_value=instante):
            respuesta = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigo}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_200_OK)

    def test_codigo_totp_no_se_puede_reutilizar(self):
        secreto, _ = self._configurar_y_confirmar("admin")
        self._cerrar_sesion()

        codigo, instante = self._codigo_dentro_de(secreto, UN_PASO)
        self._login("admin")
        with patch("users.mfa._ahora", return_value=instante):
            primero = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigo}, format="json")
        self.assertEqual(primero.status_code, status.HTTP_200_OK)
        self._cerrar_sesion()

        self._login("admin")
        with patch("users.mfa._ahora", return_value=instante):
            repetido = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigo}, format="json")
        self.assertEqual(repetido.status_code, status.HTTP_400_BAD_REQUEST)

    def test_codigo_del_mismo_paso_que_la_confirmacion_no_sirve_para_entrar(self):
        """El código usado para confirmar no puede volver a usarse en el mismo paso de 30 s."""
        instante = time.time()
        secreto, _ = self._configurar_y_confirmar("admin", instante=instante)
        self._cerrar_sesion()
        self._login("admin")
        codigo = pyotp.TOTP(secreto).at(instante)
        with patch("users.mfa._ahora", return_value=instante):
            respuesta = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigo}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_codigo_de_recuperacion_es_de_un_solo_uso(self):
        _, codigos = self._configurar_y_confirmar("admin")
        self._cerrar_sesion()

        self._login("admin")
        primera = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigos[0]}, format="json")
        self.assertEqual(primera.status_code, status.HTTP_200_OK)
        self._cerrar_sesion()

        self._login("admin")
        segunda = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigos[0]}, format="json")
        self.assertEqual(segunda.status_code, status.HTTP_400_BAD_REQUEST)

    def test_codigo_de_recuperacion_acepta_minusculas_y_sin_guion(self):
        _, codigos = self._configurar_y_confirmar("admin")
        self._cerrar_sesion()
        self._login("admin")
        codigo = codigos[1].replace("-", "").lower()
        respuesta = self.api.post("/api/auth/2fa/verificar/", {"codigo": codigo}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)

    def test_tras_cinco_fallos_se_cancela_el_inicio(self):
        self._configurar_y_confirmar("admin")
        self._cerrar_sesion()
        self._login("admin")
        for _ in range(4):
            r = self.api.post("/api/auth/2fa/verificar/", {"codigo": "111111"}, format="json")
            self.assertEqual(r.json()["detail"], "Código incorrecto.")
        ultimo = self.api.post("/api/auth/2fa/verificar/", {"codigo": "111111"}, format="json")
        self.assertEqual(ultimo.json()["detail"], "Demasiados intentos. Inicia sesión de nuevo.")
        # Ya no hay sesión pendiente
        despues = self.api.post("/api/auth/2fa/verificar/", {"codigo": "111111"}, format="json")
        self.assertEqual(despues.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("No hay un inicio de sesión pendiente", despues.json()["detail"])

    def test_verificar_sin_login_previo_falla(self):
        respuesta = self.api.post("/api/auth/2fa/verificar/", {"codigo": "123456"}, format="json")
        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_se_puede_saltar_el_2fa_con_la_api_de_sesion(self):
        """Un usuario con 2FA no obtiene sesión solo con la contraseña."""
        self._login("admin")
        self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

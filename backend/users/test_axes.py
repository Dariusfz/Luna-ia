"""Bloqueo de login por intentos fallidos con django-axes (plan §6)."""

from axes.utils import reset
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Usuario

PASSWORD = "Clave-Segura-2026!"


class AxesBloqueoTests(TestCase):
    def setUp(self):
        # Axes guarda los intentos en la caché (Redis), que NO se revierte con la
        # transacción del test: hay que limpiarlos entre pruebas.
        reset()
        self.api = APIClient()
        self.recep = Usuario.objects.create_user(
            "recepcion",
            email="recepcion@clinica.test",
            password=PASSWORD,
            rol=Usuario.Rol.RECEPCIONISTA,
        )
        self.otra = Usuario.objects.create_user(
            "compañera",
            email="companera@clinica.test",
            password=PASSWORD,
            rol=Usuario.Rol.RECEPCIONISTA,
        )

    def tearDown(self):
        reset()

    def _login(self, username, password):
        return self.api.post(
            "/api/auth/login/", {"username": username, "password": password}, format="json"
        )

    def _fallar(self, veces):
        respuesta = None
        for _ in range(veces):
            respuesta = self._login(self.recep.username, "mala-clave")
        return respuesta

    def test_bloquea_tras_cinco_fallos_aunque_luego_ponga_la_correcta(self):
        self._fallar(5)
        bloqueado = self._login(self.recep.username, PASSWORD)
        self.assertEqual(bloqueado.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Demasiados intentos", bloqueado.json()["detail"])
        self.assertIn("Retry-After", bloqueado.headers)
        self.assertEqual(self.api.get("/api/auth/me/").status_code, status.HTTP_403_FORBIDDEN)

    def test_el_bloqueo_es_por_usuario_y_no_por_toda_la_red(self):
        self._fallar(5)
        self.assertEqual(
            self._login(self.recep.username, PASSWORD).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        # Otra persona desde la misma IP (el test cliente usa 127.0.0.1) entra normal.
        self.assertEqual(
            self._login(self.otra.username, PASSWORD).status_code, status.HTTP_200_OK
        )

    def test_un_login_exitoso_reinicia_el_contador(self):
        self._fallar(4)
        self.assertEqual(self._login(self.recep.username, PASSWORD).status_code, status.HTTP_200_OK)
        self.api.post("/api/auth/logout/")
        # Otros cuatro fallos más no deben bloquear: el éxito anterior limpió la cuenta.
        self._fallar(4)
        self.assertEqual(self._login(self.recep.username, PASSWORD).status_code, status.HTTP_200_OK)

    def test_la_cuenta_sigue_bloqueada_al_reiniciar_sesion(self):
        self._fallar(5)
        self.api.post("/api/auth/logout/")
        self.assertEqual(
            self._login(self.recep.username, PASSWORD).status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

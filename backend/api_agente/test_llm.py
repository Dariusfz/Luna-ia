from unittest.mock import patch

import httpx
from django.test import SimpleTestCase

from . import llm

MENSAJES = [{"role": "user", "content": "hola"}]


def respuesta_ok():
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": "hola"}}]},
    )


class Reintento429Tests(SimpleTestCase):
    @patch("api_agente.llm.time.sleep")
    @patch("api_agente.llm.httpx.post")
    def test_reintenta_429_y_devuelve_la_respuesta(self, post, sleep):
        post.side_effect = [
            httpx.Response(429, headers={"retry-after": "1"}),
            respuesta_ok(),
        ]
        with self.settings(LLM_REINTENTOS_429=2):
            mensaje = llm.chat(MENSAJES, [])
        self.assertEqual(mensaje["content"], "hola")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1.0)

    @patch("api_agente.llm.time.sleep")
    @patch("api_agente.llm.httpx.post")
    def test_429_agotado_lanza_error(self, post, sleep):
        post.side_effect = lambda *args, **kwargs: httpx.Response(
            429, headers={"retry-after": "1"}
        )
        with self.settings(LLM_REINTENTOS_429=1):
            with self.assertRaises(llm.LLMError):
                llm.chat(MENSAJES, [])
        self.assertEqual(post.call_count, 2)

    @patch("api_agente.llm.time.sleep")
    @patch("api_agente.llm.httpx.post")
    def test_400_no_se_reintenta(self, post, sleep):
        post.return_value = httpx.Response(400)
        with self.settings(LLM_REINTENTOS_429=3):
            with self.assertRaises(llm.LLMError):
                llm.chat(MENSAJES, [])
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch("api_agente.llm.time.sleep")
    @patch("api_agente.llm.httpx.post")
    def test_429_usa_retrydelay_del_cuerpo(self, post, sleep):
        post.side_effect = [
            httpx.Response(
                429, json={"error": {"details": [{"retryDelay": "7s"}]}}
            ),
            respuesta_ok(),
        ]
        with self.settings(LLM_REINTENTOS_429=1):
            llm.chat(MENSAJES, [])
        sleep.assert_called_once_with(7.0)

    @patch("api_agente.llm.httpx.post")
    def test_envia_headers_de_identificacion(self, post):
        post.return_value = respuesta_ok()
        with self.settings(LLM_USER_AGENT="LUNA-IA/test"):
            llm.chat(MENSAJES, [], session_id="ses_prueba")
        cabeceras = post.call_args.kwargs["headers"]
        self.assertEqual(cabeceras["User-Agent"], "LUNA-IA/test")
        self.assertEqual(cabeceras["x-opencode-session"], "ses_prueba")

    @patch("api_agente.llm.httpx.post")
    def test_400_incluye_el_cuerpo_del_error(self, post):
        post.return_value = httpx.Response(
            400,
            text='{"error": {"message": "Requests ending with a model turn are not supported."}}',
        )
        with self.assertRaises(llm.LLMError) as error:
            llm.chat(MENSAJES, [])
        self.assertIn("Requests ending with a model turn", str(error.exception))

    @patch("api_agente.llm.httpx.post")
    def test_error_de_red_lanza_llm_error(self, post):
        post.side_effect = httpx.ConnectError("sin red")
        with self.assertRaises(llm.LLMError):
            llm.chat(MENSAJES, [])

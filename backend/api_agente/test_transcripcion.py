from types import SimpleNamespace
from unittest.mock import patch
import sys

from django.test import SimpleTestCase, override_settings

from . import transcripcion


class SegmentoFalso:
    def __init__(self, texto):
        self.text = texto


class ModeloFalso:
    def __init__(self, textos=None, error=None):
        self.textos = textos or []
        self.error = error
        self.opciones = None
        self.llamadas = 0

    def transcribe(self, audio, **opciones):
        self.llamadas += 1
        self.opciones = opciones
        if self.error:
            raise self.error
        return iter([SegmentoFalso(t) for t in self.textos]), SimpleNamespace(language="es")


@override_settings(WHISPER_LANGUAGE="es", WHISPER_BEAM_SIZE=5)
class TranscripcionTests(SimpleTestCase):
    def setUp(self):
        transcripcion._modelo = None

    def tearDown(self):
        transcripcion._modelo = None

    def test_audio_vacio_no_carga_el_modelo(self):
        with patch.object(transcripcion, "_cargar_modelo") as cargar:
            self.assertEqual(transcripcion.transcribir(b""), "")
        cargar.assert_not_called()

    def test_une_segmentos_y_quita_espacios(self):
        transcripcion._modelo = ModeloFalso([" Quiero ", " una cita ", "   "])
        self.assertEqual(transcripcion.transcribir(b"ogg"), "Quiero una cita")

    def test_usa_espanol_y_filtro_de_voz(self):
        modelo = ModeloFalso(["Hola"])
        transcripcion._modelo = modelo
        transcripcion.transcribir(b"ogg")
        self.assertEqual(modelo.opciones["language"], "es")
        self.assertTrue(modelo.opciones["vad_filter"])

    def test_el_modelo_se_carga_una_sola_vez(self):
        with patch.object(transcripcion, "_cargar_modelo", return_value=ModeloFalso(["Hola"])) as cargar:
            transcripcion.transcribir(b"ogg")
            transcripcion.transcribir(b"ogg")
        self.assertEqual(cargar.call_count, 1)

    def test_error_del_modelo_se_envuelve(self):
        transcripcion._modelo = ModeloFalso(error=RuntimeError("sin GPU"))
        with self.assertRaises(transcripcion.TranscripcionError):
            transcripcion.transcribir(b"ogg")

    def test_si_falta_faster_whisper_se_avisa(self):
        with patch.dict(sys.modules, {"faster_whisper": None}):
            with self.assertRaises(transcripcion.TranscripcionError):
                transcripcion._cargar_modelo()

    @override_settings(WHISPER_DEVICE="cuda")
    def test_si_la_gpu_falla_se_reintenta_en_cpu(self):
        modelo = ModeloFalso(["Hola"])
        with patch.object(
            transcripcion, "_crear_modelo", side_effect=[RuntimeError("sin cuDNN"), modelo]
        ) as crear:
            self.assertIs(transcripcion._cargar_modelo(), modelo)
        self.assertEqual(crear.call_args_list[0].args, ("cuda", "int8"))
        self.assertEqual(crear.call_args_list[1].args, ("cpu", "int8"))

    @override_settings(WHISPER_DEVICE="cpu")
    def test_si_la_cpu_falla_no_reintenta(self):
        with patch.object(transcripcion, "_crear_modelo", side_effect=RuntimeError("roto")) as crear:
            with self.assertRaises(transcripcion.TranscripcionError):
                transcripcion._cargar_modelo()
        self.assertEqual(crear.call_count, 1)

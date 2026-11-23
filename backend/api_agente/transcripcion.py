"""
Transcripción de notas de voz con faster-whisper (plan §5.3).

El modelo se carga una vez por proceso y se reutiliza: la carga tarda varios segundos y
ocupa memoria. Se configura solo por entorno (`WHISPER_*`); el audio llega y se procesa
en memoria, nunca se escribe en disco ni en la base de datos.
"""

import io
import logging
import re
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_modelo = None
# Si la GPU falla al transcribir (por ejemplo, falta cublas), se queda en CPU
# para este proceso y no se vuelve a intentar en cada nota de voz.
_modelo_forzado_cpu = False
_cerrojo = threading.Lock()

# Errores típicos de CUDA mal instalada en Windows (cublas/cuDNN ausentes) o de
# binarios incompatibles. No se incluye "gpu" a secas para no confundir errores
# de otra índole.
_ERROR_GPU = re.compile(
    r"cublas|cudnn|cuda|no kernel image|Library .* (?:is )?not found|cannot be loaded",
    re.IGNORECASE,
)


class TranscripcionError(Exception):
    pass


def _es_error_de_gpu(error: Exception) -> bool:
    return bool(_ERROR_GPU.search(str(error)))


def _crear_modelo(device: str, compute_type: str):
    # Import perezoso: faster-whisper es pesado y solo se necesita en la cola `audio`.
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )


def _cargar_modelo():
    global _modelo_forzado_cpu
    if _modelo_forzado_cpu:
        return _crear_modelo("cpu", "int8")
    try:
        return _crear_modelo(settings.WHISPER_DEVICE, settings.WHISPER_COMPUTE_TYPE)
    except ImportError as error:
        raise TranscripcionError(f"faster-whisper no está instalado: {error}") from error
    except Exception as error:
        if settings.WHISPER_DEVICE == "cpu":
            raise TranscripcionError(f"No se pudo cargar el modelo de audio: {error}") from error
        # GPU mal configurada (por ejemplo, sin cuDNN): se continúa en CPU.
        logger.warning(
            "No se pudo cargar Whisper en %s (%s); se reintenta en CPU",
            settings.WHISPER_DEVICE, error,
        )
        try:
            modelo = _crear_modelo("cpu", "int8")
        except Exception as error_cpu:
            raise TranscripcionError(
                f"No se pudo cargar el modelo de audio: {error_cpu}"
            ) from error_cpu
        _modelo_forzado_cpu = True
        return modelo


def modelo_actual():
    """Instancia compartida del modelo, cargada la primera vez que se transcribe."""
    global _modelo
    if _modelo is None:
        with _cerrojo:
            if _modelo is None:
                _modelo = _cargar_modelo()
    return _modelo


def _cambiar_a_cpu():
    """Descarta el modelo de GPU y carga uno de CPU (una sola vez)."""
    global _modelo, _modelo_forzado_cpu
    with _cerrojo:
        _modelo_forzado_cpu = True
        _modelo = _crear_modelo("cpu", "int8")
    logger.warning("Whisper queda configurado en CPU para este proceso")
    return _modelo


def _texto_de(modelo, audio: bytes) -> str:
    segmentos, _ = modelo.transcribe(
        io.BytesIO(audio),
        language=settings.WHISPER_LANGUAGE,
        vad_filter=True,
        beam_size=settings.WHISPER_BEAM_SIZE,
    )
    return " ".join(segmento.text.strip() for segmento in segmentos if segmento.text.strip()).strip()


def transcribir(audio: bytes, mimetype: str = "audio/ogg") -> str:
    """
    Devuelve el texto en español. Cadena vacía si no se reconoce voz.
    `mimetype` se acepta por compatibilidad; faster-whisper detecta el formato por el
    contenido (WhatsApp envía OGG/Opus, que decodifica con PyAV).

    Si la GPU carga el modelo pero falla al transcribir (caso típico: falta
    `cublas64_12.dll`), se recarga el modelo en CPU y se reintenta una vez.
    """
    if not audio:
        return ""
    try:
        return _texto_de(modelo_actual(), audio)
    except TranscripcionError:
        raise
    except Exception as error:
        if not _modelo_forzado_cpu and _es_error_de_gpu(error):
            logger.warning("Whisper falló en GPU (%s); se reintenta en CPU", error)
            try:
                return _texto_de(_cambiar_a_cpu(), audio)
            except Exception as error_cpu:
                raise TranscripcionError(
                    f"Falló la transcripción en CPU: {error_cpu}"
                ) from error_cpu
        raise TranscripcionError(f"Falló la transcripción: {error}") from error

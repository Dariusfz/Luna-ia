"""
Transcripción de notas de voz con faster-whisper (plan §5.3).

El modelo se carga una vez por proceso y se reutiliza: la carga tarda varios segundos y
ocupa memoria. Se configura solo por entorno (`WHISPER_*`); el audio llega y se procesa
en memoria, nunca se escribe en disco ni en la base de datos.
"""

import io
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_modelo = None
_cerrojo = threading.Lock()


class TranscripcionError(Exception):
    pass


def _crear_modelo(device: str, compute_type: str):
    # Import perezoso: faster-whisper es pesado y solo se necesita en la cola `audio`.
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.WHISPER_MODEL,
        device=device,
        compute_type=compute_type,
    )


def _cargar_modelo():
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
            return _crear_modelo("cpu", "int8")
        except Exception as error_cpu:
            raise TranscripcionError(
                f"No se pudo cargar el modelo de audio: {error_cpu}"
            ) from error_cpu


def modelo_actual():
    """Instancia compartida del modelo, cargada la primera vez que se transcribe."""
    global _modelo
    if _modelo is None:
        with _cerrojo:
            if _modelo is None:
                _modelo = _cargar_modelo()
    return _modelo


def transcribir(audio: bytes, mimetype: str = "audio/ogg") -> str:
    """
    Devuelve el texto en español. Cadena vacía si no se reconoce voz.
    `mimetype` se acepta por compatibilidad; faster-whisper detecta el formato por el
    contenido (WhatsApp envía OGG/Opus, que decodifica con PyAV).
    """
    if not audio:
        return ""
    try:
        segmentos, _ = modelo_actual().transcribe(
            io.BytesIO(audio),
            language=settings.WHISPER_LANGUAGE,
            vad_filter=True,
            beam_size=settings.WHISPER_BEAM_SIZE,
        )
        return " ".join(segmento.text.strip() for segmento in segmentos if segmento.text.strip()).strip()
    except TranscripcionError:
        raise
    except Exception as error:
        raise TranscripcionError(f"Falló la transcripción: {error}") from error

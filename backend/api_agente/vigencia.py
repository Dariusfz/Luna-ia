"""
Vigencia de los mensajes de WhatsApp.

Evolution API entrega los mensajes que se acumularon mientras el proyecto estaba
apagado en cuanto la instancia vuelve a conectarse. Esos mensajes son viejos y el
agente no debe responderlos ni continuar hilos que ya terminaron.

Se aplican dos filtros (configurables por entorno en settings.py):
- Antigüedad: se descarta todo mensaje con más de WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS.
- Arranque: se descarta todo mensaje escrito antes de que arrancara este proceso,
  con un margen de WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS por latencia del webhook.
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

# Momento en que se cargó este proceso (runserver o worker de Celery).
ARRANQUE = timezone.now()


def _consciente(momento: datetime | None) -> datetime | None:
    if momento is None:
        return None
    if timezone.is_naive(momento):
        return momento.replace(tzinfo=dt_timezone.utc)
    return momento


def _segundos(nombre: str, defecto: int) -> float:
    return float(getattr(settings, nombre, defecto) or 0)


def marca_temporal(mensaje_data: dict) -> datetime | None:
    """Extrae la hora de envío del payload de Evolution, si viene incluida.

    Evolution v2 la manda en `messageTimestamp` (segundos, a veces texto) y, en
    algunos eventos, como `date_time` ISO. Si no aparece, devuelve None y el
    mensaje se procesa como siempre.
    """
    datos = mensaje_data or {}
    valor = datos.get("messageTimestamp")
    if valor is None:
        valor = datos.get("message_timestamp") or datos.get("date_time")
    if valor is None:
        return None

    numero: float | None = None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        numero = float(valor)
    elif isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        try:
            numero = float(texto)
        except ValueError:
            return _consciente(parse_datetime(texto))
    else:
        return None

    if numero > 1e11:  # algunas versiones lo envían en milisegundos
        numero /= 1000
    try:
        return datetime.fromtimestamp(numero, tz=dt_timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def motivo_para_ignorar(mensaje_data: dict, *, ahora: datetime | None = None) -> str | None:
    """Devuelve el motivo por el que un webhook no debe procesarse, o None."""
    marca = marca_temporal(mensaje_data)
    if marca is None:
        return None  # sin marca no se puede juzgar: se procesa como siempre

    referencia = ahora or timezone.now()
    maximo = _segundos("WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS", 300)
    if maximo > 0:
        edad = (referencia - marca).total_seconds()
        if edad > maximo:
            return f"llegó con {edad:.0f}s de retraso"

    tolerancia = _segundos("WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS", 90)
    if marca < ARRANQUE - timedelta(seconds=tolerancia):
        return "se escribió antes de arrancar el sistema"
    return None


def mensaje_vigente(mensaje, *, ahora: datetime | None = None) -> bool:
    """Revisa un mensaje ya guardado (tarea en cola) usando su hora de creación.

    Cubre el caso de tareas que quedaron en el broker mientras el sistema estaba
    apagado: al arrancar el worker las ejecutaría, pero ya no corresponden.
    """
    maximo = _segundos("WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS", 300)
    if maximo <= 0:
        return True
    referencia = ahora or timezone.now()
    return (referencia - mensaje.creado).total_seconds() <= maximo

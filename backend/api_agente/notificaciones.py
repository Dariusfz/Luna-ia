"""
Avisos internos al administrador de la clínica por WhatsApp.

Son informativos: si el envío falla, el flujo del paciente no se interrumpe.
El número (o números separados por coma) se configura en ADMIN_WHATSAPP.
"""

import logging

from django.conf import settings
from django.utils import timezone

from . import evolution
from .cifrado import cifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp

logger = logging.getLogger(__name__)

DIAS_SEMANA = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]


def _fecha_con_dia(fecha) -> str:
    """Formato para el administrador: 'lunes 16/11/2026'."""
    return f"{DIAS_SEMANA[fecha.weekday()]} {fecha.strftime('%d/%m/%Y')}"


def _destinatarios() -> list[str]:
    crudo = getattr(settings, "ADMIN_WHATSAPP", "") or ""
    numeros = []
    for numero in crudo.split(","):
        digitos = "".join(c for c in numero if c.isdigit())
        if digitos:
            numeros.append(f"+{digitos}")
    return numeros


def _registrar_envio(destino: str, texto: str, wa_id: str | None) -> None:
    """Guarda el aviso enviado como SISTEMA para reconocer su eco en el webhook.

    Así el mensaje que el agente manda al administrador no pausa su conversación
    ni aparece en el historial que ve el modelo.
    """
    if not wa_id:
        return
    try:
        conversacion, _ = ConversacionWhatsApp.objects.get_or_create(telefono=destino)
        MensajeWhatsApp.objects.get_or_create(
            wa_message_id=wa_id,
            defaults={
                "conversacion": conversacion,
                "rol": MensajeWhatsApp.Rol.SISTEMA,
                "tipo": MensajeWhatsApp.Tipo.TEXTO,
                "contenido_cifrado": cifrar(texto),
            },
        )
    except Exception:
        logger.exception("No se pudo registrar el aviso enviado a %s", destino)


def _enviar(texto: str) -> None:
    if not getattr(settings, "NOTIFICACIONES_WHATSAPP", True):
        return
    for destino in _destinatarios():
        try:
            wa_id = evolution.enviar_texto(destino, texto)
        except Exception:
            logger.exception("No se pudo avisar al administrador (%s)", destino)
            continue
        _registrar_envio(destino, texto, wa_id)


def _edad(fecha_nacimiento) -> int | None:
    if not fecha_nacimiento:
        return None
    hoy = timezone.localdate()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def _datos_cita(cita) -> list[str]:
    lineas = [f"Paciente: {cita.paciente.nombres} {cita.paciente.apellidos}"]
    edad = _edad(cita.paciente.fecha_nacimiento)
    if edad is not None:
        lineas.append(f"Edad: {edad} años")
    lineas.extend([
        f"Teléfono: {cita.paciente.telefono or '(sin teléfono)'}",
        f"Tratamiento: {cita.tipo_trabajo.nombre}",
        f"Sede: {cita.sede.nombre}",
        f"Doctor: {cita.doctor.nombres} {cita.doctor.apellidos}",
        f"Fecha: {_fecha_con_dia(cita.fecha)} a las {cita.hora_inicio.strftime('%H:%M')}",
    ])
    return lineas


def notificar_cita_creada(cita) -> None:
    """Avisa al administrador los datos de una cita creada por el agente."""
    _enviar("\n".join(["Nueva cita agendada desde WhatsApp", *_datos_cita(cita)]))


def notificar_cita_cancelada(cita) -> None:
    """Avisa al administrador que el agente canceló una cita."""
    _enviar("\n".join(["Cita cancelada desde WhatsApp", *_datos_cita(cita)]))


def notificar_cita_modificada(cita, cambios: str = "") -> None:
    """Avisa al administrador que el agente cambió una cita."""
    lineas = ["Cita modificada desde WhatsApp", *_datos_cita(cita)]
    if cambios:
        lineas.append(f"Cambios: {cambios[:300]}")
    _enviar("\n".join(lineas))


def notificar_tratamiento_no_disponible(conversacion, motivo: str) -> None:
    """Avisa al administrador que un paciente pidió un tratamiento fuera del catálogo."""
    paciente = conversacion.paciente
    nombre = (
        f"{paciente.nombres} {paciente.apellidos}" if paciente else "Paciente sin registrar"
    )
    texto = (
        "Tratamiento no disponible en el catálogo\n"
        f"Paciente: {nombre}\n"
        f"Teléfono: {conversacion.telefono}\n"
        f"Tratamiento solicitado: {motivo or '(no especificado)'}\n"
        "El paciente espera que la clínica le contacte."
    )
    _enviar(texto)

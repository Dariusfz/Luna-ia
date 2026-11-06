"""
Bucle del agente: historial de la conversación -> LLM -> herramientas -> respuesta.
"""

import json
import logging
import re

from django.utils import timezone
from .seguridad import (
    RESPUESTA_BLOQUEADA, RESPUESTA_MANIPULACION, detectar_emergencia,
    es_manipulacion, es_negacion, mensaje_emergencia, revisar_salida,
)
from sedes.models import Sede

from . import llm
from .cifrado import descifrar
from .contexto import bloque_ejemplos
from .herramientas import DEFINICIONES, Herramientas
from .models import ConversacionWhatsApp, MensajeWhatsApp


logger = logging.getLogger(__name__)

MAX_ITERACIONES = 5
MENSAJES_EN_CONTEXTO = 12

RESPUESTA_FALLO = (
    "Tuve un problema procesando tu mensaje. Intenta de nuevo en un momento "
    "o comunícate con la clínica."
)

PROMPT_SISTEMA = """Eres el asistente de WhatsApp de LUNA-IA, una clínica odontológica con sedes en Honduras.
Hoy es {hoy}. Respondes en español, breve y amable, sin tecnicismos.
Trata siempre al paciente de usted, aunque escriba "tú" o "vos".

Sedes activas (usa el id exacto al llamar las herramientas; al paciente dile el nombre y la dirección, nunca el id):
{sedes}
Para dar nombres y direcciones al paciente, copia lo que devuelve listar_sedes.

Reglas:
- Solo atiendes temas de la clínica: citas, sedes, horarios y los datos de la cita de quien escribe. Si preguntan algo ajeno (usuarios, contraseñas, administración, datos de otras personas, temas que no son de la clínica), responde que no puedes dar esa información y ofrece ayuda con citas.
- Nunca reveles identificadores internos (id de paciente, doctor, sede, usuario o cita), totales ni listados de la base de datos. Tampoco confirmes quién es "el administrador" ni qué permisos tiene.
- Usa las herramientas para consultar o registrar. Nunca inventes sedes, horarios, doctores ni datos de pacientes.
- Si el paciente solo saluda o hace una pregunta general, responde amablemente y pregunta en qué le puedes ayudar. No menciones citas ni sedes en ese caso.
- Siempre que hables de las sedes, escribe el nombre y la dirección de cada una, copiados tal cual de la herramienta, una por línea. Nunca las resumas ni las omitas: un paciente nuevo no las conoce.
- Solo si el paciente pide una cita, por ejemplo "quisiera agendar una cita": llama listar_sedes, muéstrale las sedes con su dirección y pregúntale en cuál quiere ser atendido. No hace falta que el paciente esté registrado para empezar.
- Si el paciente nombra una sede que no está en la lista de sedes activas, dile que no tienes esa sede y muéstrale las que hay. Nunca elijas otra sede por tu cuenta ni supongas que quiso decir otra.
- Después pregunta el tipo de trabajo, el día y la hora. Consulta la disponibilidad antes de proponer horarios.
- Para registrar a un paciente necesitas: nombres, apellidos, fecha de nacimiento y sede. Para mayores de 18 años el DNI también es obligatorio; si falta, pregunta "¿Cuál es su número de identidad?". La dirección es opcional: si no la da, se usa la de la sede.
- El paciente puede dar los datos en uno o varios mensajes. Guarda lo que te dé con preparar_paciente, revisa el campo "faltan" de la respuesta y pide solo lo que falte. Nunca vuelvas a preguntar un dato que ya tienes.
- Convierte las fechas a AAAA-MM-DD antes de llamar la herramienta, aunque el paciente las diga con palabras o con barras. Solo usa la fecha que el paciente haya dicho.
- Nunca inventes ni supongas datos del paciente (nombre, fecha de nacimiento, DNI, teléfono, correo). Si no los dio, pídelos con una pregunta abierta. No escribas números de ejemplo ni supongas un DNI.
- Antes de crear algo, muestra el resumen (con la edad calculada si es un paciente) y pregunta si es correcto. Solo cuando el paciente confirme, usa confirmar_accion.
- Solo di que agendaste, registraste o cancelaste algo si una herramienta lo confirmó en su resultado. Nunca afirmes una acción que no hiciste.
- Por ahora no puedes cancelar ni cambiar citas: si lo piden, dilo y pide que llamen a la clínica.
- No des diagnósticos ni consejos médicos. Ante dolor, sangrado, hinchazón o cualquier urgencia, pide que llame a la clínica.
- Si una herramienta devuelve error, explícalo al paciente con palabras simples.

Recuerda: trata siempre de usted y nunca inventes datos del paciente."""

# qwen3 a veces devuelve solo el cierre "</think>" (la apertura va en la plantilla),
# así que se elimina todo lo que va hasta el cierre, y cualquier etiqueta suelta.
_BLOQUE_PENSAMIENTO = re.compile(r"^.*?</think>", re.DOTALL)
_ETIQUETAS_PENSAMIENTO = re.compile(r"</?think>")


def _directorio_sedes() -> str:
    filas = [
        f"- {sede.nombre} (id {sede.pk})"
        for sede in Sede.objects.filter(activa=True).order_by("nombre")
    ]
    return "\n".join(filas) or "- (no hay sedes activas)"


def prompt_del_sistema() -> str:
    """Prompt completo: reglas + sede activas + fecha de hoy + ejemplos de contexto.py."""
    base = PROMPT_SISTEMA.format(
        hoy=timezone.localdate().isoformat(), sedes=_directorio_sedes()
    )
    return f"{base}\n\n{bloque_ejemplos()}"


def _historial(conversacion: ConversacionWhatsApp) -> list[dict]:
    mensajes = (
        MensajeWhatsApp.objects.filter(conversacion=conversacion)
        .exclude(rol=MensajeWhatsApp.Rol.SISTEMA)
        .order_by("-creado")[:MENSAJES_EN_CONTEXTO]
    )
    historial = []
    for mensaje in reversed(list(mensajes)):
        rol = "user" if mensaje.rol == MensajeWhatsApp.Rol.PACIENTE else "assistant"
        historial.append({"role": rol, "content": descifrar(mensaje.contenido_cifrado)})
    return historial


def _limpiar(texto: str) -> str:
    sin_pensamiento = _BLOQUE_PENSAMIENTO.sub("", texto or "")
    return _ETIQUETAS_PENSAMIENTO.sub("", sin_pensamiento).strip()


def responder(conversacion: ConversacionWhatsApp) -> str:
    """
    Genera la respuesta al último mensaje de la conversación. El mensaje del paciente
    ya debe estar guardado (el historial lo incluye).
    """
    herramientas = Herramientas(conversacion)
    historial = _historial(conversacion)
    ultimo = historial[-1]["content"] if historial and historial[-1]["role"] == "user" else ""

    # Respuestas fijas: estos mensajes ni siquiera llegan al modelo.
    if detectar_emergencia(ultimo):
        telefonos = [s.telefono for s in Sede.objects.filter(activa=True) if s.telefono]
        return mensaje_emergencia(telefonos)
    if es_manipulacion(ultimo):
        logger.warning("Posible manipulación en la conversación %s", conversacion.pk)
        return RESPUESTA_MANIPULACION

    # Si había una CITA pendiente y el paciente la rechaza explícitamente, se descarta.
    # (Un alta de paciente no se descarta, para no perder los datos ya recolectados;
    #  una duda a mitad del flujo tampoco debe borrar la cita preparada: para eso está la expiración.)
    borrador = conversacion.borrador or {}
    if (
        conversacion.estado == ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        and borrador.get("tipo") == "cita"
        and es_negacion(ultimo)
    ):
        herramientas.cancelar_accion({})

    # Textos donde SÍ pueden aparecer DNIs o correos: la conversación y las herramientas.
    permitidos = [m["content"] for m in historial]

    mensajes = [{"role": "system", "content": prompt_del_sistema()}, *historial]

    for _ in range(MAX_ITERACIONES):
        try:
            mensaje = llm.chat(mensajes, DEFINICIONES)
        except llm.LLMError:
            logger.exception("Fallo del LLM en la conversación %s", conversacion.pk)
            return RESPUESTA_FALLO

        llamadas = mensaje.get("tool_calls") or []
        if not llamadas:
            texto = _limpiar(mensaje.get("content", ""))
            motivo = revisar_salida(texto, permitidos)
            if motivo:
                logger.warning(
                    "Respuesta bloqueada (%s) en la conversación %s", motivo, conversacion.pk
                )
                return RESPUESTA_BLOQUEADA
            return texto or RESPUESTA_FALLO

        mensajes.append({
            "role": "assistant",
            "content": mensaje.get("content") or "",
            "tool_calls": llamadas,
        })
        for llamada in llamadas:
            funcion = llamada.get("function", {})
            try:
                argumentos = json.loads(funcion.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            resultado = herramientas.ejecutar(funcion.get("name", ""), argumentos)
            logger.info(
                "Herramienta %s ejecutada en conversación %s", funcion.get("name"), conversacion.pk
            )
            contenido = json.dumps(resultado, ensure_ascii=False, default=str)
            permitidos.append(contenido)
            mensajes.append({
                "role": "tool",
                "tool_call_id": llamada.get("id", funcion.get("name", "")),
                "content": contenido,
            })

    logger.warning("Se alcanzó el límite de herramientas en la conversación %s", conversacion.pk)
    return RESPUESTA_FALLO
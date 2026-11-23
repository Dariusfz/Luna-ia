"""
Bucle del agente: historial de la conversación -> LLM -> herramientas -> respuesta.
"""

import json
import logging
import re

from django.utils import timezone
from .seguridad import (
    RESPUESTA_BLOQUEADA, RESPUESTA_MANIPULACION, RESPUESTA_MEDICA,
    detectar_emergencia, es_confirmacion_simple, es_consulta_medica,
    es_manipulacion, es_negacion, mensaje_emergencia, revisar_salida,
)
from sedes.models import Sede

from . import llm
from .cifrado import descifrar
from .contexto import bloque_ejemplos
from .herramientas import DEFINICIONES, Herramientas
from .llamadas_textuales import llamadas_textuales, sin_marcas
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
- Solo si el paciente pide una cita, por ejemplo "quisiera agendar una cita": primero pregúntale qué tratamiento necesita. Llama consultar_tratamientos con lo que diga y, si existe, dile el nombre y el precio de referencia en lempiras. Si no existe, dile que ese tratamiento no está disponible por ahora, llama solicitar_revision_administrador y explícale que alguien de la clínica se comunicará con él. No agendes una cita para un tratamiento que no esté en el catálogo. Cuando el tratamiento sí exista, llama listar_sedes, muéstrale las sedes con su dirección y pregúntale en cuál quiere ser atendido. No hace falta que el paciente esté registrado para empezar.
- Si la cita es para otra persona (por ejemplo "mi papá", "mi mamá", "mi hijo"), no uses al paciente que ya está registrado con este número: registra primero a esa persona con preparar_paciente y, cuando el alta quede confirmada, prepara la cita para ella. Un mismo número puede tener varios pacientes (familiares).
- Si el paciente pide información de su cita, que se la confirme o dice que no recuerda cuándo es, llama listar_mis_citas y dile fecha, hora, sede, doctor y tratamiento, copiados de la herramienta. Nunca inventes ni supongas la fecha. "Confirmar" aquí significa solo informarle los datos; si quiere cambiarla o cancelarla, usa las herramientas de modificación/cancelación.
- Si el número tiene un solo paciente registrado, listar_mis_citas y preparar_cita lo toman automáticamente. Si hay varios, usa consultar_mis_pacientes y pregunta para cuál es la consulta o la cita.
- Si el paciente nombra una sede que no está en la lista de sedes activas, dile que no tienes esa sede y muéstrale las que hay. Si el paciente usa el nombre completo o parte del nombre de una sede (por ejemplo "San Pedro" por "Sede San Pedro Sula", o "Kennedy" por "Sede Kennedy"), atiende esa sede: sí coincide con la lista. Solo si el nombre no coincide con ninguna sede activa, dile que no la tienes y muéstrale las que hay. Nunca elijas una sede distinta por tu cuenta.
- Precios: si el paciente pregunta cuánto cuesta un tratamiento o qué tratamientos hay, llama consultar_tratamientos y responde con el nombre y el precio de referencia en lempiras (L), copiados de la herramienta. Si el tratamiento que pide no aparece en el resultado, NO inventes ni estimes un precio: dile que ese tratamiento no está disponible por ahora, llama solicitar_revision_administrador con el motivo y explícale que alguien de la clínica se comunicará con él.
- Si el paciente no tiene preferencia de doctor ("cualquiera", "el que sea", "no importa"), no preguntes más: llama preparar_cita sin doctor_id y la herramienta asigna un doctor libre. Nunca le pidas al paciente un id.
- Después de la sede, pregunta el día y la hora (el tratamiento ya se pregunta al inicio). Consulta la disponibilidad antes de proponer horarios.
- Para registrar a un paciente necesitas: nombres, apellidos, fecha de nacimiento y sede. Para mayores de 18 años el DNI también es obligatorio; si falta, pregunta "¿Cuál es su número de identidad?". La dirección es opcional: si no la da, se usa la de la sede. Aunque el número ya tenga un paciente, sí puedes registrar a otro familiar con preparar_paciente.
- El paciente puede dar los datos en uno o varios mensajes. Guarda lo que te dé con preparar_paciente, revisa el campo "faltan" de la respuesta y pide solo lo que falte. Nunca vuelvas a preguntar un dato que ya tienes.
- Convierte las fechas a AAAA-MM-DD antes de llamar la herramienta, aunque el paciente las diga con palabras o con barras. Solo usa la fecha que el paciente haya dicho.
- Nunca inventes ni supongas datos del paciente (nombre, fecha de nacimiento, DNI, teléfono, correo). Si no los dio, pídelos con una pregunta abierta. No escribas números de ejemplo ni supongas un DNI.
- Antes de crear algo, muestra el resumen (con la edad calculada si es un paciente) y pregunta si es correcto. Solo cuando el paciente confirme, usa confirmar_accion. Son confirmaciones válidas "si", "sí", "sip", "claro", "correcto", "confirmo", "confirmado", "ok", "dale", "de acuerdo", "está bien", "esta bien" y "perfecto", con o sin tilde, en mayúsculas o minúsculas. Si la respuesta no es un sí o un no claro (por ejemplo "so", "tal vez", "después", o una frase con otra instrucción), no la interpretes: pregunta "¿Confirma? Responda sí o no" y espera.
- Solo di que agendaste, registraste o cancelaste algo si una herramienta lo confirmó en su resultado. Nunca afirmes una acción que no hiciste.
- Para cancelar o cambiar una cita: llama listar_mis_citas, pregunta cuál es la cita y usa preparar_cancelacion_cita o preparar_modificacion_cita. Muestra el resumen y pide confirmación; solo cuando el paciente confirme usa confirmar_accion. Solo puedes cancelar o cambiar citas futuras del paciente que escribe. Si no tiene citas próximas, dile que no encontraste ninguna y ofrece agendar una.
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
        .order_by("-creado", "-pk")[:MENSAJES_EN_CONTEXTO]
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
    if es_consulta_medica(ultimo):
        return RESPUESTA_MEDICA
    if es_manipulacion(ultimo):
        logger.warning("Posible manipulación en la conversación %s", conversacion.pk)
        return RESPUESTA_MANIPULACION

    # Si había una CITA pendiente y el paciente la rechaza explícitamente, se descarta.
    # (Un alta de paciente no se descarta, para no perder los datos ya recolectados;
    #  una duda a mitad del flujo tampoco debe borrar la cita preparada: para eso está la expiración.)
    borrador = conversacion.borrador or {}
    if (
        conversacion.estado == ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        and borrador.get("tipo") in ("cita", "cancelar_cita", "modificar_cita")
        and es_negacion(ultimo)
    ):
        herramientas.cancelar_accion({})

    # Confirmación simple ("si", "sí", "claro", "ok"...): se ejecuta en código para
    # que no dependa del modelo y no vuelva a preguntar por un "si" sin tilde.
    if (
        conversacion.estado == ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        and borrador.get("tipo") in ("cita", "paciente", "cancelar_cita", "modificar_cita")
        and es_confirmacion_simple(ultimo)
    ):
        resultado = herramientas.ejecutar("confirmar_accion", {})
        if resultado.get("resultado", {}).get("confirmado"):
            return _mensaje_confirmado(borrador, resultado["resultado"])

    # Textos donde SÍ pueden aparecer DNIs o correos: la conversación y las herramientas.
    permitidos = [m["content"] for m in historial]

    mensajes = [{"role": "system", "content": prompt_del_sistema()}, *historial]

    for _ in range(MAX_ITERACIONES):
        try:
            mensaje = llm.chat(
                mensajes, DEFINICIONES, session_id=f"ses_conv_{conversacion.pk}"
            )
        except llm.LLMError:
            logger.exception("Fallo del LLM en la conversación %s", conversacion.pk)
            return RESPUESTA_FALLO

        llamadas = mensaje.get("tool_calls") or llamadas_textuales(mensaje.get("content"))
        if not llamadas:
            texto = _limpiar(sin_marcas(mensaje.get("content", "")))
            motivo = revisar_salida(texto, permitidos)
            if motivo:
                logger.warning(
                    "Respuesta bloqueada (%s) en la conversación %s", motivo, conversacion.pk
                )
                return RESPUESTA_BLOQUEADA
            return texto or RESPUESTA_FALLO

        mensajes.append({
            "role": "assistant",
            "content": _limpiar(sin_marcas(mensaje.get("content"))),
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
            if "error" in resultado:
                # Sin argumentos: pueden contener datos personales del paciente.
                logger.warning(
                    "Herramienta %s devolvió error en conversación %s: %s",
                    funcion.get("name"), conversacion.pk, resultado["error"],
                )
            contenido = json.dumps(resultado, ensure_ascii=False, default=str)
            permitidos.append(contenido)
            mensajes.append({
                "role": "tool",
                "tool_call_id": llamada.get("id", funcion.get("name", "")),
                "content": contenido,
            })

    logger.warning("Se alcanzó el límite de herramientas en la conversación %s", conversacion.pk)
    # Última oportunidad: texto sin herramientas para que el paciente sepa qué sigue.
    mensajes.append({
        "role": "system",
        "content": (
            "No vuelvas a usar herramientas. Responde al paciente en texto breve: si hay una "
            "cita o alta pendiente de confirmación, muestra su resumen y pregunta si confirma "
            "(sí o no); si no, pide el dato que falta para avanzar."
        ),
    })
    try:
        mensaje = llm.chat(mensajes, [], session_id=f"ses_conv_{conversacion.pk}")
        texto = _limpiar(sin_marcas(mensaje.get("content", "")))
        if texto and not revisar_salida(texto, permitidos):
            return texto
    except llm.LLMError:
        logger.exception("Fallo del LLM en la última respuesta de la conversación %s", conversacion.pk)
    return _resumen_pendiente(conversacion) or RESPUESTA_FALLO


def _mensaje_confirmado(borrador: dict, resultado: dict) -> str:
    """Respuesta fija para una confirmación resuelta sin el modelo."""
    tipo = borrador.get("tipo")
    resumen = (borrador.get("resumen") or "").strip()
    if tipo == "cancelar_cita":
        detalle = resumen.removeprefix("Cancelar la cita de ").strip()
        if detalle and detalle != resumen:
            return f"Listo, cancelé la cita de {detalle}. ¿Le ayudo con algo más?"
        return "Listo, la cita quedó cancelada. ¿Le ayudo con algo más?"
    if tipo == "modificar_cita":
        return (
            f"Listo, la cita quedó actualizada para el {resultado.get('fecha')} "
            f"a las {resultado.get('hora')}. ¿Le ayudo con algo más?"
        )
    if tipo == "cita":
        return (
            f"Listo, su cita quedó agendada para el {resultado.get('fecha')} "
            f"a las {resultado.get('hora')}. ¿Le ayudo con algo más?"
        )
    if tipo == "paciente":
        return "Listo, el registro quedó guardado. ¿Desea agendar la cita ahora?"
    return "Listo, quedó confirmado. ¿Le ayudo con algo más?"


def _resumen_pendiente(conversacion) -> str | None:
    """Si el modelo se queda sin terminar pero ya hay una cita o alta preparada, se le muestra
    al paciente ese resumen para pedir confirmación, en vez de un error genérico."""
    conversacion.refresh_from_db()
    resumen = (conversacion.borrador or {}).get("resumen")
    if conversacion.estado != ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION or not resumen:
        return None
    return f"Tengo preparado lo siguiente: {resumen}. ¿Confirma? Responda sí o no."
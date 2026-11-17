"""
Asistente IA interno del ERP (plan §5.4).

Flujo: pregunta del personal -> LLM elige UNA consulta analítica predefinida y sus filtros
-> se ejecuta la vista de analítica con el usuario autenticado (permisos por sede aplicados
por el backend) -> el LLM redacta la respuesta con ese resultado, sin herramientas.

El modelo no escribe SQL, no elige columnas y no ve datos crudos: solo recibe los totales
que devuelven las vistas de analítica.
"""

import json
import logging
from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from api_agente import llm
from sedes.models import Sede
from users.permisos import filtrar_por_sede

from .views import (
    AtendidosMesView,
    CitasHoyView,
    PorHoraView,
    PorSedeView,
    PorServicioView,
)

logger = logging.getLogger(__name__)

MAX_LONGITUD_PREGUNTA = 500
PARAMETROS_PERMITIDOS = ("desde", "hasta", "mes", "sede")

_FECHA = "Fecha en formato AAAA-MM-DD."

HERRAMIENTAS = {
    "citas_hoy": {
        "vista": CitasHoyView.as_view(),
        "ruta": "/api/analitica/citas-hoy/",
        "descripcion": (
            "Citas de HOY agrupadas por estado (pendiente, confirmada, completada, cancelada). "
            "Úsala para preguntas sobre 'hoy' o 'el día de hoy'."
        ),
        "parametros": ["sede"],
    },
    "atendidos_mes": {
        "vista": AtendidosMesView.as_view(),
        "ruta": "/api/analitica/atendidos-mes/",
        "descripcion": (
            "Pacientes atendidos (citas completadas) por día de un mes. "
            "Úsala para 'cuántos pacientes se atendieron este mes' o en un mes concreto."
        ),
        "parametros": ["mes", "sede"],
    },
    "por_servicio": {
        "vista": PorServicioView.as_view(),
        "ruta": "/api/analitica/por-servicio/",
        "descripcion": (
            "Cantidad de citas por tipo de trabajo o tratamiento en un rango de fechas. "
            "Úsala para preguntas sobre tratamientos más solicitados o por servicio."
        ),
        "parametros": ["desde", "hasta", "sede"],
    },
    "por_hora": {
        "vista": PorHoraView.as_view(),
        "ruta": "/api/analitica/por-hora/",
        "descripcion": (
            "Cantidad de citas por hora de inicio en un rango de fechas. "
            "Úsala para preguntas sobre horas con más o menos citas."
        ),
        "parametros": ["desde", "hasta", "sede"],
    },
    "por_sede": {
        "vista": PorSedeView.as_view(),
        "ruta": "/api/analitica/por-sede/",
        "descripcion": (
            "Cantidad de citas por sede en un rango de fechas. "
            "Úsala para comparar sedes."
        ),
        "parametros": ["desde", "hasta"],
    },
}

DESCRIPCION_PARAMETROS = {
    "desde": f"Fecha inicial. {_FECHA}",
    "hasta": f"Fecha final. {_FECHA}",
    "mes": "Mes en formato AAAA-MM (por ejemplo 2026-03).",
    "sede": "ID numérico de la sede, copiado de la lista de sedes del prompt.",
}


def _definiciones() -> list[dict]:
    definiciones = []
    for nombre, config in HERRAMIENTAS.items():
        propiedades = {
            parametro: {"type": "string", "description": DESCRIPCION_PARAMETROS[parametro]}
            for parametro in config["parametros"]
        }
        definiciones.append(
            {
                "type": "function",
                "function": {
                    "name": nombre,
                    "description": config["descripcion"],
                    "parameters": {
                        "type": "object",
                        "properties": propiedades,
                        "additionalProperties": False,
                    },
                },
            }
        )
    return definiciones


def _sedes_visibles(usuario) -> str:
    sedes = filtrar_por_sede(
        Sede.objects.filter(activa=True), usuario, campo_sede="id"
    ).order_by("nombre")
    filas = [f"- {sede.nombre} (id {sede.pk})" for sede in sedes]
    return "\n".join(filas) or "- (no tienes sedes asignadas)"


def _prompt_sistema(usuario) -> str:
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    return f"""Eres el asistente interno de LUNA-IA, el sistema de una clínica odontológica en Honduras.
Hoy es {hoy.isoformat()} (ayer fue {ayer.isoformat()}). Respondes en español, breve y claro.

Respondes preguntas de métricas de la clínica usando las herramientas disponibles.
- Elige la herramienta que mejor responda la pregunta y llénala con los filtros que el usuario mencione.
- Convierte fechas relativas ("hoy", "ayer", "este mes", "la semana pasada") a AAAA-MM-DD o AAAA-MM según corresponda.
- Si no mencionan sede, no envíes sede (verás el consolidado de todas tus sedes).
- Si la pregunta no es sobre métricas de la clínica, responde que solo puedes ayudar con estadísticas de citas y atenciones, sin llamar herramientas.
- No inventes cifras: usa solo el resultado de la herramienta.

Sedes disponibles para este usuario:
{_sedes_visibles(usuario)}
"""


def _argumentos_seguros(argumentos) -> dict:
    """Solo se aceptan los parámetros conocidos, siempre como texto."""
    if not isinstance(argumentos, dict):
        return {}
    return {
        clave: str(valor)
        for clave, valor in argumentos.items()
        if clave in PARAMETROS_PERMITIDOS and valor not in (None, "")
    }


def ejecutar_consulta(nombre: str, argumentos: dict, usuario) -> tuple[int, dict]:
    """Ejecuta una consulta analítica como si la pidiera el propio usuario."""
    config = HERRAMIENTAS.get(nombre)
    if config is None:
        return status.HTTP_400_BAD_REQUEST, {"error": "Consulta desconocida."}
    parametros = {
        clave: valor
        for clave, valor in _argumentos_seguros(argumentos).items()
        if clave in config["parametros"]
    }
    peticion = APIRequestFactory().get(config["ruta"], parametros)
    force_authenticate(peticion, user=usuario)
    respuesta = config["vista"](peticion)
    return respuesta.status_code, respuesta.data


class AsistenteView(APIView):
    """POST /api/analitica/asistente/ con {"pregunta": "..."}."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        pregunta = str(request.data.get("pregunta", "") or "").strip()
        if not pregunta:
            return Response(
                {"pregunta": "Escribe una pregunta."}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(pregunta) > MAX_LONGITUD_PREGUNTA:
            return Response(
                {"pregunta": f"La pregunta no puede superar {MAX_LONGITUD_PREGUNTA} caracteres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mensajes = [
            {"role": "system", "content": _prompt_sistema(request.user)},
            {"role": "user", "content": pregunta},
        ]
        sesion = f"ses_asistente_u{request.user.pk}"

        try:
            mensaje = llm.chat(mensajes, _definiciones(), session_id=sesion)
        except llm.LLMError:
            logger.exception("Fallo del LLM en el asistente interno")
            return Response(
                {"detail": "El asistente no está disponible en este momento."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        llamadas = mensaje.get("tool_calls") or []
        if not llamadas:
            return Response(
                {"respuesta": (mensaje.get("content") or "").strip(), "grafica": None}
            )

        # Solo se ejecuta la primera consulta: una pregunta produce una gráfica.
        llamada = llamadas[0]
        funcion = llamada.get("function", {})
        try:
            argumentos = json.loads(funcion.get("arguments") or "{}")
        except json.JSONDecodeError:
            argumentos = {}
        codigo, datos = ejecutar_consulta(funcion.get("name", ""), argumentos, request.user)
        grafica = datos if codigo == status.HTTP_200_OK else None
        resultado = json.dumps(datos, ensure_ascii=False, default=str)

        mensajes.append(
            {"role": "assistant", "content": mensaje.get("content") or "", "tool_calls": [llamada]}
        )
        mensajes.append(
            {"role": "tool", "tool_call_id": llamada.get("id", ""), "content": resultado}
        )
        try:
            # Sin herramientas: el modelo solo redacta la respuesta con el resultado.
            final = llm.chat(mensajes, [], session_id=sesion)
        except llm.LLMError:
            logger.exception("Fallo del LLM al redactar la respuesta del asistente")
            return Response(
                {"detail": "El asistente no está disponible en este momento."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "respuesta": (final.get("content") or "").strip(),
                "grafica": grafica,
            }
        )

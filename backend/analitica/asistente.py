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

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from api_agente import llm
from api_agente.llamadas_textuales import llamadas_textuales, sin_marcas
from sedes.models import Sede
from users.permisos import filtrar_por_sede

from .models import ConversacionAsistente, MensajeAsistente
from . import estrategia, registros
from .politicas import consultas_permitidas, puede_consultar
from .views import (
    AtendidosMesView,
    CitasHoyView,
    IngresosView,
    PorHoraView,
    PorSedeView,
    PorServicioView,
)

logger = logging.getLogger(__name__)

MAX_LONGITUD_PREGUNTA = 500
# El modelo suele pedir en un mismo turno el total y sus desgloses (sede, doctor...).
MAX_LLAMADAS_POR_TURNO = 3

# Tipos que sabe pintar el frontend (`Asistente.tsx`).
TIPOS_GRAFICA = ("barras", "pastel", "puntos", "linea")

ETIQUETAS_ENTIDAD = {
    "atenciones": "Citas",
    "pacientes": "Pacientes",
    "doctores": "Doctores",
    "lista_espera": "Lista de espera",
    "pagos": "Cobros",
    "pagos_doctores": "Pagos a doctores",
    "jornadas_externas": "Jornadas",
    "personal": "Personal",
    "tipos_trabajo": "Tratamientos",
}

ETIQUETAS_AGRUPACION = {
    "sede": "Sede",
    "doctor": "Doctor",
    "estado": "Estado",
    "origen": "Origen",
    "tratamiento": "Tratamiento",
    "metodo": "Método de pago",
    "rol": "Rol",
    "activo": "Estado",
    "prioridad": "Prioridad",
    "lugar": "Lugar",
    "tipo": "Tipo",
}
PARAMETROS_PERMITIDOS = ("desde", "hasta", "mes", "sede", "grafica")

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
    "ingresos": {
        "vista": IngresosView.as_view(),
        "ruta": "/api/analitica/ingresos/",
        "descripcion": (
            "Dinero de la clínica en un rango de fechas: cobrado, por cobrar, comisión a "
            "doctores y ganancia neta (en lempiras). Úsala para preguntas sobre dinero, "
            "ingresos, cobros, caja, ganancias o cuánto se ha cobrado o hecho."
        ),
        "parametros": ["desde", "hasta", "sede"],
    },
}

# Módulo al que pertenece cada consulta, para explicarle al usuario qué puede consultar.
MODULO_DE_CONSULTA = {
    "citas_hoy": "Agenda: citas de hoy por estado",
    "atendidos_mes": "Atenciones: pacientes atendidos por mes",
    "por_servicio": "Tratamientos: citas por tipo de trabajo",
    "por_hora": "Agenda: citas por hora",
    "por_sede": "Sedes: comparación de citas entre sedes",
    "ingresos": "Caja: cobrado, por cobrar, comisiones y ganancia",
}

DESCRIPCION_PARAMETROS = {
    "desde": f"Fecha inicial. {_FECHA}",
    "hasta": f"Fecha final. {_FECHA}",
    "mes": "Mes en formato AAAA-MM (por ejemplo 2026-03).",
    "sede": "ID numérico de la sede, copiado de la lista de sedes del prompt.",
}


def _definiciones(usuario) -> list[dict]:
    """Solo las herramientas que el rol del usuario puede usar."""
    definiciones = []
    for nombre, config in HERRAMIENTAS.items():
        if not puede_consultar(usuario, nombre):
            continue
        propiedades = {
            parametro: {"type": "string", "description": DESCRIPCION_PARAMETROS[parametro]}
            for parametro in config["parametros"]
        }
        propiedades["grafica"] = {
            "type": "string",
            "enum": list(TIPOS_GRAFICA),
            "description": (
                "Tipo de gráfica que pidió el usuario (barras, pastel, puntos o linea). "
                "Omitir si no pidió una gráfica."
            ),
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
    herramienta_registros = registros.definicion_herramienta(usuario)
    if herramienta_registros:
        definiciones.append(herramienta_registros)
    herramienta_estrategia = estrategia.definicion_herramienta(usuario)
    if herramienta_estrategia:
        definiciones.append(herramienta_estrategia)
    return definiciones


def _sedes_visibles(usuario) -> str:
    sedes = filtrar_por_sede(
        Sede.objects.filter(activa=True), usuario, campo_sede="id"
    ).order_by("nombre")
    filas = [f"- {sede.nombre} (id {sede.pk})" for sede in sedes]
    return "\n".join(filas) or "- (no tienes sedes asignadas)"


def _modulos_disponibles(usuario) -> str:
    lineas = [
        f"- {MODULO_DE_CONSULTA[nombre]}"
        for nombre in HERRAMIENTAS
        if nombre in consultas_permitidas(usuario)
    ]
    lineas += [
        f"- Registros ({nombre}): {registros.ENTIDADES[nombre].descripcion}"
        for nombre in sorted(registros.entidades_permitidas(usuario))
    ]
    return "\n".join(lineas) or "- (ninguno: tu rol no tiene consultas habilitadas)"


def _prompt_sistema(usuario) -> str:
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)
    return f"""Eres el asistente interno de LUNA-IA, el sistema de una clínica odontológica en Honduras.
Hoy es {hoy.isoformat()} (ayer fue {ayer.isoformat()}). Respondes en español, breve y claro.

Respondes preguntas sobre la clínica usando SOLO las herramientas que tienes disponibles.
Módulos a los que este usuario tiene acceso:
{_modulos_disponibles(usuario)}

- Elige la herramienta que mejor responda la pregunta y llénala con los filtros que el usuario mencione.
- Para contar, buscar o listar registros (pacientes, doctores, especialidades, tratamientos, sedes, citas, lista de espera, pagos o personal) usa consultar_registros. Por ejemplo, "cuántos pacientes se llaman Carlos" es entidad pacientes con filtro nombre "Carlos". Si el resultado tiene más registros que los mostrados, dilo.
- Para las citas de un día concreto (hoy, mañana, el 25 de noviembre) usa el filtro "fecha" de atenciones (AAAA-MM-DD). Para un rango usa "fecha_desde" y "fecha_hasta". No uses "mes" si el usuario pide un solo día.
- Puedes pedir varias consultas en la misma respuesta: por ejemplo, el total de atenciones con filtro "fecha", el mismo total con agrupar_por "sede" y con agrupar_por "doctor". Se ejecutan todas y después redactas con todos los resultados; úsalas para responder preguntas de varias partes (cuántas, en qué sedes y qué doctores).
- Responde con todos los datos que devuelva la herramienta (nombres, fechas, montos, estados), sin resumirlos de más. Nunca muestres identificadores internos.
- Formato: texto natural, breve y ordenado, en español, con una idea por línea. Usa listas con "- " cuando enumeres. Puedes usar **negrita** solo para resaltar totales, fechas y nombres clave (el sistema la muestra en negrita). No uses tablas, encabezados con "#", bloques de código ni asteriscos sueltos.
- Si el usuario pide una gráfica, un gráfico, pastel, barras, puntos o línea: usa consultar_registros con agrupar_por (por ejemplo sede, doctor, estado o tratamiento) y añade el argumento "grafica" con el tipo pedido (si no dice el tipo, usa "barras"). También puedes pasar "grafica" a las consultas analíticas para cambiar el tipo. La gráfica se dibuja con el resultado de la herramienta: nunca inventes valores; en el texto resume lo que muestra.
- Para "este mes", "en octubre", etc., usa el filtro "mes" (AAAA-MM) en lugar de fechas: cuenta el mes completo, incluidas las fechas futuras. Hoy es {hoy.isoformat()}, así que "este mes" es {hoy.strftime('%Y-%m')}.
- Para planes estratégicos, análisis, proyecciones, recomendaciones o "qué tratamientos conviene impulsar", usa analisis_estrategico. Estructura la respuesta en: 1) Diagnóstico con cifras (pacientes atendidos por mes, citas, cancelaciones, tendencias); 2) Proyección del próximo mes, indicando que es una estimación; 3) Tratamientos que crecen y los que bajan, y qué conviene promover o ajustar; 4) Recomendaciones priorizadas y concretas (horarios pico, carga de doctores, sedes, lista de espera); 5) Riesgos. Todo debe salir de los datos del resultado: si una sección no aparece en el resultado, no hables de ese tema.
- Para "cuántas citas": el número es el campo "total" del resultado, tal cual. Incluye todas las citas (también canceladas) y desglósalas por estado (pendiente, confirmada, completada, cancelada). No excluyas ninguna salvo que el usuario lo pida.
- Para citas creadas por el agente de WhatsApp usa origen "agente_whatsapp" en consultar_registros.
- Convierte fechas relativas ("hoy", "ayer", "este mes", "la semana pasada") a AAAA-MM-DD o AAAA-MM según corresponda.
- Si no mencionan sede, no envíes sede (verás el consolidado de tus sedes).
- Si la pregunta pide información de un módulo que no está en la lista de arriba, responde solo: "No tienes acceso a esa información con tu rol." No des cifras, no supongas datos y no sugieras cómo obtenerlos.
- Si la pregunta no es sobre la clínica, dilo y explica brevemente en qué sí puedes ayudar.
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
    if nombre == registros.NOMBRE_HERRAMIENTA:
        return registros.ejecutar(usuario, argumentos)
    if nombre == estrategia.NOMBRE_HERRAMIENTA:
        return estrategia.ejecutar(usuario, argumentos)
    config = HERRAMIENTAS.get(nombre)
    if config is None:
        return status.HTTP_400_BAD_REQUEST, {"error": "Consulta desconocida."}
    if not puede_consultar(usuario, nombre):
        return status.HTTP_403_FORBIDDEN, {
            "error": "Tu rol no tiene acceso a esta información."
        }
    parametros = {
        clave: valor
        for clave, valor in _argumentos_seguros(argumentos).items()
        if clave in config["parametros"]
    }
    peticion = APIRequestFactory().get(config["ruta"], parametros)
    force_authenticate(peticion, user=usuario)
    respuesta = config["vista"](peticion)
    return respuesta.status_code, respuesta.data


MENSAJES_HISTORIAL = 10

# Algunos modelos escriben la llamada a la herramienta como texto con marcas DSML en
# lugar de devolver una llamada estructurada. El parseo es compartido con el agente de
# WhatsApp (`api_agente.llamadas_textuales`); aquí se mantienen los alias locales.
_llamadas_textuales = llamadas_textuales
_sin_marcas = sin_marcas


def _texto_de_respaldo(datos) -> str:
    """
    Respuesta armada con el resultado de la consulta, cuando el modelo no redacta texto
    utilizable. Así el usuario siempre recibe el dato aunque la redacción falle.
    Acepta un resultado o la lista de resultados de varias consultas.
    """
    if isinstance(datos, (list, tuple)):
        partes = []
        for dato in datos:
            if not isinstance(dato, dict) or "error" in dato:
                continue
            texto = _texto_de_respaldo(dato)
            if texto not in partes:
                partes.append(texto)
        return "\n\n".join(partes) or "No pude obtener esa información. Intenta preguntarlo de otra forma."
    if not isinstance(datos, dict) or "error" in datos:
        return "No pude obtener esa información. Intenta preguntarlo de otra forma."
    if "grupos" in datos:
        lineas = [f"- {grupo['valor']}: {grupo['cantidad']}" for grupo in datos["grupos"]]
        return f"Total: {datos['total']}.\n" + "\n".join(lineas)
    if "registros" in datos:
        cabecera = f"Encontré {datos['total']} registro(s) en {datos['entidad']}."
        filas = [
            f"{indice}. " + " · ".join(str(v) for v in fila.values() if v not in (None, ""))
            for indice, fila in enumerate(datos["registros"], start=1)
        ]
        return "\n".join([cabecera, *filas])
    if "tipo_grafica" in datos:
        return f"{datos['titulo']}: total {datos['total']}."
    if "secciones" in datos:
        return "No pude redactar el análisis en este momento. Intenta pedirlo de nuevo."
    return "No pude completar la consulta. Intenta preguntarlo de otra forma."


def _historial(conversacion) -> list[dict]:
    """Últimos mensajes de la conversación, solo texto, para dar contexto al modelo."""
    if conversacion is None:
        return []
    ultimos = list(conversacion.mensajes.order_by("-creado", "-id")[:MENSAJES_HISTORIAL])
    return [
        {
            "role": "user" if mensaje.rol == MensajeAsistente.Rol.USUARIO else "assistant",
            "content": mensaje.texto,
        }
        for mensaje in reversed(ultimos)
    ]


def _responder_y_guardar(usuario, conversacion, pregunta, texto, grafica) -> Response:
    """Guarda pregunta y respuesta solo si el LLM respondió (así no quedan preguntas huérfanas)."""
    with transaction.atomic():
        if conversacion is None:
            conversacion = ConversacionAsistente.objects.create(
                usuario=usuario, titulo=pregunta[:60]
            )
        conversacion.mensajes.create(rol=MensajeAsistente.Rol.USUARIO, texto=pregunta)
        conversacion.mensajes.create(
            rol=MensajeAsistente.Rol.ASISTENTE, texto=texto, grafica=grafica
        )
        conversacion.save(update_fields=["actualizada"])
    return Response(
        {"conversacion": conversacion.pk, "respuesta": texto, "grafica": grafica}
    )


def _grafica_desde_grupos(datos: dict, tipo: str, argumentos: dict) -> dict | None:
    """Convierte los grupos de consultar_registros en el formato de gráfica del frontend."""
    grupos = datos.get("grupos") or []
    if not grupos:
        return None
    filtros = argumentos.get("filtros") or {}
    if isinstance(filtros, str):
        try:
            filtros = json.loads(filtros)
        except json.JSONDecodeError:
            filtros = {}
    if not isinstance(filtros, dict):
        filtros = {}
    entidad = datos.get("entidad", "")
    agrupado = datos.get("agrupado_por", "")
    desde = (
        filtros.get("fecha")
        or filtros.get("fecha_desde")
        or filtros.get("desde")
        or filtros.get("mes")
        or ""
    )
    hasta = (
        filtros.get("fecha")
        or filtros.get("fecha_hasta")
        or filtros.get("hasta")
        or filtros.get("mes")
        or ""
    )
    return {
        "titulo": (
            f"{ETIQUETAS_ENTIDAD.get(entidad, entidad.title())} por "
            f"{ETIQUETAS_AGRUPACION.get(agrupado, agrupado)}"
        ),
        "tipo_grafica": tipo,
        "ejes": {"x": ETIQUETAS_AGRUPACION.get(agrupado, agrupado), "y": "Cantidad"},
        "datos": [
            {"etiqueta": str(grupo.get("valor") or "Sin dato"), "valor": grupo.get("cantidad", 0)}
            for grupo in grupos
        ],
        "total": datos.get("total", 0),
        "filtros": {"desde": str(desde), "hasta": str(hasta), "sede": None},
    }


class AsistenteView(APIView):
    """
    POST /api/analitica/asistente/ con {"pregunta": "...", "conversacion": id (opcional)}.
    Sin `conversacion` se crea una conversación nueva. Las conversaciones son privadas.
    """

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

        id_conversacion = request.data.get("conversacion")
        conversacion = None
        if id_conversacion not in (None, ""):
            if not str(id_conversacion).isdigit():
                return Response(
                    {"conversacion": "Indica una conversación válida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            conversacion = ConversacionAsistente.objects.filter(
                usuario=request.user, pk=int(id_conversacion)
            ).first()
            if conversacion is None:
                return Response(
                    {"detail": "La conversación no existe."}, status=status.HTTP_404_NOT_FOUND
                )

        mensajes = [
            {"role": "system", "content": _prompt_sistema(request.user)},
            *_historial(conversacion),
            {"role": "user", "content": pregunta},
        ]
        sesion = f"ses_asistente_u{request.user.pk}"

        try:
            mensaje = llm.chat(mensajes, _definiciones(request.user), session_id=sesion)
        except llm.LLMError:
            logger.exception("Fallo del LLM en el asistente interno")
            return Response(
                {"detail": "El asistente no está disponible en este momento."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        llamadas = mensaje.get("tool_calls") or _llamadas_textuales(mensaje.get("content"))
        if not llamadas:
            return _responder_y_guardar(
                request.user,
                conversacion,
                pregunta,
                _sin_marcas(mensaje.get("content")),
                None,
            )

        # El modelo puede pedir varias consultas en el mismo turno (p. ej. el total, el
        # desglose por sede y el desglose por doctor). Se ejecutan todas y luego redacta.
        llamadas = llamadas[:MAX_LLAMADAS_POR_TURNO]
        mensajes.append(
            {
                "role": "assistant",
                "content": _sin_marcas(mensaje.get("content")),
                "tool_calls": llamadas,
            }
        )
        grafica = None
        resultados: list[dict] = []
        for llamada in llamadas:
            funcion = llamada.get("function", {})
            try:
                argumentos = json.loads(funcion.get("arguments") or "{}")
            except json.JSONDecodeError:
                argumentos = {}
            codigo, datos = ejecutar_consulta(funcion.get("name", ""), argumentos, request.user)
            tipo_pedido = str(argumentos.get("grafica") or "").lower()
            if codigo == status.HTTP_200_OK and isinstance(datos, dict):
                if tipo_pedido in TIPOS_GRAFICA and "tipo_grafica" in datos:
                    # El usuario pidió otro tipo (pastel, puntos...): se respeta.
                    datos["tipo_grafica"] = tipo_pedido
                if grafica is None and "tipo_grafica" in datos:
                    grafica = datos
                elif grafica is None and tipo_pedido in TIPOS_GRAFICA and datos.get("grupos"):
                    grafica = _grafica_desde_grupos(datos, tipo_pedido, argumentos)
            resultados.append(datos)
            mensajes.append(
                {
                    "role": "tool",
                    "tool_call_id": llamada.get("id", ""),
                    "content": json.dumps(datos, ensure_ascii=False, default=str),
                }
            )
        try:
            # Sin herramientas: el modelo solo redacta la respuesta con los resultados.
            final = llm.chat(mensajes, [], session_id=sesion)
        except llm.LLMError:
            logger.exception("Fallo del LLM al redactar la respuesta del asistente")
            return Response(
                {"detail": "El asistente no está disponible en este momento."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        texto_final = _sin_marcas(final.get("content")) or _texto_de_respaldo(resultados)
        return _responder_y_guardar(request.user, conversacion, pregunta, texto_final, grafica)


class ConversacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversacionAsistente
        fields = ["id", "titulo", "creada", "actualizada"]


class MensajeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MensajeAsistente
        fields = ["id", "rol", "texto", "grafica", "creado"]


class ConversacionDetalleSerializer(ConversacionSerializer):
    mensajes = MensajeSerializer(many=True, read_only=True)

    class Meta(ConversacionSerializer.Meta):
        fields = [*ConversacionSerializer.Meta.fields, "mensajes"]


class ConversacionesView(generics.ListAPIView):
    """Lista las conversaciones del usuario, la más reciente primero."""

    serializer_class = ConversacionSerializer

    def get_queryset(self):
        return ConversacionAsistente.objects.filter(usuario=self.request.user)


class ConversacionDetalleView(generics.RetrieveDestroyAPIView):
    """Ver los mensajes de una conversación propia, o borrarla."""

    serializer_class = ConversacionDetalleSerializer

    def get_queryset(self):
        return (
            ConversacionAsistente.objects.filter(usuario=self.request.user)
            .prefetch_related("mensajes")
        )

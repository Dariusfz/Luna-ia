"""
Panel del agente de WhatsApp para el ERP (plan §7.12 y §15.4).

Estos endpoints son para el personal de la clínica (admin y recepción), no para el
agente: usan la sesión normal del ERP. Permiten ver las conversaciones del agente,
leer los mensajes descifrados, pausar/reactivar el agente en un hilo y consultar
métricas de uso del agente.

Las conversaciones y sus mensajes contienen datos personales, así que:
- solo entran roles operativos (admin y recepcionista);
- la recepcionista solo ve las conversaciones de sus sedes (o sin sede asignada);
- el contenido siempre se descifra al leerlo y nunca se expone el ciphertext.
"""

from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.generics import ListAPIView, RetrieveAPIView, UpdateAPIView
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from agenda.models import Atencion
from users.models import Usuario
from users.permisos import es_admin, filtrar_por_sede

from .cifrado import descifrar
from .models import ConversacionWhatsApp, MensajeWhatsApp

TEXTO_NO_DESCIFRABLE = "[No se pudo descifrar el mensaje]"
MAX_MENSAJES_DETALLE = 300
DIAS_MENSAJES = 14


class PuedeGestionarAgente(BasePermission):
    """Admin o recepción: son quienes atienden los hilos de WhatsApp."""

    message = "Solo el administrador o recepción pueden gestionar el agente."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(
            usuario
            and usuario.is_authenticated
            and (es_admin(usuario) or usuario.rol == Usuario.Rol.RECEPCIONISTA)
        )


def _conversaciones_visibles(usuario):
    """Admin ve todo; recepción, las conversaciones de sus sedes y las aún sin sede."""
    consulta = ConversacionWhatsApp.objects.select_related("paciente", "sede")
    if es_admin(usuario):
        return consulta
    return consulta.filter(
        Q(sede__in=usuario.sedes.all()) | Q(sede__isnull=True)
    )


def _con_anotaciones(consulta):
    """Añade el total de mensajes y una vista previa del último mensaje."""
    ultimo = MensajeWhatsApp.objects.filter(conversacion=OuterRef("pk")).order_by(
        "-creado", "-pk"
    )
    return consulta.annotate(
        total_mensajes=Count("mensajes"),
        ultimo_contenido=Subquery(ultimo.values("contenido_cifrado")[:1]),
        ultimo_rol_anotado=Subquery(ultimo.values("rol")[:1]),
    )


def _descifrar_seguro(contenido):
    try:
        return descifrar(contenido)
    except Exception:  # clave distinta o dato corrupto: no romper el panel
        return TEXTO_NO_DESCIFRABLE


class MensajePanelSerializer(serializers.ModelSerializer):
    texto = serializers.SerializerMethodField()

    class Meta:
        model = MensajeWhatsApp
        fields = ["id", "rol", "tipo", "texto", "creado"]

    def get_texto(self, obj):
        return _descifrar_seguro(obj.contenido_cifrado)


class ConversacionPanelSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.SerializerMethodField()
    total_mensajes = serializers.SerializerMethodField()
    ultimo_mensaje = serializers.SerializerMethodField()
    ultimo_rol = serializers.SerializerMethodField()

    class Meta:
        model = ConversacionWhatsApp
        fields = [
            "id",
            "telefono",
            "paciente",
            "paciente_nombre",
            "sede",
            "sede_nombre",
            "estado",
            "agente_activo",
            "creada",
            "ultima_actividad",
            "total_mensajes",
            "ultimo_mensaje",
            "ultimo_rol",
        ]

    def get_paciente_nombre(self, obj):
        if obj.paciente is None:
            return ""
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}".strip()

    def get_sede_nombre(self, obj):
        return obj.sede.nombre if obj.sede_id else None

    def get_total_mensajes(self, obj):
        anotado = getattr(obj, "total_mensajes", None)
        if anotado is not None:
            return anotado
        return obj.mensajes.count()

    def get_ultimo_mensaje(self, obj):
        contenido = getattr(obj, "ultimo_contenido", None)
        if contenido is None:
            ultimo = obj.mensajes.order_by("-creado", "-pk").only("contenido_cifrado").first()
            contenido = ultimo.contenido_cifrado if ultimo else None
        if not contenido:
            return ""
        return _descifrar_seguro(contenido)[:140]

    def get_ultimo_rol(self, obj):
        rol = getattr(obj, "ultimo_rol_anotado", "")
        if rol:
            return rol
        ultimo = obj.mensajes.order_by("-creado", "-pk").only("rol").first()
        return ultimo.rol if ultimo else ""


class DetalleConversacionPanelSerializer(ConversacionPanelSerializer):
    mensajes = serializers.SerializerMethodField()

    class Meta(ConversacionPanelSerializer.Meta):
        fields = [*ConversacionPanelSerializer.Meta.fields, "mensajes"]

    def get_mensajes(self, obj):
        # Los últimos MAX_MENSAJES_DETALLE, del más antiguo al más reciente.
        ultimos = list(obj.mensajes.order_by("-creado", "-pk")[:MAX_MENSAJES_DETALLE])
        ultimos.reverse()
        return MensajePanelSerializer(ultimos, many=True).data


class ActualizarAgenteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversacionWhatsApp
        fields = ["id", "agente_activo"]
        read_only_fields = ["id"]


class ConversacionesPanelView(ListAPIView):
    """Lista paginada de conversaciones del agente, la más reciente primero."""

    permission_classes = [PuedeGestionarAgente]
    serializer_class = ConversacionPanelSerializer

    def get_queryset(self):
        consulta = _con_anotaciones(_conversaciones_visibles(self.request.user))
        parametros = self.request.query_params

        texto = (parametros.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(telefono__icontains=texto)
                | Q(paciente__nombres__icontains=texto)
                | Q(paciente__apellidos__icontains=texto)
            )

        activo = parametros.get("agente_activo")
        if activo in ("true", "false"):
            consulta = consulta.filter(agente_activo=(activo == "true"))

        estado = parametros.get("estado")
        if estado in dict(ConversacionWhatsApp.Estado.choices):
            consulta = consulta.filter(estado=estado)

        sede = parametros.get("sede")
        if sede and str(sede).isdigit():
            consulta = consulta.filter(sede_id=int(sede))

        return consulta.order_by("-ultima_actividad", "-pk")


class ConversacionPanelDetalleView(RetrieveAPIView):
    permission_classes = [PuedeGestionarAgente]
    serializer_class = DetalleConversacionPanelSerializer

    def get_queryset(self):
        return _con_anotaciones(_conversaciones_visibles(self.request.user))


class ConversacionPanelActualizarView(UpdateAPIView):
    """Pausa o reactiva el agente en un hilo (solo cambia `agente_activo`)."""

    http_method_names = ["patch"]
    permission_classes = [PuedeGestionarAgente]
    serializer_class = ActualizarAgenteSerializer

    def get_queryset(self):
        return _conversaciones_visibles(self.request.user)


class ResumenAgenteView(APIView):
    """Métricas de uso del agente de WhatsApp para el panel y el informe."""

    permission_classes = [PuedeGestionarAgente]

    def get(self, request):
        usuario = request.user
        hoy = timezone.localdate()
        inicio_mes = hoy.replace(day=1)
        conversaciones = _conversaciones_visibles(usuario)

        total = conversaciones.count()
        activas = conversaciones.filter(agente_activo=True).count()
        pausadas = total - activas
        nuevas_hoy = conversaciones.filter(creada__date=hoy).count()

        mensajes = MensajeWhatsApp.objects.filter(conversacion__in=conversaciones)
        mensajes_hoy = mensajes.filter(creado__date=hoy)
        por_rol_hoy = {
            fila["rol"]: fila["total"]
            for fila in mensajes_hoy.values("rol").annotate(total=Count("id"))
        }

        desde = hoy - timedelta(days=DIAS_MENSAJES - 1)
        por_dia = {}
        filas = (
            mensajes.filter(creado__date__gte=desde)
            .annotate(dia=TruncDate("creado"))
            .values("dia", "rol")
            .annotate(total=Count("id"))
        )
        for fila in filas:
            dia = fila["dia"].isoformat()
            registro = por_dia.setdefault(
                dia, {"fecha": dia, "total": 0, "paciente": 0, "agente": 0, "humano": 0}
            )
            registro[fila["rol"]] = registro.get(fila["rol"], 0) + fila["total"]
            registro["total"] += fila["total"]

        serie = []
        for i in range(DIAS_MENSAJES):
            dia = (desde + timedelta(days=i)).isoformat()
            serie.append(
                por_dia.get(
                    dia, {"fecha": dia, "total": 0, "paciente": 0, "agente": 0, "humano": 0}
                )
            )

        citas = filtrar_por_sede(Atencion.objects.all(), usuario)
        citas_mes = citas.filter(creada__date__gte=inicio_mes)
        citas_agente_mes = citas_mes.filter(origen=Atencion.Origen.AGENTE_WHATSAPP)
        citas_agente_hoy = citas.filter(
            origen=Atencion.Origen.AGENTE_WHATSAPP, creada__date=hoy
        )
        total_citas_mes = citas_mes.count()
        total_agente_mes = citas_agente_mes.count()

        return Response(
            {
                "conversaciones": {
                    "total": total,
                    "activas": activas,
                    "pausadas": pausadas,
                    "nuevas_hoy": nuevas_hoy,
                },
                "mensajes": {
                    "hoy": mensajes_hoy.count(),
                    "paciente_hoy": por_rol_hoy.get(MensajeWhatsApp.Rol.PACIENTE, 0),
                    "agente_hoy": por_rol_hoy.get(MensajeWhatsApp.Rol.AGENTE, 0),
                    "humano_hoy": por_rol_hoy.get(MensajeWhatsApp.Rol.HUMANO, 0),
                },
                "citas": {
                    "agente_hoy": citas_agente_hoy.count(),
                    "agente_mes": total_agente_mes,
                    "total_mes": total_citas_mes,
                    "porcentaje_agente": (
                        round(total_agente_mes * 100 / total_citas_mes, 1)
                        if total_citas_mes
                        else 0
                    ),
                },
                "mensajes_por_dia": serie,
            }
        )

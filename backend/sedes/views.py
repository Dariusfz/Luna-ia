from django.db.models import Q
from rest_framework import viewsets

from users.permisos import LecturaTodosEscrituraAdmin, es_admin, filtrar_por_sede

from .models import Feriado, HorarioSede, LugarExterno, Sede
from .serializers import (
    FeriadoSerializer,
    HorarioSedeSerializer,
    LugarExternoSerializer,
    SedeSerializer,
)


class SedeViewSet(viewsets.ModelViewSet):
    """
    Sedes de la clínica. Todos ven las sedes a las que tienen acceso; solo el admin
    crea o edita. No se borran: se desactivan.
    """

    serializer_class = SedeSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        if not es_admin(user):
            return user.sedes.filter(activa=True)
        qs = Sede.objects.all()
        activa = self.request.query_params.get("activa", "todas")
        if activa == "true":
            qs = qs.filter(activa=True)
        elif activa == "false":
            qs = qs.filter(activa=False)
        return qs


class LugarExternoViewSet(viewsets.ReadOnlyModelViewSet):
    """Lugares externos para registrar jornadas. Solo el admin los administra en el admin de Django."""

    serializer_class = LugarExternoSerializer
    queryset = LugarExterno.objects.filter(activo=True)


class HorarioSedeViewSet(viewsets.ModelViewSet):
    """Turnos semanales de cada sede. Lectura para todos; cambios solo admin."""

    serializer_class = HorarioSedeSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    pagination_class = None

    def get_queryset(self):
        qs = HorarioSede.objects.select_related("sede")
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        sede = self.request.query_params.get("sede", "")
        if sede.isdigit():
            qs = qs.filter(sede_id=int(sede))
        return qs


class FeriadoViewSet(viewsets.ModelViewSet):
    """
    Feriados por sede (o para todas con `sede` vacía). Lectura para todos;
    cambios solo admin. Los feriados globales los ve cualquier usuario.
    """

    serializer_class = FeriadoSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    pagination_class = None

    def get_queryset(self):
        qs = Feriado.objects.select_related("sede")
        user = self.request.user
        if not es_admin(user):
            if not (user and user.is_authenticated):
                return qs.none()
            qs = qs.filter(Q(sede__in=user.sedes.all()) | Q(sede__isnull=True))
        sede = self.request.query_params.get("sede", "")
        if sede.isdigit():
            qs = qs.filter(Q(sede_id=int(sede)) | Q(sede__isnull=True))
        return qs

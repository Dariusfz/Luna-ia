from rest_framework import viewsets

from users.permisos import LecturaTodosEscrituraAdmin, es_admin

from .models import Especialidad, TipoTrabajo
from .serializers import EspecialidadSerializer, TipoTrabajoSerializer


class TipoTrabajoViewSet(viewsets.ModelViewSet):
    """
    Catálogo de tipos de trabajo. Todos ven los activos; solo el admin crea o edita.
    No se borran: se desactivan (campo activo) para no romper el historial.
    """

    serializer_class = TipoTrabajoSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = TipoTrabajo.objects.all()
        if not es_admin(self.request.user):
            return qs.filter(activo=True)
        # El admin puede filtrar por estado: true | false | todos (por defecto, todos).
        if self.action == "list":
            activo = self.request.query_params.get("activo", "todos")
            if activo == "true":
                qs = qs.filter(activo=True)
            elif activo == "false":
                qs = qs.filter(activo=False)
        return qs


class EspecialidadViewSet(viewsets.ModelViewSet):
    """Especialidades de los doctores. Todos ven las activas; solo el admin crea o edita."""

    serializer_class = EspecialidadSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = Especialidad.objects.all()
        if not es_admin(self.request.user):
            return qs.filter(activo=True)
        if self.action == "list":
            activo = self.request.query_params.get("activo", "todos")
            if activo == "true":
                qs = qs.filter(activo=True)
            elif activo == "false":
                qs = qs.filter(activo=False)
        return qs

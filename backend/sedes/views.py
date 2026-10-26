from rest_framework import viewsets

from users.permisos import LecturaTodosEscrituraAdmin, es_admin

from .models import LugarExterno, Sede
from .serializers import LugarExternoSerializer, SedeSerializer


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

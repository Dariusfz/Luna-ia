from rest_framework import viewsets

from users.permisos import EsAdmin, filtrar_por_sede

from .models import Atencion, JornadaExterna
from .serializers import AtencionSerializer, JornadaExternaSerializer

METODOS_SIN_BORRADO = ["get", "post", "put", "patch", "head", "options"]


class AtencionViewSet(viewsets.ModelViewSet):
    """
    Atenciones de las sedes del usuario. El admin ve todas. No se borran.

    Filtros del listado: sede, doctor, desde, hasta (fechas AAAA-MM-DD).
    """

    serializer_class = AtencionSerializer
    http_method_names = METODOS_SIN_BORRADO

    def get_queryset(self):
        qs = Atencion.objects.select_related("sede", "doctor", "paciente", "tipo_trabajo")
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("sede", "").isdigit():
            qs = qs.filter(sede_id=int(params["sede"]))
        if params.get("doctor", "").isdigit():
            qs = qs.filter(doctor_id=int(params["doctor"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        if params.get("estado"):
            estados = [
                estado
                for estado in params["estado"].split(",")
                if estado in Atencion.Estado.values
            ]
            qs = qs.filter(estado__in=estados)
        return qs


class JornadaExternaViewSet(viewsets.ModelViewSet):
    """Trabajos fuera de la clínica. Solo el administrador. No guardan datos de pacientes."""

    serializer_class = JornadaExternaSerializer
    permission_classes = [EsAdmin]
    http_method_names = METODOS_SIN_BORRADO

    def get_queryset(self):
        return JornadaExterna.objects.select_related("doctor", "lugar", "tipo_trabajo")

from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from users.permisos import filtrar_por_sede

from .models import HistoriaClinica, Odontograma, Paciente
from .querysets import pacientes_visibles
from .serializers import HistoriaClinicaSerializer, OdontogramaSerializer, PacienteSerializer


class PacienteViewSet(viewsets.ModelViewSet):
    """
    Pacientes visibles según las sedes del usuario. Se crean y editan, pero no se borran:
    se desactivan (activo = false).

    Filtros (query string):
    - q: texto en nombres, apellidos, identidad o teléfono
    - sede: id de la sede de origen
    - activo: true | false | todos (por defecto, true)
    """

    serializer_class = PacienteSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = pacientes_visibles(self.request.user).select_related("sede_origen")
        # Los filtros aplican solo al listado. El detalle (editar, reactivar) ve todos.
        if self.action != "list":
            return qs
        params = self.request.query_params

        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(nombres__icontains=texto)
                | Q(apellidos__icontains=texto)
                | Q(identidad__icontains=texto)
                | Q(telefono__icontains=texto)
            )

        sede = params.get("sede", "")
        if sede.isdigit():
            qs = qs.filter(sede_origen_id=int(sede))

        activo = params.get("activo", "true")
        if activo == "true":
            qs = qs.filter(activo=True)
        elif activo == "false":
            qs = qs.filter(activo=False)

        return qs


def _valor_historial(valor):
    """Convierte fechas, horas y decimales a texto para el JSON del historial."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


class _HistorialMixin:
    """Acción `historial` con los cambios de simple_history."""

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        objeto = self.get_object()
        tipos = {"+": "Creada", "~": "Actualizada", "-": "Eliminada"}
        registros = []
        for registro in objeto.history.all().select_related("history_user"):
            cambios = []
            anterior = registro.prev_record
            if anterior is not None:
                for cambio in registro.diff_against(anterior).changes:
                    cambios.append(
                        {
                            "campo": cambio.field,
                            "antes": _valor_historial(cambio.old),
                            "despues": _valor_historial(cambio.new),
                        }
                    )
            usuario = registro.history_user
            if usuario is None:
                usuario_nombre = "Sistema"
            else:
                usuario_nombre = (
                    f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username
                )
            registros.append(
                {
                    "id": registro.history_id,
                    "fecha": registro.history_date,
                    "tipo": registro.history_type,
                    "tipo_nombre": tipos.get(registro.history_type, registro.history_type),
                    "usuario": usuario.username if usuario else None,
                    "usuario_nombre": usuario_nombre,
                    "motivo": registro.history_change_reason or "",
                    "cambios": cambios,
                }
            )
        return Response(registros)


class HistoriaClinicaViewSet(_HistorialMixin, viewsets.ModelViewSet):
    """
    Historia clínica de las sedes del usuario. No se borra: se corrige editando.

    Filtros del listado: paciente, sede, doctor, desde, hasta (AAAA-MM-DD) y q
    (nombre o apellido del paciente).
    """

    serializer_class = HistoriaClinicaSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = HistoriaClinica.objects.select_related(
            "paciente", "sede", "doctor", "atencion", "odontograma"
        )
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("paciente", "").isdigit():
            qs = qs.filter(paciente_id=int(params["paciente"]))
        if params.get("sede", "").isdigit():
            qs = qs.filter(sede_id=int(params["sede"]))
        if params.get("doctor", "").isdigit():
            qs = qs.filter(doctor_id=int(params["doctor"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(paciente__nombres__icontains=texto)
                | Q(paciente__apellidos__icontains=texto)
            )
        return qs


class OdontogramaViewSet(_HistorialMixin, viewsets.ModelViewSet):
    """
    Odontogramas de las sedes del usuario. Los hallazgos se envían anidados en
    `hallazgos` y, al editar, reemplazan a los anteriores.

    Filtros del listado: paciente, sede, desde y hasta (AAAA-MM-DD).
    """

    serializer_class = OdontogramaSerializer
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = Odontograma.objects.select_related(
            "paciente", "sede", "doctor", "historia"
        ).prefetch_related("hallazgos")
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("paciente", "").isdigit():
            qs = qs.filter(paciente_id=int(params["paciente"]))
        if params.get("sede", "").isdigit():
            qs = qs.filter(sede_id=int(params["sede"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        return qs

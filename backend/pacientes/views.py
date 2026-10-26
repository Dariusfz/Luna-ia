from django.db.models import Q
from rest_framework import viewsets

from .models import Paciente
from .querysets import pacientes_visibles
from .serializers import PacienteSerializer


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

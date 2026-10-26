from django.db.models import Q

from users.permisos import es_admin

from .models import Paciente


def pacientes_visibles(user):
    """
    Un paciente es visible para un usuario si su sede de origen es una de sus sedes
    o si tiene al menos una atención en una de sus sedes. El admin ve todos.
    """
    qs = Paciente.objects.all()
    if es_admin(user):
        return qs
    if not user or not user.is_authenticated:
        return qs.none()
    sedes = user.sedes.all()
    return qs.filter(Q(sede_origen__in=sedes) | Q(atenciones__sede__in=sedes)).distinct()

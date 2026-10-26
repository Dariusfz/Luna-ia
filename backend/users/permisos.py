"""
Reglas de acceso por rol y por sede (AGENTS.md reglas 3 y 6).

- admin: ve todas las sedes propias (consolidado) y es el único que gestiona invitaciones
  y jornadas externas.
- resto de roles: solo ve los registros de las sedes que tiene asignadas.
"""

from rest_framework.permissions import BasePermission

from .models import Usuario


def es_admin(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.rol == Usuario.Rol.ADMIN)
    )


def filtrar_por_sede(queryset, user, campo_sede: str = "sede"):
    """Restringe un queryset a las sedes del usuario. El admin ve todo."""
    if es_admin(user):
        return queryset
    if not user or not user.is_authenticated:
        return queryset.none()
    return queryset.filter(**{f"{campo_sede}__in": user.sedes.all()})


def puede_usar_sede(user, sede) -> bool:
    """Valida que el usuario pueda registrar algo en esa sede."""
    if es_admin(user):
        return True
    return user.is_authenticated and user.sedes.filter(pk=sede.pk).exists()


class EsAdmin(BasePermission):
    message = "Solo el administrador puede realizar esta acción."

    def has_permission(self, request, view):
        return es_admin(request.user)


class LecturaTodosEscrituraAdmin(BasePermission):
    """Lectura para cualquier usuario autenticado; cualquier cambio solo para el admin."""

    message = "Solo el administrador puede modificar este catálogo."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return es_admin(request.user)

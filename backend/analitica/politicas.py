"""
Qué consultas analíticas puede usar cada rol (AGENTS.md regla 3: los permisos viven en Django).

Se aplica en dos sitios:
- Las vistas de /api/analitica/ (`AnaliticaBase.initial`): responden 403 si el rol no tiene acceso.
- El asistente IA: solo recibe las herramientas que su rol puede usar, así que el modelo ni
  siquiera las ve.

Las sedes siguen filtrándose con `users.permisos.filtrar_por_sede` en todas las consultas.
"""

from users.models import Usuario
from users.permisos import es_admin

CONSULTAS_TODAS = frozenset(
    {"citas_hoy", "atendidos_mes", "por_servicio", "por_hora", "por_sede", "ingresos"}
)

POLITICA_POR_ROL = {
    Usuario.Rol.RECEPCIONISTA: frozenset(
        {"citas_hoy", "atendidos_mes", "por_servicio", "por_hora", "por_sede"}
    ),
    Usuario.Rol.ASISTENTE: frozenset({"citas_hoy", "atendidos_mes", "por_hora"}),
    # El doctor solo ve su propia agenda (ver `solo_agenda_propia`).
    Usuario.Rol.DOCTOR: frozenset({"citas_hoy", "atendidos_mes", "por_servicio", "por_hora"}),
}


def consultas_permitidas(usuario) -> frozenset:
    if not (usuario and usuario.is_authenticated):
        return frozenset()
    if es_admin(usuario):
        return CONSULTAS_TODAS
    return POLITICA_POR_ROL.get(usuario.rol, frozenset())


def puede_consultar(usuario, consulta: str) -> bool:
    return consulta in consultas_permitidas(usuario)


def solo_agenda_propia(usuario) -> bool:
    """Un doctor (no admin) solo cuenta las citas en las que él es el doctor."""
    return bool(
        usuario
        and usuario.is_authenticated
        and not es_admin(usuario)
        and usuario.rol == Usuario.Rol.DOCTOR
    )

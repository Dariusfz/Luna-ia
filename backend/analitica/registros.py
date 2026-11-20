"""
Consultas de LECTURA sobre los registros del ERP para el asistente IA.

El modelo no escribe SQL ni elige columnas: solo puede
- elegir una entidad de la lista blanca (`ENTIDADES`),
- usar los filtros declarados para esa entidad (con su tipo validado),
- agrupar por los campos declarados como agrupables,
- pedir hasta `LIMITE_MAXIMO` registros.

Lo que puede ver cada rol se decide en `ENTIDADES_POR_ROL` (Django, no el prompt) y el
alcance de datos (sedes, pacientes propios de un doctor) se aplica en cada `base`.

Campos excluidos a propósito, por ser datos sensibles y no necesarios para responder:
- Historia clínica del paciente (alergias, antecedentes, medicamentos, observaciones).
- Número de identidad (DNI), correo y dirección del paciente.
- Contraseñas, 2FA, tokens, invitaciones y conversaciones de WhatsApp.
- Identificadores internos (ids): el asistente nunca debe mostrarlos.
"""

import json
from dataclasses import dataclass
from datetime import time
from typing import Any, Callable

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status

from agenda.models import Atencion, ListaEspera
from pacientes.models import Paciente
from pacientes.querysets import pacientes_visibles
from pagos.models import MetodoPago, Pago, PagoDoctor
from agenda.models import JornadaExterna
from servicios.models import Especialidad, TipoTrabajo
from sedes.models import Sede
from users.models import Doctor, Usuario
from users.permisos import es_admin, filtrar_por_sede

from .politicas import solo_agenda_propia

NOMBRE_HERRAMIENTA = "consultar_registros"
LIMITE_DEFECTO = 20
LIMITE_MAXIMO = 50

@dataclass(frozen=True)
class Filtro:
    tipo: str  # "texto" | "fecha" | "bool" | "opcion"
    aplicar: Callable[[Any, Any], Any]
    opciones: tuple = ()  # para "opcion": pares (valor, etiqueta)
    ayuda: str = ""


@dataclass(frozen=True)
class Entidad:
    descripcion: str
    base: Callable[[Any], Any]
    filtros: dict
    campos: dict
    agrupables: dict  # nombre -> (ruta del ORM, {valor: etiqueta} o None)
    orden: tuple
    suma: str | None = None  # ruta del ORM que se suma (solo pagos)


def _fmt_fecha(valor):
    return valor.isoformat() if valor else None


def _fmt_hora(valor: time | None):
    return valor.strftime("%H:%M") if valor else None


def _fmt_monto(valor):
    return f"{valor:.2f}" if valor is not None else None


def _edad(fecha_nacimiento):
    if not fecha_nacimiento:
        return None
    hoy = timezone.localdate()
    return hoy.year - fecha_nacimiento.year - (
        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    )


def _nombre(obj) -> str:
    return f"{obj.nombres} {obj.apellidos}".strip()


def _nombre_usuario(u: Usuario) -> str:
    return (f"{u.first_name} {u.last_name}").strip() or u.username


def _opciones(choices) -> tuple:
    """Convierte `Modelo.Campo.choices` en pares (valor, etiqueta)."""
    return tuple((valor, str(etiqueta)) for valor, etiqueta in choices)


def _mapa(opciones: tuple) -> dict:
    return {valor: etiqueta for valor, etiqueta in opciones}


def _filtro_opcion(campo: str, opciones: tuple) -> Filtro:
    return Filtro(
        "opcion",
        lambda qs, v: qs.filter(**{campo: v}),
        opciones=opciones,
        ayuda="Uno de: " + ", ".join(etiqueta for _, etiqueta in opciones),
    )


def _filtro_texto(*campos_icontains: str, ayuda: str = "") -> Filtro:
    def aplicar(qs, valor):
        consulta = Q()
        for campo in campos_icontains:
            consulta |= Q(**{f"{campo}__icontains": valor})
        return qs.filter(consulta)

    return Filtro("texto", aplicar, ayuda=ayuda)


def _filtro_nombre(*campos: str, ayuda: str = "Nombre o apellido (puede ser parcial o completo)") -> Filtro:
    """Cada palabra debe aparecer en alguno de los campos (así 'Carlos Pérez' funciona)."""

    def aplicar(qs, valor):
        for palabra in str(valor).split():
            consulta = Q()
            for campo in campos:
                consulta |= Q(**{f"{campo}__icontains": palabra})
            qs = qs.filter(consulta)
        return qs

    return Filtro("texto", aplicar, ayuda=ayuda)


def _filtro_fecha(campo: str, operador: str, ayuda: str = "") -> Filtro:
    return Filtro(
        "fecha",
        lambda qs, v: qs.filter(**{f"{campo}__{operador}": v}),
        ayuda=ayuda or "AAAA-MM-DD",
    )


def _filtro_mes(campo: str, ayuda: str = "Mes en formato AAAA-MM (mes completo)") -> Filtro:
    """Filtra por mes calendario completo, incluidas las fechas futuras de ese mes."""
    return Filtro(
        "mes",
        lambda qs, v: qs.filter(**{f"{campo}__year": v[0], f"{campo}__month": v[1]}),
        ayuda=ayuda,
    )


def _filtro_bool(campo: str) -> Filtro:
    return Filtro("bool", lambda qs, v: qs.filter(**{campo: v}), ayuda="true o false")


# ---------------------------------------------------------------------------
# Bases (alcance por rol)
# ---------------------------------------------------------------------------


def _base_pacientes(usuario):
    qs = pacientes_visibles(usuario).select_related("sede_origen")
    if solo_agenda_propia(usuario):
        qs = qs.filter(atenciones__doctor__usuario=usuario).distinct()
    return qs


def _base_doctores(usuario):
    qs = Doctor.objects.prefetch_related("especialidades", "sedes")
    if not es_admin(usuario):
        qs = filtrar_por_sede(qs, usuario, campo_sede="sedes").distinct()
    return qs


def _base_especialidades(usuario):
    return Especialidad.objects.all()


def _base_tipos_trabajo(usuario):
    return TipoTrabajo.objects.all()


def _base_sedes(usuario):
    return filtrar_por_sede(Sede.objects.all(), usuario, campo_sede="id")


def _base_atenciones(usuario):
    qs = filtrar_por_sede(
        Atencion.objects.select_related("paciente", "doctor", "sede", "tipo_trabajo"),
        usuario,
    )
    if solo_agenda_propia(usuario):
        qs = qs.filter(doctor__usuario=usuario)
    return qs


def _base_lista_espera(usuario):
    return filtrar_por_sede(
        ListaEspera.objects.select_related("paciente", "sede", "doctor", "tipo_trabajo"),
        usuario,
    )


def _base_pagos(usuario):
    return Pago.objects.select_related("atencion__paciente", "atencion__sede")


def _base_personal(usuario):
    return Usuario.objects.prefetch_related("sedes")


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------

ENTIDADES: dict[str, Entidad] = {
    "pacientes": Entidad(
        descripcion="Pacientes: nombre, teléfono, edad, sede de origen y estado. "
        "Se puede buscar por nombre, teléfono o sede y contar pacientes nuevos por fecha.",
        base=_base_pacientes,
        filtros={
            "nombre": _filtro_nombre("nombres", "apellidos"),
            "telefono": _filtro_texto("telefono", ayuda="Teléfono (parcial)"),
            "sede": _filtro_texto("sede_origen__nombre", ayuda="Nombre de la sede de origen"),
            "activo": _filtro_bool("activo"),
            "mes_alta": _filtro_mes("creado", "Mes de alta en formato AAAA-MM"),
            "creado_desde": _filtro_fecha("creado", "date__gte", "Fecha de alta, desde"),
            "creado_hasta": _filtro_fecha("creado", "date__lte", "Fecha de alta, hasta"),
        },
        campos={
            "nombre": _nombre,
            "telefono": lambda p: p.telefono or None,
            "edad": lambda p: _edad(p.fecha_nacimiento),
            "sede_origen": lambda p: p.sede_origen.nombre,
            "activo": lambda p: p.activo,
            "fecha_alta": lambda p: _fmt_fecha(p.creado.date()),
        },
        agrupables={
            "activo": ("activo", {True: "Activos", False: "Inactivos"}),
            "sede": ("sede_origen__nombre", None),
        },
        orden=("nombres", "apellidos"),
    ),
    "doctores": Entidad(
        descripcion="Doctores: nombre, tipo (interno o por sesión), especialidades, sedes y estado.",
        base=_base_doctores,
        filtros={
            "nombre": _filtro_nombre("nombres", "apellidos"),
            "especialidad": _filtro_texto("especialidades__nombre", ayuda="Nombre de la especialidad"),
            "sede": _filtro_texto("sedes__nombre", ayuda="Nombre de la sede"),
            "tipo": _filtro_opcion("tipo", _opciones(Doctor.Tipo.choices)),
            "activo": _filtro_bool("activo"),
        },
        campos={
            "nombre": _nombre,
            "tipo": lambda d: d.get_tipo_display(),
            "especialidades": lambda d: [e.nombre for e in d.especialidades.all()],
            "sedes": lambda d: [s.nombre for s in d.sedes.all()],
            "telefono": lambda d: d.telefono or None,
            "numero_colegiado": lambda d: d.numero_colegiado or None,
            "activo": lambda d: d.activo,
        },
        agrupables={
            "tipo": ("tipo", _mapa(_opciones(Doctor.Tipo.choices))),
            "activo": ("activo", {True: "Activos", False: "Inactivos"}),
        },
        orden=("nombres", "apellidos"),
    ),
    "especialidades": Entidad(
        descripcion="Especialidades odontológicas registradas en el sistema.",
        base=_base_especialidades,
        filtros={
            "nombre": _filtro_texto("nombre"),
            "activo": _filtro_bool("activo"),
        },
        campos={"nombre": lambda e: e.nombre, "activo": lambda e: e.activo},
        agrupables={"activo": ("activo", {True: "Activas", False: "Inactivas"})},
        orden=("nombre",),
    ),
    "tipos_trabajo": Entidad(
        descripcion="Tratamientos y tipos de trabajo, con su precio de referencia en lempiras.",
        base=_base_tipos_trabajo,
        filtros={
            "nombre": _filtro_texto("nombre"),
            "activo": _filtro_bool("activo"),
        },
        campos={
            "nombre": lambda t: t.nombre,
            "precio": lambda t: _fmt_monto(t.precio),
            "descripcion": lambda t: t.descripcion or None,
            "activo": lambda t: t.activo,
        },
        agrupables={"activo": ("activo", {True: "Activos", False: "Inactivos"})},
        orden=("nombre",),
    ),
    "sedes": Entidad(
        descripcion="Sedes de la clínica: nombre, dirección, teléfono y estado.",
        base=_base_sedes,
        filtros={
            "nombre": _filtro_texto("nombre"),
            "activa": _filtro_bool("activa"),
        },
        campos={
            "nombre": lambda s: s.nombre,
            "direccion": lambda s: s.direccion or None,
            "telefono": lambda s: s.telefono or None,
            "activa": lambda s: s.activa,
        },
        agrupables={"activa": ("activa", {True: "Activas", False: "Inactivas"})},
        orden=("nombre",),
    ),
    "atenciones": Entidad(
        descripcion="Citas y atenciones: fecha, horario, paciente, doctor, sede, tratamiento, "
        "estado y origen (panel del personal o agente de WhatsApp). Sirve para contar citas "
        "por estado, por origen, por sede, por fecha o por paciente.",
        base=_base_atenciones,
        filtros={
            "mes": _filtro_mes("fecha"),
            "fecha_desde": _filtro_fecha("fecha", "gte", "Fecha de la cita, desde"),
            "fecha_hasta": _filtro_fecha("fecha", "lte", "Fecha de la cita, hasta"),
            "estado": _filtro_opcion("estado", _opciones(Atencion.Estado.choices)),
            "origen": _filtro_opcion("origen", _opciones(Atencion.Origen.choices)),
            "sede": _filtro_texto("sede__nombre", ayuda="Nombre de la sede"),
            "doctor": _filtro_nombre("doctor__nombres", "doctor__apellidos", ayuda="Nombre del doctor"),
            "paciente": _filtro_nombre("paciente__nombres", "paciente__apellidos", ayuda="Nombre del paciente"),
            "tratamiento": _filtro_texto("tipo_trabajo__nombre", ayuda="Nombre del tratamiento"),
        },
        campos={
            "fecha": lambda a: _fmt_fecha(a.fecha),
            "hora_inicio": lambda a: _fmt_hora(a.hora_inicio),
            "hora_fin": lambda a: _fmt_hora(a.hora_fin),
            "paciente": lambda a: _nombre(a.paciente),
            "doctor": lambda a: _nombre(a.doctor),
            "sede": lambda a: a.sede.nombre,
            "tratamiento": lambda a: a.tipo_trabajo.nombre,
            "estado": lambda a: a.get_estado_display(),
            "origen": lambda a: a.get_origen_display(),
            "precio": lambda a: _fmt_monto(a.precio_paciente),
        },
        agrupables={
            "estado": ("estado", _mapa(_opciones(Atencion.Estado.choices))),
            "origen": ("origen", _mapa(_opciones(Atencion.Origen.choices))),
            "sede": ("sede__nombre", None),
            "tratamiento": ("tipo_trabajo__nombre", None),
        },
        orden=("-fecha", "-hora_inicio"),
    ),
    "lista_espera": Entidad(
        descripcion="Lista de espera: pacientes que esperan cupo, con prioridad, estado y motivo.",
        base=_base_lista_espera,
        filtros={
            "estado": _filtro_opcion("estado", _opciones(ListaEspera.Estado.choices)),
            "prioridad": _filtro_opcion("prioridad", _opciones(ListaEspera.Prioridad.choices)),
            "sede": _filtro_texto("sede__nombre", ayuda="Nombre de la sede"),
            "paciente": _filtro_nombre("paciente__nombres", "paciente__apellidos", ayuda="Nombre del paciente"),
        },
        campos={
            "paciente": lambda e: _nombre(e.paciente),
            "sede": lambda e: e.sede.nombre,
            "estado": lambda e: e.get_estado_display(),
            "prioridad": lambda e: e.get_prioridad_display(),
            "doctor_preferido": lambda e: _nombre(e.doctor) if e.doctor else None,
            "tratamiento": lambda e: e.tipo_trabajo.nombre if e.tipo_trabajo else None,
            "fecha_deseada": lambda e: _fmt_fecha(e.fecha_deseada),
            "motivo": lambda e: e.motivo or None,
        },
        agrupables={
            "estado": ("estado", _mapa(_opciones(ListaEspera.Estado.choices))),
            "sede": ("sede__nombre", None),
            "prioridad": ("prioridad", _mapa(_opciones(ListaEspera.Prioridad.choices))),
        },
        orden=("-prioridad", "creada"),
    ),
    "pagos": Entidad(
        descripcion="Abonos y cobros de pacientes (caja): fecha, monto, método, paciente y sede. "
        "Sirve para totales cobrados por fecha, método o sede.",
        base=_base_pagos,
        filtros={
            "mes": _filtro_mes("fecha"),
            "desde": _filtro_fecha("fecha", "gte", "Fecha del cobro, desde"),
            "hasta": _filtro_fecha("fecha", "lte", "Fecha del cobro, hasta"),
            "metodo": _filtro_opcion("metodo", _opciones(MetodoPago.choices)),
            "sede": _filtro_texto("atencion__sede__nombre", ayuda="Nombre de la sede"),
            "paciente": _filtro_texto("atencion__paciente__nombres", "atencion__paciente__apellidos", ayuda="Nombre del paciente"),
        },
        campos={
            "fecha": lambda p: _fmt_fecha(p.fecha),
            "monto": lambda p: _fmt_monto(p.monto),
            "metodo": lambda p: p.get_metodo_display(),
            "paciente": lambda p: _nombre(p.atencion.paciente),
            "sede": lambda p: p.atencion.sede.nombre,
            "nota": lambda p: p.nota or None,
        },
        agrupables={
            "metodo": ("metodo", _mapa(_opciones(MetodoPago.choices))),
            "sede": ("atencion__sede__nombre", None),
        },
        orden=("-fecha", "-id"),
        suma="monto",
    ),
    "pagos_doctores": Entidad(
        descripcion="Pagos realizados a doctores (comisiones): fecha, monto, método, doctor, "
        "paciente de la cita y sede.",
        base=lambda usuario: PagoDoctor.objects.select_related("doctor", "atencion__paciente", "atencion__sede"),
        filtros={
            "mes": _filtro_mes("fecha"),
            "desde": _filtro_fecha("fecha", "gte", "Fecha del pago, desde"),
            "hasta": _filtro_fecha("fecha", "lte", "Fecha del pago, hasta"),
            "doctor": _filtro_nombre("doctor__nombres", "doctor__apellidos", ayuda="Nombre del doctor"),
            "metodo": _filtro_opcion("metodo", _opciones(MetodoPago.choices)),
            "sede": _filtro_texto("atencion__sede__nombre", ayuda="Nombre de la sede"),
        },
        campos={
            "fecha": lambda p: _fmt_fecha(p.fecha),
            "monto": lambda p: _fmt_monto(p.monto),
            "metodo": lambda p: p.get_metodo_display(),
            "doctor": lambda p: _nombre(p.doctor),
            "paciente": lambda p: _nombre(p.atencion.paciente),
            "sede": lambda p: p.atencion.sede.nombre,
            "nota": lambda p: p.nota or None,
        },
        agrupables={
            "metodo": ("metodo", _mapa(_opciones(MetodoPago.choices))),
            "sede": ("atencion__sede__nombre", None),
            "doctor": ("doctor__apellidos", None),
        },
        orden=("-fecha", "-id"),
        suma="monto",
    ),
    "jornadas_externas": Entidad(
        descripcion="Jornadas de trabajo fuera de la clínica: fecha, horario, lugar, tipo de "
        "trabajo, doctor y cobro.",
        base=lambda usuario: JornadaExterna.objects.select_related("doctor", "lugar", "tipo_trabajo"),
        filtros={
            "mes": _filtro_mes("fecha"),
            "desde": _filtro_fecha("fecha", "gte", "Fecha, desde"),
            "hasta": _filtro_fecha("fecha", "lte", "Fecha, hasta"),
            "doctor": _filtro_nombre("doctor__nombres", "doctor__apellidos", ayuda="Nombre del doctor"),
            "lugar": _filtro_texto("lugar__nombre", ayuda="Nombre del lugar externo"),
        },
        campos={
            "fecha": lambda j: _fmt_fecha(j.fecha),
            "hora_inicio": lambda j: _fmt_hora(j.hora_inicio),
            "hora_fin": lambda j: _fmt_hora(j.hora_fin),
            "doctor": lambda j: _nombre(j.doctor),
            "lugar": lambda j: j.lugar.nombre,
            "tratamiento": lambda j: j.tipo_trabajo.nombre,
            "cobrado": lambda j: _fmt_monto(j.monto_cobrado),
            "observaciones": lambda j: j.observaciones or None,
        },
        agrupables={
            "lugar": ("lugar__nombre", None),
            "doctor": ("doctor__apellidos", None),
        },
        orden=("-fecha", "-hora_inicio"),
        suma="monto_cobrado",
    ),
    "personal": Entidad(
        descripcion="Usuarios del sistema (personal): nombre, usuario, rol, sedes y estado. "
        "Sin contraseñas ni datos de seguridad.",
        base=_base_personal,
        filtros={
            "nombre": _filtro_nombre("first_name", "last_name", "username", ayuda="Nombre o usuario"),
            "rol": _filtro_opcion("rol", _opciones(Usuario.Rol.choices)),
            "activo": _filtro_bool("is_active"),
            "sede": _filtro_texto("sedes__nombre", ayuda="Nombre de la sede"),
        },
        campos={
            "nombre": _nombre_usuario,
            "usuario": lambda u: u.username,
            "rol": lambda u: u.get_rol_display(),
            "sedes": lambda u: [s.nombre for s in u.sedes.all()],
            "activo": lambda u: u.is_active,
        },
        agrupables={
            "rol": ("rol", _mapa(_opciones(Usuario.Rol.choices))),
            "activo": ("is_active", {True: "Activos", False: "Inactivos"}),
        },
        orden=("first_name", "last_name", "username"),
    ),
}


# ---------------------------------------------------------------------------
# Permisos por rol
# ---------------------------------------------------------------------------

_ENTIDADES_STAFF = {"especialidades", "tipos_trabajo", "sedes", "doctores"}

ENTIDADES_POR_ROL = {
    Usuario.Rol.RECEPCIONISTA: frozenset(
        _ENTIDADES_STAFF | {"pacientes", "atenciones", "lista_espera"}
    ),
    Usuario.Rol.ASISTENTE: frozenset(_ENTIDADES_STAFF | {"pacientes", "atenciones", "lista_espera"}),
    Usuario.Rol.DOCTOR: frozenset(_ENTIDADES_STAFF | {"pacientes", "atenciones"}),
}


def entidades_permitidas(usuario) -> frozenset:
    if not (usuario and usuario.is_authenticated):
        return frozenset()
    if es_admin(usuario):
        return frozenset(ENTIDADES)
    return ENTIDADES_POR_ROL.get(usuario.rol, frozenset())


def definicion_herramienta(usuario) -> dict | None:
    """Definición de la herramienta para el LLM, o None si el rol no tiene entidades."""
    permitidas = sorted(entidades_permitidas(usuario))
    if not permitidas:
        return None
    lineas = [f"- {nombre}: {ENTIDADES[nombre].descripcion}" for nombre in permitidas]
    return {
        "type": "function",
        "function": {
            "name": NOMBRE_HERRAMIENTA,
            "description": (
                "Cuenta, busca o lista registros del sistema. Úsala para preguntas de tipo "
                "'cuántos', 'cuáles', 'qué', 'lista' o 'busca' sobre pacientes, doctores, "
                "especialidades, tratamientos, sedes, citas, lista de espera, pagos o personal.\n"
                + "\n".join(lineas)
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entidad": {"type": "string", "enum": permitidas},
                    "filtros": {
                        "type": "object",
                        "description": "Solo los filtros que el usuario mencionó. Valores como texto. "
                        "Fechas AAAA-MM-DD. Los filtros disponibles dependen de la entidad.",
                    },
                    "agrupar_por": {
                        "type": "string",
                        "description": "Opcional: cuenta los registros agrupados por este campo. "
                        "Valores: " + "; ".join(sorted({
                            clave for nombre in permitidas for clave in ENTIDADES[nombre].agrupables
                        })),
                    },
                    "limite": {
                        "type": "integer",
                        "description": f"Cuántos registros listar (1 a {LIMITE_MAXIMO}).",
                    },
                },
                "required": ["entidad"],
                "additionalProperties": False,
            },
        },
    }


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------


class ErrorConsulta(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _valor_filtro(nombre: str, filtro: Filtro, valor):
    texto = str(valor).strip()
    if filtro.tipo == "texto":
        return texto
    if filtro.tipo == "fecha":
        fecha = parse_date(texto)
        if fecha is None:
            raise ErrorConsulta(400, f"El filtro '{nombre}' debe ser una fecha AAAA-MM-DD.")
        return fecha
    if filtro.tipo == "mes":
        partes = texto.split("-")
        try:
            anio, mes = int(partes[0]), int(partes[1])
            if not (1 <= mes <= 12 and 1900 <= anio <= 2999) or len(partes) != 2:
                raise ValueError
        except (ValueError, IndexError):
            raise ErrorConsulta(400, f"El filtro '{nombre}' debe tener formato AAAA-MM.")
        return (anio, mes)
    if filtro.tipo == "bool":
        bajo = texto.lower()
        if bajo in ("true", "si", "sí", "1", "activo", "activa"):
            return True
        if bajo in ("false", "no", "0", "inactivo", "inactiva"):
            return False
        raise ErrorConsulta(400, f"El filtro '{nombre}' debe ser verdadero o falso.")
    if filtro.tipo == "opcion":
        bajo = texto.lower()
        for valor_opcion, etiqueta in filtro.opciones:
            if bajo in (str(valor_opcion).lower(), etiqueta.lower()):
                return valor_opcion
        raise ErrorConsulta(400, f"El valor '{texto}' no es válido para '{nombre}'.")
    raise ErrorConsulta(400, "Filtro no soportado.")


def ejecutar(usuario, argumentos) -> tuple[int, dict]:
    """Devuelve (código HTTP, resultado). El resultado nunca incluye ids."""
    try:
        return status.HTTP_200_OK, _ejecutar(usuario, argumentos)
    except ErrorConsulta as error:
        codigo = error.codigo
        return codigo, {"error": error.mensaje}


def _ejecutar(usuario, argumentos) -> dict:
    if not isinstance(argumentos, dict):
        raise ErrorConsulta(400, "Argumentos inválidos.")

    nombre = str(argumentos.get("entidad", "")).strip()
    if nombre not in ENTIDADES:
        raise ErrorConsulta(400, "Entidad desconocida.")
    if nombre not in entidades_permitidas(usuario):
        raise ErrorConsulta(403, "Tu rol no tiene acceso a esta información.")
    entidad = ENTIDADES[nombre]

    qs = entidad.base(usuario)
    filtros = argumentos.get("filtros") or {}
    if isinstance(filtros, str):
        try:
            filtros = json.loads(filtros) if filtros.strip() else {}
        except json.JSONDecodeError:
            raise ErrorConsulta(400, "Los filtros deben ser un objeto.")
    if not isinstance(filtros, dict):
        raise ErrorConsulta(400, "Los filtros deben ser un objeto.")
    for clave, valor in filtros.items():
        if valor in (None, ""):
            continue
        clave = _clave_filtro(entidad, clave)
        if clave not in entidad.filtros:
            raise ErrorConsulta(
                400,
                f"El filtro '{clave}' no existe para {nombre}. "
                f"Filtros válidos: {', '.join(entidad.filtros)}.",
            )
        filtro = entidad.filtros[clave]
        qs = filtro.aplicar(qs, _valor_filtro(clave, filtro, valor))

    qs = qs.distinct()  # los filtros por relaciones M2M pueden repetir filas
    total = qs.count()
    resultado = {"entidad": nombre, "total": total}

    agrupar = argumentos.get("agrupar_por")
    if agrupar:
        if agrupar not in entidad.agrupables:
            raise ErrorConsulta(
                400,
                f"No se puede agrupar {nombre} por '{agrupar}'. "
                f"Opciones: {', '.join(entidad.agrupables)}.",
            )
        ruta, etiquetas = entidad.agrupables[agrupar]
        filas = (
            qs.order_by()
            .values(ruta)
            .annotate(cantidad=Count("pk", distinct=True))
            .order_by("-cantidad")
        )
        resultado["agrupado_por"] = agrupar
        resultado["grupos"] = [
            {
                "valor": (
                    etiquetas.get(fila[ruta], str(fila[ruta])) if etiquetas else (fila[ruta] or "Sin dato")
                ),
                "cantidad": fila["cantidad"],
            }
            for fila in filas
        ]
        return resultado

    limite = _limite(argumentos.get("limite"))
    registros = list(qs.order_by(*entidad.orden)[:limite])
    resultado["mostrando"] = len(registros)
    resultado["registros"] = [
        {campo: funcion(obj) for campo, funcion in entidad.campos.items()} for obj in registros
    ]
    if entidad.suma:
        suma = qs.aggregate(total=Sum(entidad.suma))["total"] or 0
        resultado["suma_total"] = _fmt_monto(suma)
    return resultado


# Nombres alternativos que el modelo suele usar para el mismo filtro de fecha.
_ALIAS_FILTROS = {
    "desde": ("fecha_desde", "creado_desde", "desde"),
    "hasta": ("fecha_hasta", "creado_hasta", "hasta"),
    "fecha_desde": ("fecha_desde", "desde"),
    "fecha_hasta": ("fecha_hasta", "hasta"),
}


def _clave_filtro(entidad: Entidad, clave: str) -> str:
    """Si el filtro no existe con ese nombre, usa el alias que sí exista en la entidad."""
    if clave in entidad.filtros:
        return clave
    for alias in _ALIAS_FILTROS.get(clave, ()):
        if alias in entidad.filtros:
            return alias
    return clave


def _limite(valor) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return LIMITE_DEFECTO
    return max(1, min(numero, LIMITE_MAXIMO))

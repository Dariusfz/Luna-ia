"""
Análisis estratégico para el asistente: tendencias, proyecciones y señales de negocio.

Todos los números los calcula el código (no el modelo). El modelo solo interpreta el
resultado y propone planes. Cada sección aparece únicamente si el rol tiene acceso al
módulo correspondiente (`registros.entidades_permitidas`), y las citas respetan el
alcance por sede y por doctor de `registros._base_atenciones`.

Las proyecciones son una regresión lineal sobre los meses completos: son estimaciones,
no garantías.
"""

from collections import Counter, defaultdict
from datetime import date

from django.db.models import Count
from django.utils import timezone
from rest_framework import status

from agenda.models import Atencion, AtencionTrabajo, ListaEspera
from pagos.models import Pago

from . import registros

NOMBRE_HERRAMIENTA = "analisis_estrategico"
MESES_DEFECTO = 6
MESES_MINIMO = 3  # con menos meses no hay tendencia que calcular
MESES_MAXIMO = 12
TOP = 10

NOTA = (
    "Las proyecciones son estimaciones lineales sobre los meses completos (el mes en curso "
    "es parcial y no se usa para proyectar). Úsalas como orientación, no como certeza."
)


def _meses(valor) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return MESES_DEFECTO
    return max(MESES_MINIMO, min(numero, MESES_MAXIMO))


def _rotulos(hoy: date, cantidad: int) -> list[str]:
    """Meses 'AAAA-MM' desde `cantidad - 1` meses atrás hasta el actual."""
    base = hoy.year * 12 + (hoy.month - 1) - (cantidad - 1)
    return [f"{(base + i) // 12}-{(base + i) % 12 + 1:02d}" for i in range(cantidad)]


def _mes(fecha: date) -> str:
    return f"{fecha.year}-{fecha.month:02d}"


def proyectar(valores: list[float]) -> dict | None:
    """Regresión lineal simple: estimación del valor siguiente y dirección de la tendencia."""
    n = len(valores)
    if n < 2:
        return None
    media_x = (n - 1) / 2
    media_y = sum(valores) / n
    denominador = sum((i - media_x) ** 2 for i in range(n))
    pendiente = sum((i - media_x) * (y - media_y) for i, y in enumerate(valores)) / denominador
    estimado = media_y + pendiente * (n - media_x)
    if pendiente > 0.5:
        tendencia = "al alza"
    elif pendiente < -0.5:
        tendencia = "a la baja"
    else:
        tendencia = "estable"
    return {
        "estimado_proximo_mes": max(0, round(estimado, 1)),
        "tendencia": tendencia,
        "cambio_promedio_mensual": round(pendiente, 1),
    }


def _seccion_citas(usuario, inicio, hoy, rotulos):
    completos = rotulos[:-1]
    total, completadas = Counter(), Counter()
    pacientes = defaultdict(set)
    canceladas = activas = futuras = 0
    filas = registros._base_atenciones(usuario).filter(fecha__gte=inicio).values_list(
        "fecha", "estado", "paciente_id"
    )
    for fecha, estado, paciente_id in filas:
        if fecha > hoy:
            if estado in (Atencion.Estado.PENDIENTE, Atencion.Estado.CONFIRMADA):
                futuras += 1
            continue
        if estado == Atencion.Estado.CANCELADA:
            canceladas += 1
            continue
        activas += 1
        total[_mes(fecha)] += 1
        if estado == Atencion.Estado.COMPLETADA:
            completadas[_mes(fecha)] += 1
            pacientes[_mes(fecha)].add(paciente_id)

    atendidos = [len(pacientes[m]) for m in completos]
    tasa = round(canceladas / (canceladas + activas) * 100, 1) if canceladas + activas else None
    proximo = _rotulos(hoy, len(rotulos) + 1)[-1]
    return {
        "citas_por_mes": [
            {
                "mes": m,
                "citas": total[m],
                "completadas": completadas[m],
                "pacientes_atendidos": len(pacientes[m]),
                "parcial": m == rotulos[-1],
            }
            for m in rotulos
        ],
        "proyeccion_citas": {"mes": proximo, **(proyectar([total[m] for m in completos]) or {})},
        "proyeccion_pacientes_atendidos": {
            "mes": proximo,
            **(proyectar(atendidos) or {}),
        },
        "tasa_cancelacion_pct": tasa,
        "citas_futuras_agendadas": futuras,
    }


def _seccion_tratamientos(usuario, inicio, hoy, rotulos):
    """Tratamientos más pedidos y si crecen: compara la mitad final con la inicial del periodo."""
    mitad = len(rotulos) // 2
    antes, despues = set(rotulos[:mitad]), set(rotulos[mitad:])
    total, primera, segunda = Counter(), Counter(), Counter()
    filas = (
        AtencionTrabajo.objects.filter(
            atencion__in=registros._base_atenciones(usuario).filter(fecha__gte=inicio, fecha__lte=hoy)
        )
        .exclude(atencion__estado=Atencion.Estado.CANCELADA)
        .values_list("tipo_trabajo__nombre", "atencion__fecha")
    )
    for nombre, fecha in filas:
        total[nombre] += 1
        if _mes(fecha) in antes:
            primera[nombre] += 1
        elif _mes(fecha) in despues:
            segunda[nombre] += 1
    suma = sum(total.values()) or 1
    salida = []
    for nombre, cantidad in total.most_common(TOP):
        a, b = primera[nombre], segunda[nombre]
        if a == 0 and b > 0:
            tendencia = "crece"
        elif b > a * 1.2:
            tendencia = "crece"
        elif b < a * 0.8:
            tendencia = "baja"
        else:
            tendencia = "estable"
        salida.append(
            {
                "tratamiento": nombre,
                "citas": cantidad,
                "porcentaje_del_total": round(cantidad / suma * 100, 1),
                "primera_mitad_del_periodo": a,
                "segunda_mitad_del_periodo": b,
                "tendencia": tendencia,
            }
        )
    return {"mas_solicitados": salida}


def _seccion_horas(usuario, inicio, hoy):
    conteo = Counter(
        hora.hour
        for hora in registros._base_atenciones(usuario)
        .exclude(estado=Atencion.Estado.CANCELADA)
        .filter(fecha__gte=inicio, fecha__lte=hoy)
        .values_list("hora_inicio", flat=True)
    )
    return {"horas_pico": [{"hora": f"{h:02d}:00", "citas": c} for h, c in conteo.most_common(5)]}


def _seccion_carga_doctores(usuario, inicio, hoy):
    conteo = Counter(
        f"{nombres} {apellidos}".strip()
        for nombres, apellidos in registros._base_atenciones(usuario)
        .exclude(estado=Atencion.Estado.CANCELADA)
        .filter(fecha__gte=inicio, fecha__lte=hoy)
        .values_list("doctor__nombres", "doctor__apellidos")
    )
    return {"doctores": [{"doctor": n, "citas": c} for n, c in conteo.most_common(TOP)]}


def _seccion_sedes(usuario, inicio, hoy):
    totales, canceladas = Counter(), Counter()
    for sede, estado in (
        registros._base_atenciones(usuario)
        .filter(fecha__gte=inicio, fecha__lte=hoy)
        .values_list("sede__nombre", "estado")
    ):
        totales[sede] += 1
        if estado == Atencion.Estado.CANCELADA:
            canceladas[sede] += 1
    return {
        "sedes": [
            {
                "sede": sede,
                "citas": cantidad,
                "cancelaciones_pct": round(canceladas[sede] / cantidad * 100, 1),
            }
            for sede, cantidad in totales.most_common()
        ]
    }


def _seccion_pacientes(usuario, inicio, hoy, rotulos):
    base = registros._base_pacientes(usuario)
    nuevos = Counter(_mes(creado.date()) for creado in base.filter(creado__date__gte=inicio).values_list("creado", flat=True))
    completos = rotulos[:-1]
    return {
        "activos": base.filter(activo=True).count(),
        "altas_por_mes": [{"mes": m, "pacientes_nuevos": nuevos[m]} for m in rotulos],
        "proyeccion_altas": {
            "mes": _rotulos(hoy, len(rotulos) + 1)[-1],
            **(proyectar([nuevos[m] for m in completos]) or {}),
        },
    }


def _seccion_lista_espera(usuario):
    base = registros._base_lista_espera(usuario).filter(estado=ListaEspera.Estado.ESPERANDO)
    por_tratamiento = (
        base.values("tipo_trabajo__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad")
    )
    return {
        "en_espera": base.count(),
        "por_tratamiento": [
            {"tratamiento": f["tipo_trabajo__nombre"] or "Sin especificar", "pacientes": f["cantidad"]}
            for f in por_tratamiento
        ],
    }


def _seccion_finanzas(inicio, hoy, rotulos):
    por_mes = defaultdict(float)
    total = 0.0
    for fecha, monto in Pago.objects.filter(fecha__gte=inicio, fecha__lte=hoy).values_list("fecha", "monto"):
        por_mes[_mes(fecha)] += float(monto)
        total += float(monto)
    completos = rotulos[:-1]
    return {
        "cobrado_por_mes": [{"mes": m, "monto": round(por_mes[m], 2)} for m in rotulos],
        "total_cobrado_periodo": round(total, 2),
        "proyeccion_cobro": {
            "mes": _rotulos(hoy, len(rotulos) + 1)[-1],
            **(proyectar([por_mes[m] for m in completos]) or {}),
        },
    }


def definicion_herramienta(usuario) -> dict | None:
    if not registros.entidades_permitidas(usuario):
        return None
    return {
        "type": "function",
        "function": {
            "name": NOMBRE_HERRAMIENTA,
            "description": (
                "Análisis estratégico de la clínica: cuántas personas se atienden por mes, "
                "tendencias y proyección del próximo mes, tratamientos más solicitados y si "
                "crecen, horas pico, carga de doctores, sedes, lista de espera e ingresos "
                "(si tienes acceso). Úsala para planes estratégicos, análisis, proyecciones "
                "o recomendaciones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "meses": {
                        "type": "integer",
                        "description": f"Meses a analizar ({MESES_MINIMO} a {MESES_MAXIMO}). Por defecto {MESES_DEFECTO}.",
                    }
                },
                "additionalProperties": False,
            },
        },
    }


def ejecutar(usuario, argumentos) -> tuple[int, dict]:
    if not isinstance(argumentos, dict):
        argumentos = {}
    permitidas = registros.entidades_permitidas(usuario)
    if not permitidas:
        return status.HTTP_403_FORBIDDEN, {"error": "Tu rol no tiene acceso a esta información."}

    meses = _meses(argumentos.get("meses"))
    hoy = timezone.localdate()
    rotulos = _rotulos(hoy, meses)
    inicio = date(int(rotulos[0][:4]), int(rotulos[0][5:]), 1)

    secciones = {}
    if "atenciones" in permitidas:
        secciones["citas_y_atenciones"] = _seccion_citas(usuario, inicio, hoy, rotulos)
        secciones["tratamientos"] = _seccion_tratamientos(usuario, inicio, hoy, rotulos)
        secciones["horas_pico"] = _seccion_horas(usuario, inicio, hoy)
        secciones["carga_doctores"] = _seccion_carga_doctores(usuario, inicio, hoy)
        secciones["sedes"] = _seccion_sedes(usuario, inicio, hoy)
    if "pacientes" in permitidas:
        secciones["pacientes"] = _seccion_pacientes(usuario, inicio, hoy, rotulos)
    if "lista_espera" in permitidas:
        secciones["lista_espera"] = _seccion_lista_espera(usuario)
    if "pagos" in permitidas:
        secciones["finanzas"] = _seccion_finanzas(inicio, hoy, rotulos)

    return status.HTTP_200_OK, {
        "periodo": {
            "desde": inicio.isoformat(),
            "hasta": hoy.isoformat(),
            "meses": meses,
            "mes_en_curso": rotulos[-1],
        },
        "secciones": secciones,
        "nota": NOTA,
    }

"""
Horarios de sede y feriados compartidos por la agenda.

Si una sede no tiene ningún turno configurado se considera sin restricción
(fail-open) para no bloquear datos históricos ni sedes recién creadas.
"""

from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from sedes.models import Feriado, HorarioSede


def turnos_del_dia(sede, fecha):
    """Turnos configurados para el día de la semana de `fecha`."""
    return list(
        HorarioSede.objects.filter(
            sede=sede, dia_semana=fecha.weekday()
        ).order_by("hora_apertura")
    )


def feriados_del_dia(sede, fecha):
    """Feriados de la sede y los globales (sede vacía) para esa fecha."""
    return list(
        Feriado.objects.filter(fecha=fecha)
        .filter(Q(sede=sede) | Q(sede__isnull=True))
        .order_by("hora_inicio")
    )


def _restar_intervalos(intervalos, bloqueos):
    """Resta los bloqueos `(inicio, fin)` de los intervalos `(inicio, fin)`."""
    resultado = list(intervalos)
    for bloqueo_inicio, bloqueo_fin in bloqueos:
        siguiente = []
        for inicio, fin in resultado:
            if bloqueo_fin <= inicio or bloqueo_inicio >= fin:
                siguiente.append((inicio, fin))
                continue
            if inicio < bloqueo_inicio:
                siguiente.append((inicio, bloqueo_inicio))
            if bloqueo_fin < fin:
                siguiente.append((bloqueo_fin, fin))
        resultado = siguiente
    return resultado


def intervalos_abiertos(sede, fecha):
    """
    Intervalos efectivamente abiertos (turnos menos feriados de medio día).

    Devuelve ``None`` si la sede no tiene ningún horario configurado; en ese
    caso no se restringe el agendamiento salvo por feriados explícitos.
    """
    feriados = feriados_del_dia(sede, fecha)
    if any(feriado.todo_el_dia for feriado in feriados):
        return []
    if not HorarioSede.objects.filter(sede=sede).exists():
        return None
    bloqueos = [
        (feriado.hora_inicio, feriado.hora_fin)
        for feriado in feriados
        if feriado.hora_inicio and feriado.hora_fin
    ]
    turnos = [(turno.hora_apertura, turno.hora_cierre) for turno in turnos_del_dia(sede, fecha)]
    return _restar_intervalos(turnos, bloqueos)


def motivo_cierre(sede, fecha):
    """Motivo por el que la sede no abre ese día, o ``None`` si abre."""
    feriados = feriados_del_dia(sede, fecha)
    completo = next((feriado for feriado in feriados if feriado.todo_el_dia), None)
    if completo:
        return f"Cerrado por feriado: {completo.nombre}."
    if not HorarioSede.objects.filter(sede=sede).exists():
        return None
    if not turnos_del_dia(sede, fecha):
        return "La sede no abre ese día."
    if not intervalos_abiertos(sede, fecha):
        return "La sede no tiene horario disponible ese día."
    return None


def error_horario(sede, fecha, inicio, fin):
    """
    Valida que una cita quepa completa dentro de un turno abierto.

    Devuelve el mensaje de error o ``None`` si es válida o si la sede no tiene
    horario configurado (los feriados explícitos siempre aplican).
    """
    abiertos = intervalos_abiertos(sede, fecha)
    if abiertos is None:
        for feriado in feriados_del_dia(sede, fecha):
            if (
                feriado.hora_inicio
                and feriado.hora_fin
                and inicio < feriado.hora_fin
                and fin > feriado.hora_inicio
            ):
                return f"El horario cae dentro del feriado: {feriado.nombre}."
        return None
    motivo = motivo_cierre(sede, fecha)
    if motivo:
        return motivo
    if not any(apertura <= inicio and fin <= cierre for apertura, cierre in abiertos):
        return "El horario está fuera del horario de atención de la sede."
    return None


def generar_huecos(intervalos, ocupadas, fecha, duracion_minutos):
    """
    Horas de inicio libres cada `duracion_minutos` dentro de los intervalos.

    Las citas `ocupadas` son objetos con `hora_inicio` y `hora_fin`. Si la fecha
    es hoy, se descartan las horas que ya pasaron.
    """
    ahora = timezone.localtime()
    huecos = []
    for apertura, cierre in intervalos:
        actual = datetime.combine(fecha, apertura)
        limite = datetime.combine(fecha, cierre)
        while actual + timedelta(minutes=duracion_minutos) <= limite:
            slot_inicio = actual.time()
            slot_fin = (actual + timedelta(minutes=duracion_minutos)).time()
            ocupado = any(
                atencion.hora_inicio < slot_fin and atencion.hora_fin > slot_inicio
                for atencion in ocupadas
            )
            pasado = fecha == ahora.date() and actual <= ahora.replace(tzinfo=None)
            if not ocupado and not pasado:
                huecos.append(actual.strftime("%H:%M"))
            actual += timedelta(minutes=duracion_minutos)
    return huecos

"""
Endpoints analíticos predefinidos (plan §5.4). Son consultas fijas y agregadas: no hay
SQL libre ni parámetros que elijan columnas. Todas filtran por las sedes del usuario
(el admin ve el consolidado) con `users.permisos.filtrar_por_sede`.

Formato común de respuesta, pensado para que el asistente IA y el frontend lo rendericen:
{
  "titulo": str,
  "tipo_grafica": "barras" | "linea",
  "ejes": {"x": str, "y": str},
  "datos": [{"etiqueta": str, "valor": int}],
  "total": int,
  "filtros": {"desde": str, "hasta": str, "sede": int | null}
}
"""

from collections import Counter
from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from agenda.models import Atencion, AtencionTrabajo
from users.permisos import filtrar_por_sede

MAX_DIAS_RANGO = 366


class ErrorFiltro(Exception):
    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo
        self.mensaje = mensaje


def _inicio_mes(hoy: date) -> date:
    return hoy.replace(day=1)


def _rango(params):
    """Devuelve (desde, hasta). Por defecto, desde el día 1 del mes actual hasta hoy."""
    hoy = timezone.localdate()
    desde = parse_date(params.get("desde", "")) if params.get("desde") else None
    hasta = parse_date(params.get("hasta", "")) if params.get("hasta") else None
    if params.get("desde") and desde is None:
        raise ErrorFiltro("desde", "La fecha inicial debe tener formato AAAA-MM-DD.")
    if params.get("hasta") and hasta is None:
        raise ErrorFiltro("hasta", "La fecha final debe tener formato AAAA-MM-DD.")
    desde = desde or _inicio_mes(hoy)
    hasta = hasta or hoy
    if desde > hasta:
        raise ErrorFiltro("hasta", "La fecha final debe ser igual o posterior a la inicial.")
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise ErrorFiltro("hasta", f"El rango no puede superar {MAX_DIAS_RANGO} días.")
    return desde, hasta


def _mes(params):
    """Devuelve (inicio, fin) del mes indicado con `mes=AAAA-MM`, o del mes actual."""
    if params.get("mes"):
        try:
            anio, mes = (int(p) for p in params["mes"].split("-"))
            inicio = date(anio, mes, 1)
        except (ValueError, TypeError):
            raise ErrorFiltro("mes", "El mes debe tener formato AAAA-MM.")
    else:
        inicio = _inicio_mes(timezone.localdate())
    fin = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return inicio, fin


def _sede(params):
    valor = params.get("sede", "")
    if not valor:
        return None
    if not valor.isdigit():
        raise ErrorFiltro("sede", "Indica una sede válida.")
    return int(valor)


class AnaliticaBase(APIView):
    """Base común: resuelve filtros, aplica permisos por sede y formatea la respuesta."""

    def _base(self, request):
        """Atenciones visibles para el usuario, opcionalmente filtradas por una sede."""
        qs = filtrar_por_sede(Atencion.objects.all(), request.user)
        sede = _sede(request.query_params)
        if sede is not None:
            qs = qs.filter(sede_id=sede)
        return qs, sede

    def _responder(self, titulo, tipo, eje_x, eje_y, datos, filtros):
        return Response(
            {
                "titulo": titulo,
                "tipo_grafica": tipo,
                "ejes": {"x": eje_x, "y": eje_y},
                "datos": [{"etiqueta": e, "valor": v} for e, v in datos],
                "total": sum(v for _, v in datos),
                "filtros": filtros,
            }
        )

    def _error(self, error: ErrorFiltro):
        return Response({error.campo: error.mensaje}, status=status.HTTP_400_BAD_REQUEST)


class CitasHoyView(AnaliticaBase):
    """Citas del día por estado (incluye canceladas para dar contexto operativo)."""

    def get(self, request):
        try:
            sede_qs, sede = self._base(request)
            hoy = timezone.localdate()
        except ErrorFiltro as error:
            return self._error(error)
        conteo = Counter(
            sede_qs.filter(fecha=hoy).values_list("estado", flat=True)
        )
        datos = [
            (etiqueta, conteo.get(estado, 0))
            for estado, etiqueta in Atencion.Estado.choices
        ]
        return self._responder(
            "Citas de hoy por estado",
            "barras",
            "Estado",
            "Citas",
            datos,
            {"desde": hoy.isoformat(), "hasta": hoy.isoformat(), "sede": sede},
        )


class AtendidosMesView(AnaliticaBase):
    """Atenciones completadas por día en un mes (`mes=AAAA-MM`, por defecto el actual)."""

    def get(self, request):
        try:
            sede_qs, sede = self._base(request)
            inicio, fin = _mes(request.query_params)
        except ErrorFiltro as error:
            return self._error(error)
        completadas = sede_qs.filter(
            estado=Atencion.Estado.COMPLETADA, fecha__range=(inicio, fin)
        )
        conteo = Counter(completadas.values_list("fecha", flat=True))
        datos = [
            (dia.isoformat(), conteo.get(dia, 0))
            for dia in (inicio + timedelta(days=i) for i in range((fin - inicio).days + 1))
        ]
        return self._responder(
            "Pacientes atendidos por día",
            "linea",
            "Fecha",
            "Atenciones completadas",
            datos,
            {"desde": inicio.isoformat(), "hasta": fin.isoformat(), "sede": sede},
        )


class _RangoAtencionesView(AnaliticaBase):
    """Base para vistas sobre citas no canceladas dentro de un rango de fechas."""

    def _atenciones(self, request):
        qs, sede = self._base(request)
        desde, hasta = _rango(request.query_params)
        qs = qs.exclude(estado=Atencion.Estado.CANCELADA).filter(
            fecha__range=(desde, hasta)
        )
        return qs, desde, hasta, sede


class PorServicioView(_RangoAtencionesView):
    """Cantidad de citas por tipo de trabajo (una cita con varios trabajos cuenta en cada uno)."""

    def get(self, request):
        try:
            atenciones, desde, hasta, sede = self._atenciones(request)
        except ErrorFiltro as error:
            return self._error(error)
        filas = (
            AtencionTrabajo.objects.filter(atencion__in=atenciones)
            .values("tipo_trabajo__nombre")
            .annotate(cantidad=Count("atencion", distinct=True))
            .order_by("-cantidad", "tipo_trabajo__nombre")
        )
        datos = [(f["tipo_trabajo__nombre"], f["cantidad"]) for f in filas]
        return self._responder(
            "Citas por tipo de trabajo",
            "barras",
            "Tipo de trabajo",
            "Citas",
            datos,
            {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "sede": sede},
        )


class PorHoraView(_RangoAtencionesView):
    """Cantidad de citas por hora de inicio."""

    def get(self, request):
        try:
            atenciones, desde, hasta, sede = self._atenciones(request)
        except ErrorFiltro as error:
            return self._error(error)
        conteo = Counter(
            hora.hour for hora in atenciones.values_list("hora_inicio", flat=True)
        )
        datos = [(f"{hora:02d}:00", conteo[hora]) for hora in sorted(conteo)]
        return self._responder(
            "Citas por hora de inicio",
            "barras",
            "Hora",
            "Citas",
            datos,
            {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "sede": sede},
        )


class PorSedeView(_RangoAtencionesView):
    """Cantidad de citas por sede. El admin ve todas; el resto, solo sus sedes."""

    def get(self, request):
        try:
            atenciones, desde, hasta, sede = self._atenciones(request)
        except ErrorFiltro as error:
            return self._error(error)
        filas = (
            atenciones.values("sede__nombre")
            .annotate(cantidad=Count("id"))
            .order_by("-cantidad", "sede__nombre")
        )
        datos = [(f["sede__nombre"], f["cantidad"]) for f in filas]
        return self._responder(
            "Citas por sede",
            "barras",
            "Sede",
            "Citas",
            datos,
            {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "sede": sede},
        )

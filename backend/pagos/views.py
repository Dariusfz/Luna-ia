from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from agenda.models import Atencion
from users.permisos import EsAdmin

from .models import MetodoPago, Pago, PagoDoctor
from .serializers import PagoDoctorSerializer, PagoSerializer


def _total(queryset) -> Decimal:
    return queryset.aggregate(total=Sum("monto"))["total"] or Decimal("0")


def _monto(valor: Decimal) -> str:
    return f"{valor:.2f}"


class PagoViewSet(viewsets.ModelViewSet):
    """Abonos de pacientes. Solo el administrador ve y registra movimientos de caja."""

    serializer_class = PagoSerializer
    permission_classes = [EsAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Pago.objects.select_related(
            "atencion",
            "atencion__sede",
            "atencion__paciente",
            "atencion__doctor",
            "atencion__tipo_trabajo",
            "registrado_por",
        ).prefetch_related(
            "atencion__trabajos__tipo_trabajo",
            "atencion__pagos",
            "atencion__pagos_doctor",
        )
        params = self.request.query_params
        if params.get("atencion", "").isdigit():
            qs = qs.filter(atencion_id=int(params["atencion"]))
        if params.get("sede", "").isdigit():
            qs = qs.filter(atencion__sede_id=int(params["sede"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        if params.get("metodo") in MetodoPago.values:
            qs = qs.filter(metodo=params["metodo"])
        return qs


class PagoDoctorViewSet(viewsets.ModelViewSet):
    """Pagos reales a doctores. Solo el administrador."""

    serializer_class = PagoDoctorSerializer
    permission_classes = [EsAdmin]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = PagoDoctor.objects.select_related(
            "atencion",
            "atencion__sede",
            "atencion__paciente",
            "atencion__tipo_trabajo",
            "doctor",
            "registrado_por",
        ).prefetch_related(
            "atencion__trabajos__tipo_trabajo",
            "atencion__pagos",
            "atencion__pagos_doctor",
        )
        params = self.request.query_params
        if params.get("atencion", "").isdigit():
            qs = qs.filter(atencion_id=int(params["atencion"]))
        if params.get("doctor", "").isdigit():
            qs = qs.filter(doctor_id=int(params["doctor"]))
        if params.get("sede", "").isdigit():
            qs = qs.filter(atencion__sede_id=int(params["sede"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        if params.get("metodo") in MetodoPago.values:
            qs = qs.filter(metodo=params["metodo"])
        return qs


class ResumenCajaView(APIView):
    """Totales de caja por rango de fechas y sede. Solo el administrador."""

    permission_classes = [EsAdmin]

    def get(self, request):
        params = request.query_params
        hoy = timezone.localdate()
        desde = parse_date(params.get("desde", "")) or hoy
        hasta = parse_date(params.get("hasta", "")) or desde
        if desde > hasta:
            return Response(
                {"hasta": "La fecha final debe ser igual o posterior a la inicial."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sede_id = params.get("sede", "")
        if sede_id and not sede_id.isdigit():
            return Response(
                {"sede": "Indica una sede válida."}, status=status.HTTP_400_BAD_REQUEST
            )
        sede_id = int(sede_id) if sede_id else None

        pagos = Pago.objects.filter(fecha__range=(desde, hasta))
        pagos_doctor = PagoDoctor.objects.filter(fecha__range=(desde, hasta))
        if sede_id:
            pagos = pagos.filter(atencion__sede_id=sede_id)
            pagos_doctor = pagos_doctor.filter(atencion__sede_id=sede_id)

        abonos_caja = _total(pagos)
        pagado_doctores = _total(pagos_doctor)

        atenciones = (
            Atencion.objects.filter(fecha__range=(desde, hasta))
            .exclude(estado=Atencion.Estado.CANCELADA)
            .select_related("tipo_trabajo")
            .prefetch_related("pagos")
        )
        if sede_id:
            atenciones = atenciones.filter(sede_id=sede_id)
        atenciones = list(atenciones)

        completadas = [
            atencion
            for atencion in atenciones
            if atencion.estado == Atencion.Estado.COMPLETADA
        ]
        pendientes = [
            atencion
            for atencion in atenciones
            if atencion.estado
            in (Atencion.Estado.PENDIENTE, Atencion.Estado.CONFIRMADA)
        ]

        cobrado = sum(
            (atencion.precio_paciente for atencion in completadas), Decimal("0")
        )
        comision_doctores = sum(
            (atencion.honorario_doctor for atencion in completadas), Decimal("0")
        )
        por_cobrar = Decimal("0")
        for atencion in pendientes:
            abonado = sum(
                (pago.monto for pago in atencion.pagos.all()), Decimal("0")
            )
            por_cobrar += max(atencion.precio_paciente - abonado, Decimal("0"))
        ganancia = cobrado - comision_doctores

        dias = {}
        for atencion in atenciones:
            valores = dias.setdefault(
                atencion.fecha,
                {
                    "cobrado": Decimal("0"),
                    "por_cobrar": Decimal("0"),
                    "comision_doctores": Decimal("0"),
                },
            )
            if atencion.estado == Atencion.Estado.COMPLETADA:
                valores["cobrado"] += atencion.precio_paciente
                valores["comision_doctores"] += atencion.honorario_doctor
            elif atencion.estado in (
                Atencion.Estado.PENDIENTE,
                Atencion.Estado.CONFIRMADA,
            ):
                abonado = sum(
                    (pago.monto for pago in atencion.pagos.all()), Decimal("0")
                )
                valores["por_cobrar"] += max(
                    atencion.precio_paciente - abonado, Decimal("0")
                )

        por_dia = [
            {
                "fecha": fecha.isoformat(),
                "cobrado": _monto(valores["cobrado"]),
                "por_cobrar": _monto(valores["por_cobrar"]),
                "comision_doctores": _monto(valores["comision_doctores"]),
                "ganancia": _monto(
                    valores["cobrado"] - valores["comision_doctores"]
                ),
            }
            for fecha, valores in sorted(dias.items())
        ]

        return Response(
            {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "sede": sede_id,
                "cobrado": _monto(cobrado),
                "por_cobrar": _monto(por_cobrar),
                "comision_doctores": _monto(comision_doctores),
                "ganancia": _monto(ganancia),
                "abonos_caja": _monto(abonos_caja),
                "pagado_doctores": _monto(pagado_doctores),
                "cantidad_cobros": len(completadas),
                "cantidad_abonos": pagos.count(),
                "cantidad_pagos_doctores": pagos_doctor.count(),
                "por_dia": por_dia,
            }
        )

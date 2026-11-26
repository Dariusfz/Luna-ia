from django.db.models import Q
from django.utils.dateparse import parse_date, parse_time
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from sedes.models import Sede
from users.models import Doctor
from users.permisos import EsAdmin, filtrar_por_sede, puede_usar_sede

from .horarios import (
    feriados_del_dia,
    generar_huecos,
    intervalos_abiertos,
    motivo_cierre,
    turnos_del_dia,
)
from .models import Atencion, JornadaExterna, ListaEspera
from .serializers import (
    ESTADOS_QUE_OCUPAN,
    AtencionSerializer,
    JornadaExternaSerializer,
    ListaEsperaSerializer,
)

METODOS_SIN_BORRADO = ["get", "post", "put", "patch", "head", "options"]


def _hora(valor):
    return valor.strftime("%H:%M")


def _valor_historial(valor):
    """Convierte fechas, horas y decimales a texto para el JSON del historial."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


class AtencionViewSet(viewsets.ModelViewSet):
    """
    Atenciones de las sedes del usuario. El admin ve todas. No se borran.

    Filtros del listado: sede, doctor, desde, hasta (fechas AAAA-MM-DD).
    Consulta de disponibilidad: GET /api/atenciones/disponibilidad/.
    """

    serializer_class = AtencionSerializer
    http_method_names = METODOS_SIN_BORRADO

    def get_queryset(self):
        qs = Atencion.objects.select_related(
            "sede", "doctor", "paciente", "tipo_trabajo", "creado_por"
        ).prefetch_related(
            "trabajos__tipo_trabajo", "pagos", "pagos_doctor"
        )
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("sede", "").isdigit():
            qs = qs.filter(sede_id=int(params["sede"]))
        if params.get("doctor", "").isdigit():
            qs = qs.filter(doctor_id=int(params["doctor"]))
        if params.get("paciente", "").isdigit():
            qs = qs.filter(paciente_id=int(params["paciente"]))
        if params.get("desde"):
            qs = qs.filter(fecha__gte=params["desde"])
        if params.get("hasta"):
            qs = qs.filter(fecha__lte=params["hasta"])
        if params.get("estado"):
            estados = [
                estado
                for estado in params["estado"].split(",")
                if estado in Atencion.Estado.values
            ]
            qs = qs.filter(estado__in=estados)
        if params.get("origen") in Atencion.Origen.values:
            qs = qs.filter(origen=params["origen"])
        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(paciente__nombres__icontains=texto)
                | Q(paciente__apellidos__icontains=texto)
                | Q(tipo_trabajo__nombre__icontains=texto)
                | Q(trabajos__tipo_trabajo__nombre__icontains=texto)
            ).distinct()
        return qs

    @action(detail=False, methods=["get"])
    def disponibilidad(self, request):
        """
        Horarios ocupados y libres de los doctores de una sede en una fecha.

        Parámetros: sede (obligatorio), fecha (AAAA-MM-DD, obligatorio),
        doctor (opcional), hora_inicio y hora_fin (opcionales, ambos juntos) y
        duracion en minutos (opcional, 5-240, por defecto 20).

        Devuelve el horario configurado, los feriados del día, si la sede abre
        y, por doctor, las citas ocupadas y los huecos libres. Cuando se envían
        hora_inicio y hora_fin, cada doctor incluye ``disponible``.
        """
        params = request.query_params

        sede_id = params.get("sede", "")
        if not sede_id.isdigit():
            return Response(
                {"sede": "Indica una sede válida."}, status=status.HTTP_400_BAD_REQUEST
            )
        sede = Sede.objects.filter(pk=int(sede_id)).first()
        if sede is None or not puede_usar_sede(request.user, sede):
            return Response(
                {"sede": "La sede no existe o no está disponible para tu usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha = parse_date(params.get("fecha", ""))
        if fecha is None:
            return Response(
                {"fecha": "Usa el formato AAAA-MM-DD."}, status=status.HTTP_400_BAD_REQUEST
            )

        doctores = Doctor.objects.filter(activo=True, sedes=sede)
        doctor_id = params.get("doctor", "")
        if doctor_id:
            if not doctor_id.isdigit():
                return Response(
                    {"doctor": "Indica un doctor válido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            doctores = doctores.filter(pk=int(doctor_id))
            if not doctores.exists():
                return Response(
                    {"doctor": "El doctor no existe o no atiende en esa sede."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        hora_inicio = params.get("hora_inicio", "")
        hora_fin = params.get("hora_fin", "")
        if bool(hora_inicio) != bool(hora_fin):
            return Response(
                {"hora_inicio": "Indica hora_inicio y hora_fin juntas."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        inicio = fin = None
        if hora_inicio and hora_fin:
            inicio = parse_time(hora_inicio)
            fin = parse_time(hora_fin)
            if inicio is None or fin is None or fin <= inicio:
                return Response(
                    {
                        "hora_inicio": (
                            "Usa horas HH:MM y con la hora fin posterior a la inicial."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        resultado = []
        duracion_txt = params.get("duracion", "20")
        try:
            duracion = int(duracion_txt)
        except (TypeError, ValueError):
            duracion = 0
        if not 5 <= duracion <= 240:
            return Response(
                {"duracion": "Usa una duración entre 5 y 240 minutos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        abiertos = intervalos_abiertos(sede, fecha)
        turnos = turnos_del_dia(sede, fecha)
        feriados = feriados_del_dia(sede, fecha)

        for doctor in doctores:
            ocupadas = list(
                Atencion.objects.filter(
                    doctor=doctor,
                    fecha=fecha,
                    estado__in=ESTADOS_QUE_OCUPAN,
                )
                .select_related("paciente")
                .order_by("hora_inicio")
            )
            item = {
                "doctor": doctor.pk,
                "doctor_nombre": f"{doctor.nombres} {doctor.apellidos}",
                "ocupados": [
                    {
                        "atencion": atencion.pk,
                        "hora_inicio": _hora(atencion.hora_inicio),
                        "hora_fin": _hora(atencion.hora_fin),
                        "paciente": (
                            f"{atencion.paciente.nombres} {atencion.paciente.apellidos}"
                        ),
                        "estado": atencion.estado,
                    }
                    for atencion in ocupadas
                ],
            }
            if abiertos is not None:
                item["huecos"] = generar_huecos(abiertos, ocupadas, fecha, duracion)
            if inicio and fin:
                dentro = abiertos is None or any(
                    apertura <= inicio and fin <= cierre for apertura, cierre in abiertos
                )
                item["disponible"] = dentro and not any(
                    atencion.hora_inicio < fin and atencion.hora_fin > inicio
                    for atencion in ocupadas
                )
            resultado.append(item)

        datos = {
            "sede": {"id": sede.pk, "nombre": sede.nombre},
            "fecha": fecha.isoformat(),
            "duracion": duracion,
            "horario_configurado": abiertos is not None,
            "abierta": bool(abiertos) if abiertos is not None else True,
            "motivo": motivo_cierre(sede, fecha) if abiertos is not None else None,
            "horarios": [
                {
                    "hora_inicio": _hora(turno.hora_apertura),
                    "hora_fin": _hora(turno.hora_cierre),
                }
                for turno in turnos
            ],
            "abiertos": [
                {"hora_inicio": _hora(apertura), "hora_fin": _hora(cierre)}
                for apertura, cierre in (abiertos or [])
            ],
            "feriados": [
                {
                    "nombre": feriado.nombre,
                    "todo_el_dia": feriado.todo_el_dia,
                    "hora_inicio": _hora(feriado.hora_inicio) if feriado.hora_inicio else None,
                    "hora_fin": _hora(feriado.hora_fin) if feriado.hora_fin else None,
                }
                for feriado in feriados
            ],
            "doctores": resultado,
        }
        if inicio and fin:
            datos["consulta"] = {
                "hora_inicio": _hora(inicio),
                "hora_fin": _hora(fin),
            }
        return Response(datos)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        """Cambios registrados de una cita, del más reciente al más antiguo."""
        atencion = self.get_object()
        tipos = {"+": "Creada", "~": "Actualizada", "-": "Eliminada"}
        registros = []
        for registro in atencion.history.all().select_related("history_user"):
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


class ListaEsperaViewSet(viewsets.ModelViewSet):
    """
    Pacientes en espera de un cupo, filtrados por las sedes del usuario.

    Filtros del listado: sede, doctor, estado (uno o varios separados por coma),
    prioridad y q (nombre del paciente o motivo).
    """

    serializer_class = ListaEsperaSerializer
    http_method_names = METODOS_SIN_BORRADO

    def get_queryset(self):
        qs = ListaEspera.objects.select_related(
            "sede", "paciente", "doctor", "tipo_trabajo", "atencion"
        )
        qs = filtrar_por_sede(qs, self.request.user, campo_sede="sede")
        if self.action != "list":
            return qs
        params = self.request.query_params
        if params.get("sede", "").isdigit():
            qs = qs.filter(sede_id=int(params["sede"]))
        if params.get("doctor", "").isdigit():
            qs = qs.filter(doctor_id=int(params["doctor"]))
        if params.get("estado"):
            estados = [
                estado
                for estado in params["estado"].split(",")
                if estado in ListaEspera.Estado.values
            ]
            qs = qs.filter(estado__in=estados)
        if params.get("prioridad", "").isdigit():
            qs = qs.filter(prioridad=int(params["prioridad"]))
        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(paciente__nombres__icontains=texto)
                | Q(paciente__apellidos__icontains=texto)
                | Q(motivo__icontains=texto)
            )
        return qs

    @action(detail=True, methods=["post"])
    def agendar(self, request, pk=None):
        """Convierte la espera en una cita, reutilizando las validaciones de agenda."""
        espera = self.get_object()
        if espera.estado == ListaEspera.Estado.CANCELADO:
            return Response(
                {"detail": "No se puede agendar una espera cancelada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if espera.estado == ListaEspera.Estado.AGENDADO and espera.atencion_id:
            return Response(
                {"detail": "Esta espera ya fue convertida en cita."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doctor_id = request.data.get("doctor", espera.doctor_id)
        tipo_trabajo_id = request.data.get("tipo_trabajo", espera.tipo_trabajo_id)
        if not doctor_id or not tipo_trabajo_id:
            return Response(
                {"detail": "Indica el doctor y el tipo de trabajo para agendar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        datos = {
            "sede": espera.sede_id,
            "paciente": espera.paciente_id,
            "doctor": doctor_id,
            "tipo_trabajo": tipo_trabajo_id,
            "fecha": request.data.get("fecha"),
            "hora_inicio": request.data.get("hora_inicio"),
            "hora_fin": request.data.get("hora_fin"),
            "procedimiento": request.data.get("procedimiento", ""),
            "observaciones": request.data.get("observaciones", ""),
            "honorario_doctor": request.data.get("honorario_doctor", 0),
        }
        datos_cita = AtencionSerializer(
            data=datos, context=self.get_serializer_context()
        )
        datos_cita.is_valid(raise_exception=True)
        atencion = datos_cita.save()

        espera.atencion = atencion
        espera.estado = ListaEspera.Estado.AGENDADO
        espera.save(update_fields=["atencion", "estado", "actualizada"])
        return Response(
            ListaEsperaSerializer(espera, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class JornadaExternaViewSet(viewsets.ModelViewSet):
    """Trabajos fuera de la clínica. Solo el administrador. No guardan datos de pacientes."""

    serializer_class = JornadaExternaSerializer
    permission_classes = [EsAdmin]
    http_method_names = METODOS_SIN_BORRADO

    def get_queryset(self):
        return JornadaExterna.objects.select_related("doctor", "lugar", "tipo_trabajo")

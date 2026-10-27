from django.utils import timezone
from rest_framework import serializers

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO
from pacientes.querysets import pacientes_visibles
from users.models import Doctor
from users.permisos import puede_usar_sede

from .horarios import error_horario
from .models import Atencion, JornadaExterna, ListaEspera

# Estados que reservan el horario del doctor y del paciente.
ESTADOS_QUE_OCUPAN = (Atencion.Estado.PENDIENTE, Atencion.Estado.CONFIRMADA)


class AtencionSerializer(serializers.ModelSerializer):
    # Nombres legibles para las tablas (solo lectura).
    sede_nombre = serializers.SerializerMethodField()
    doctor_nombre = serializers.SerializerMethodField()
    doctor_tipo = serializers.CharField(source="doctor.tipo", read_only=True)
    paciente_nombre = serializers.SerializerMethodField()
    tipo_trabajo_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Atencion
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "doctor",
            "doctor_nombre",
            "doctor_tipo",
            "paciente",
            "paciente_nombre",
            "tipo_trabajo",
            "tipo_trabajo_nombre",
            "estado",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "procedimiento",
            "honorario_doctor",
            "observaciones",
            "creada",
            "actualizada",
        ]
        read_only_fields = ["id", "creada", "actualizada"]

    def get_sede_nombre(self, obj) -> str:
        return obj.sede.nombre

    def get_doctor_nombre(self, obj) -> str:
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_tipo_trabajo_nombre(self, obj) -> str:
        return obj.tipo_trabajo.nombre

    def validate_sede(self, sede):
        if not puede_usar_sede(self.context["request"].user, sede):
            raise serializers.ValidationError("No puedes registrar atenciones en esa sede.")
        return sede

    def validate_paciente(self, paciente):
        if not pacientes_visibles(self.context["request"].user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError("El paciente no existe o no está disponible para tu sede.")
        if not paciente.activo:
            raise serializers.ValidationError("El paciente está inactivo.")
        return paciente

    def validate_doctor(self, doctor):
        if not Doctor.objects.filter(pk=doctor.pk, activo=True).exists():
            raise serializers.ValidationError("El doctor está inactivo.")
        return doctor

    def validate_tipo_trabajo(self, tipo):
        if not tipo.activo:
            raise serializers.ValidationError("Este tipo de trabajo está inactivo.")
        return tipo

    def validate_honorario_doctor(self, valor):
        if valor < 0:
            raise serializers.ValidationError("El honorario no puede ser negativo.")
        if valor > MONTO_MAXIMO:
            raise serializers.ValidationError(MENSAJE_MONTO_MAXIMO)
        return valor

    def validate(self, data):
        inicio = data.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        fin = data.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la de inicio."}
            )
        # Un doctor solo atiende en las sedes que tiene asignadas.
        sede = data.get("sede", getattr(self.instance, "sede", None))
        doctor = data.get("doctor", getattr(self.instance, "doctor", None))
        if sede and doctor and not doctor.sedes.filter(pk=sede.pk).exists():
            raise serializers.ValidationError(
                {"doctor": "Este doctor no tiene asignada la sede seleccionada."}
            )
        paciente = data.get("paciente", getattr(self.instance, "paciente", None))
        estado = data.get("estado", getattr(self.instance, "estado", Atencion.Estado.PENDIENTE))
        fecha = data.get("fecha", getattr(self.instance, "fecha", None))
        # Una cita futura no puede marcarse como completada antes de ocurrir.
        if estado == Atencion.Estado.COMPLETADA and fecha and fecha > timezone.localdate():
            raise serializers.ValidationError(
                {"estado": "No puedes completar una cita con fecha futura."}
            )
        # Una cita nueva nace siempre pendiente; el estado se cambia al editarla.
        if self.instance is None and estado != Atencion.Estado.PENDIENTE:
            raise serializers.ValidationError(
                {"estado": "Una cita nueva se crea siempre como pendiente."}
            )
        # Solo se agendan citas para hoy o fechas futuras. Las citas existentes
        # se pueden seguir editando aunque su fecha ya haya pasado.
        if self.instance is None and fecha and fecha < timezone.localdate():
            raise serializers.ValidationError(
                {"fecha": "No puedes crear una cita en una fecha pasada."}
            )
        # La cita debe caber en un turno abierto de la sede y no caer en feriado.
        # Se valida al crear o cuando cambia sede, fecha u horas.
        campos_horario = {"sede", "fecha", "hora_inicio", "hora_fin"}
        if (
            estado in ESTADOS_QUE_OCUPAN
            and sede
            and fecha
            and inicio
            and fin
            and (self.instance is None or campos_horario & set(data.keys()))
        ):
            error = error_horario(sede, fecha, inicio, fin)
            if error:
                raise serializers.ValidationError({"hora_inicio": error})
        # Un doctor no puede tener dos citas activas que se solapen, ni en sedes distintas.
        # Un paciente tampoco puede estar en dos citas activas a la vez.
        if estado in ESTADOS_QUE_OCUPAN and doctor and paciente and fecha and inicio and fin:
            choques_doctor = Atencion.objects.filter(
                doctor=doctor,
                fecha=fecha,
                estado__in=ESTADOS_QUE_OCUPAN,
                hora_inicio__lt=fin,
                hora_fin__gt=inicio,
            )
            choques_paciente = Atencion.objects.filter(
                paciente=paciente,
                fecha=fecha,
                estado__in=ESTADOS_QUE_OCUPAN,
                hora_inicio__lt=fin,
                hora_fin__gt=inicio,
            )
            if self.instance is not None:
                choques_doctor = choques_doctor.exclude(pk=self.instance.pk)
                choques_paciente = choques_paciente.exclude(pk=self.instance.pk)
            if choques_doctor.exists():
                raise serializers.ValidationError(
                    {"hora_inicio": "El doctor ya tiene una cita en ese horario."}
                )
            if choques_paciente.exists():
                raise serializers.ValidationError(
                    {"hora_inicio": "El paciente ya tiene una cita en ese horario."}
                )
        return data


class JornadaExternaSerializer(serializers.ModelSerializer):
    class Meta:
        model = JornadaExterna
        fields = [
            "id",
            "doctor",
            "lugar",
            "tipo_trabajo",
            "fecha",
            "hora_inicio",
            "hora_fin",
            "monto_cobrado",
            "observaciones",
            "creada",
        ]
        read_only_fields = ["id", "creada"]

    def validate(self, data):
        inicio = data.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        fin = data.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if inicio and fin and fin <= inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la de inicio."}
            )
        return data


class ListaEsperaSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    paciente_nombre = serializers.SerializerMethodField()
    doctor_nombre = serializers.SerializerMethodField()
    tipo_trabajo_nombre = serializers.SerializerMethodField()
    prioridad_nombre = serializers.CharField(source="get_prioridad_display", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    atencion_fecha = serializers.DateField(source="atencion.fecha", read_only=True)
    atencion_hora_inicio = serializers.TimeField(
        source="atencion.hora_inicio", read_only=True
    )

    class Meta:
        model = ListaEspera
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "paciente",
            "paciente_nombre",
            "doctor",
            "doctor_nombre",
            "tipo_trabajo",
            "tipo_trabajo_nombre",
            "prioridad",
            "prioridad_nombre",
            "estado",
            "estado_nombre",
            "fecha_deseada",
            "motivo",
            "atencion",
            "atencion_fecha",
            "atencion_hora_inicio",
            "creada",
            "actualizada",
        ]
        read_only_fields = ["id", "creada", "actualizada", "atencion"]

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str | None:
        if not obj.doctor_id:
            return None
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def get_tipo_trabajo_nombre(self, obj) -> str | None:
        return obj.tipo_trabajo.nombre if obj.tipo_trabajo_id else None

    def validate_sede(self, sede):
        if not puede_usar_sede(self.context["request"].user, sede):
            raise serializers.ValidationError("No puedes usar esa sede.")
        return sede

    def validate_paciente(self, paciente):
        if not pacientes_visibles(self.context["request"].user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError(
                "El paciente no existe o no está disponible para tu sede."
            )
        if not paciente.activo:
            raise serializers.ValidationError("El paciente está inactivo.")
        return paciente

    def validate_doctor(self, doctor):
        if not Doctor.objects.filter(pk=doctor.pk, activo=True).exists():
            raise serializers.ValidationError("El doctor está inactivo.")
        return doctor

    def validate_tipo_trabajo(self, tipo):
        if not tipo.activo:
            raise serializers.ValidationError("Este tipo de trabajo está inactivo.")
        return tipo

    def validate(self, data):
        sede = data.get("sede", getattr(self.instance, "sede", None))
        doctor = data.get("doctor", getattr(self.instance, "doctor", None))
        if sede and doctor and not doctor.sedes.filter(pk=sede.pk).exists():
            raise serializers.ValidationError(
                {"doctor": "Este doctor no tiene asignada la sede seleccionada."}
            )
        estado = data.get(
            "estado", getattr(self.instance, "estado", ListaEspera.Estado.ESPERANDO)
        )
        if self.instance is None and estado != ListaEspera.Estado.ESPERANDO:
            raise serializers.ValidationError(
                {"estado": "Una espera nueva se crea siempre en espera."}
            )
        if (
            self.instance is not None
            and estado == ListaEspera.Estado.AGENDADO
            and not self.instance.atencion_id
        ):
            raise serializers.ValidationError(
                {"estado": "Usa la acción Agendar para convertir la espera en cita."}
            )
        return data

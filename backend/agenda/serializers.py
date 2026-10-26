from django.utils import timezone
from rest_framework import serializers

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO
from pacientes.querysets import pacientes_visibles
from users.models import Doctor
from users.permisos import puede_usar_sede

from .models import Atencion, JornadaExterna


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
        # Una cita futura no puede marcarse como completada antes de ocurrir.
        estado = data.get("estado", getattr(self.instance, "estado", Atencion.Estado.PENDIENTE))
        fecha = data.get("fecha", getattr(self.instance, "fecha", None))
        if estado == Atencion.Estado.COMPLETADA and fecha and fecha > timezone.localdate():
            raise serializers.ValidationError(
                {"estado": "No puedes completar una cita con fecha futura."}
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

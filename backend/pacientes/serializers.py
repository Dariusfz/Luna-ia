from datetime import date

from django.db import transaction
from rest_framework import serializers

from config.validadores import MENSAJE_TELEFONO, normalizar_telefono_hn
from users.permisos import puede_usar_sede

from .models import HallazgoDental, HistoriaClinica, Odontograma, Paciente
from .querysets import pacientes_visibles


class PacienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paciente
        fields = [
            "id",
            "nombres",
            "apellidos",
            "identidad",
            "fecha_nacimiento",
            "sexo",
            "telefono",
            "email",
            "direccion",
            "sede_origen",
            "alergias",
            "antecedentes_medicos",
            "medicamentos_actuales",
            "observaciones",
            "activo",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]
        # Todo paciente tiene una sede de origen (plan §8).
        extra_kwargs = {
            "sede_origen": {"required": True, "allow_null": False},
            "direccion": {
                "required": True,
                "allow_blank": False,
                "error_messages": {"required": "Escribe la dirección o lugar de residencia.", "blank": "Escribe la dirección o lugar de residencia."},
            },
            "fecha_nacimiento": {
                "error_messages": {"invalid": "Escribe una fecha válida con año de 4 dígitos."}
            },
        }

    def validate_fecha_nacimiento(self, valor):
        if valor is None:
            return valor
        hoy = date.today()
        if valor.year < 1900 or valor > hoy:
            raise serializers.ValidationError(
                f"La fecha debe estar entre 1900 y hoy ({hoy.strftime('%d/%m/%Y')})."
            )
        return valor

    def validate_telefono(self, valor):
        try:
            return normalizar_telefono_hn(valor)
        except ValueError:
            raise serializers.ValidationError(MENSAJE_TELEFONO)

    def validate_sede_origen(self, sede):
        request = self.context["request"]
        if sede is not None and not puede_usar_sede(request.user, sede):
            raise serializers.ValidationError("No tienes acceso a esa sede.")
        return sede


class _ValidacionClinicaMixin:
    """Reglas comunes: paciente visible y sede permitida para el usuario."""

    def validate_paciente(self, paciente):
        request = self.context.get("request")
        if request and not pacientes_visibles(request.user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError("No tienes acceso a ese paciente.")
        return paciente

    def validate_sede(self, sede):
        request = self.context.get("request")
        if request and not puede_usar_sede(request.user, sede):
            raise serializers.ValidationError("No tienes acceso a esa sede.")
        return sede


class HallazgoDentalSerializer(serializers.ModelSerializer):
    cara_nombre = serializers.CharField(source="get_cara_display", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = HallazgoDental
        fields = [
            "id",
            "diente",
            "cara",
            "cara_nombre",
            "estado",
            "estado_nombre",
            "observacion",
        ]
        read_only_fields = ["id"]


class OdontogramaSerializer(_ValidacionClinicaMixin, serializers.ModelSerializer):
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    doctor_nombre = serializers.SerializerMethodField()
    hallazgos = HallazgoDentalSerializer(many=True, required=False)

    class Meta:
        model = Odontograma
        fields = [
            "id",
            "paciente",
            "paciente_nombre",
            "historia",
            "sede",
            "sede_nombre",
            "doctor",
            "doctor_nombre",
            "fecha",
            "notas",
            "hallazgos",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str | None:
        if not obj.doctor_id:
            return None
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def validate(self, datos):
        paciente = datos.get("paciente") or getattr(self.instance, "paciente", None)
        sede = datos.get("sede") or getattr(self.instance, "sede", None)
        historia = datos.get("historia") or getattr(self.instance, "historia", None)
        if historia is not None:
            if paciente and historia.paciente_id != paciente.pk:
                raise serializers.ValidationError(
                    {"historia": "La historia clínica pertenece a otro paciente."}
                )
            if sede and historia.sede_id != sede.pk:
                raise serializers.ValidationError(
                    {"historia": "La historia clínica es de otra sede."}
                )
            existente = Odontograma.objects.filter(historia=historia)
            if self.instance is not None:
                existente = existente.exclude(pk=self.instance.pk)
            if existente.exists():
                raise serializers.ValidationError(
                    {"historia": "Esa historia clínica ya tiene un odontograma."}
                )
        vistos = set()
        for hallazgo in datos.get("hallazgos", []):
            clave = (hallazgo["diente"], hallazgo.get("cara", ""))
            if clave in vistos:
                raise serializers.ValidationError(
                    {"hallazgos": "Hay un hallazgo repetido para la misma pieza y cara."}
                )
            vistos.add(clave)
        return datos

    @transaction.atomic
    def create(self, validated_data):
        hallazgos = validated_data.pop("hallazgos", [])
        odontograma = Odontograma.objects.create(**validated_data)
        self._guardar_hallazgos(odontograma, hallazgos)
        return odontograma

    @transaction.atomic
    def update(self, instance, validated_data):
        hallazgos = validated_data.pop("hallazgos", None)
        odontograma = super().update(instance, validated_data)
        if hallazgos is not None:
            odontograma.hallazgos.all().delete()
            self._guardar_hallazgos(odontograma, hallazgos)
        return odontograma

    @staticmethod
    def _guardar_hallazgos(odontograma, hallazgos):
        for hallazgo in hallazgos:
            HallazgoDental.objects.create(odontograma=odontograma, **hallazgo)


class HistoriaClinicaSerializer(_ValidacionClinicaMixin, serializers.ModelSerializer):
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    doctor_nombre = serializers.SerializerMethodField()
    odontograma = OdontogramaSerializer(read_only=True)

    class Meta:
        model = HistoriaClinica
        fields = [
            "id",
            "paciente",
            "paciente_nombre",
            "atencion",
            "sede",
            "sede_nombre",
            "doctor",
            "doctor_nombre",
            "fecha",
            "motivo_consulta",
            "enfermedad_actual",
            "examen_clinico",
            "diagnostico",
            "plan_tratamiento",
            "notas",
            "odontograma",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id", "creado", "actualizado"]

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}"

    def get_doctor_nombre(self, obj) -> str:
        return f"{obj.doctor.nombres} {obj.doctor.apellidos}"

    def validate(self, datos):
        paciente = datos.get("paciente") or getattr(self.instance, "paciente", None)
        sede = datos.get("sede") or getattr(self.instance, "sede", None)
        atencion = datos.get("atencion") or getattr(self.instance, "atencion", None)
        if atencion is not None:
            if paciente and atencion.paciente_id != paciente.pk:
                raise serializers.ValidationError(
                    {"atencion": "La cita pertenece a otro paciente."}
                )
            if sede and atencion.sede_id != sede.pk:
                raise serializers.ValidationError({"atencion": "La cita es de otra sede."})
        return datos

from datetime import date

from rest_framework import serializers

from config.validadores import MENSAJE_TELEFONO, normalizar_telefono_hn
from users.permisos import puede_usar_sede

from .models import Paciente


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

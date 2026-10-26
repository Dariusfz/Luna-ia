from rest_framework import serializers

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO

from .models import Especialidad, TipoTrabajo


class EspecialidadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Especialidad
        fields = ["id", "nombre", "activo"]
        read_only_fields = ["id"]

    def validate_nombre(self, value):
        return value.strip()


class TipoTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoTrabajo
        fields = ["id", "nombre", "descripcion", "precio", "activo"]
        read_only_fields = ["id"]

    def validate_nombre(self, value):
        return value.strip()

    def validate_precio(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio no puede ser negativo.")
        if value > MONTO_MAXIMO:
            raise serializers.ValidationError(MENSAJE_MONTO_MAXIMO)
        return value

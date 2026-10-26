from rest_framework import serializers

from config.validadores import MENSAJE_TELEFONO, normalizar_telefono_hn

from .models import LugarExterno, Organizacion, Sede


class SedeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sede
        fields = ["id", "nombre", "direccion", "telefono", "activa"]

    def validate_nombre(self, valor):
        return valor.strip()

    def validate_telefono(self, valor):
        try:
            return normalizar_telefono_hn(valor)
        except ValueError:
            raise serializers.ValidationError(MENSAJE_TELEFONO)

    def create(self, datos):
        # Hoy existe una sola organización; se crea la primera vez.
        datos["organizacion"], _ = Organizacion.objects.get_or_create(nombre="Clínica")
        return super().create(datos)


class LugarExternoSerializer(serializers.ModelSerializer):
    class Meta:
        model = LugarExterno
        fields = ["id", "nombre", "direccion", "contacto", "activo"]
        read_only_fields = fields

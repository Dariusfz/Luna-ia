from rest_framework import serializers

from config.validadores import MENSAJE_TELEFONO, normalizar_telefono_hn

from .models import Feriado, HorarioSede, LugarExterno, Organizacion, Sede


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


class HorarioSedeSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    dia_nombre = serializers.CharField(source="get_dia_semana_display", read_only=True)

    class Meta:
        model = HorarioSede
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "dia_semana",
            "dia_nombre",
            "hora_apertura",
            "hora_cierre",
        ]

    def validate(self, datos):
        sede = datos.get("sede", getattr(self.instance, "sede", None))
        dia = datos.get("dia_semana", getattr(self.instance, "dia_semana", None))
        apertura = datos.get("hora_apertura", getattr(self.instance, "hora_apertura", None))
        cierre = datos.get("hora_cierre", getattr(self.instance, "hora_cierre", None))
        if apertura and cierre and cierre <= apertura:
            raise serializers.ValidationError(
                {"hora_cierre": "La hora de cierre debe ser posterior a la de apertura."}
            )
        if sede and dia is not None and apertura and cierre:
            choque = HorarioSede.objects.filter(
                sede=sede,
                dia_semana=dia,
                hora_apertura__lt=cierre,
                hora_cierre__gt=apertura,
            )
            if self.instance:
                choque = choque.exclude(pk=self.instance.pk)
            if choque.exists():
                raise serializers.ValidationError(
                    {"hora_apertura": "Se solapa con otro turno de la sede ese día."}
                )
        return datos


class FeriadoSerializer(serializers.ModelSerializer):
    sede_nombre = serializers.SerializerMethodField()

    class Meta:
        model = Feriado
        fields = [
            "id",
            "sede",
            "sede_nombre",
            "fecha",
            "nombre",
            "todo_el_dia",
            "hora_inicio",
            "hora_fin",
        ]

    def get_sede_nombre(self, obj):
        return obj.sede.nombre if obj.sede else "Todas las sedes"

    def validate_nombre(self, valor):
        return valor.strip()

    def validate(self, datos):
        todo_el_dia = datos.get("todo_el_dia", getattr(self.instance, "todo_el_dia", True))
        inicio = datos.get("hora_inicio", getattr(self.instance, "hora_inicio", None))
        fin = datos.get("hora_fin", getattr(self.instance, "hora_fin", None))
        if todo_el_dia:
            datos["hora_inicio"] = None
            datos["hora_fin"] = None
            return datos
        if not inicio or not fin:
            raise serializers.ValidationError(
                {"hora_inicio": "Indica la hora de inicio y de fin del medio día."}
            )
        if fin <= inicio:
            raise serializers.ValidationError(
                {"hora_fin": "La hora de fin debe ser posterior a la de inicio."}
            )
        return datos

from pathlib import Path

from rest_framework import serializers

from pacientes.querysets import pacientes_visibles
from users.permisos import puede_usar_sede

from .models import EXTENSIONES_PERMITIDAS, Documento, validar_tamano


class DocumentoSerializer(serializers.ModelSerializer):
    paciente_nombre = serializers.SerializerMethodField()
    sede_nombre = serializers.CharField(source="sede.nombre", read_only=True)
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    subido_por_nombre = serializers.SerializerMethodField()
    archivo_url = serializers.SerializerMethodField()
    nombre_archivo = serializers.SerializerMethodField()
    tamano_bytes = serializers.SerializerMethodField()
    es_imagen = serializers.BooleanField(read_only=True)
    atencion_resumen = serializers.SerializerMethodField()
    historia_resumen = serializers.SerializerMethodField()

    class Meta:
        model = Documento
        fields = [
            "id",
            "paciente",
            "paciente_nombre",
            "sede",
            "sede_nombre",
            "tipo",
            "tipo_nombre",
            "titulo",
            "descripcion",
            "atencion",
            "atencion_resumen",
            "historia",
            "historia_resumen",
            "archivo",
            "archivo_url",
            "nombre_archivo",
            "tamano_bytes",
            "es_imagen",
            "subido_por_nombre",
            "creado",
        ]
        extra_kwargs = {"archivo": {"write_only": True, "required": True}}

    def get_paciente_nombre(self, obj) -> str:
        return f"{obj.paciente.nombres} {obj.paciente.apellidos}".strip()

    def get_subido_por_nombre(self, obj) -> str:
        if obj.subido_por is None:
            return ""
        nombre = f"{obj.subido_por.first_name} {obj.subido_por.last_name}".strip()
        return nombre or obj.subido_por.username

    def get_archivo_url(self, obj) -> str:
        return f"/api/documentos/{obj.pk}/archivo/"

    def get_nombre_archivo(self, obj) -> str:
        return f"{obj.titulo}{obj.extension}"

    def get_tamano_bytes(self, obj) -> int | None:
        try:
            return obj.archivo.size
        except (OSError, ValueError):
            return None

    def get_atencion_resumen(self, obj) -> str | None:
        if not obj.atencion_id:
            return None
        atencion = obj.atencion
        return (
            f"{atencion.fecha.strftime('%d/%m/%Y')} "
            f"{atencion.hora_inicio.strftime('%H:%M')} · {atencion.tipo_trabajo.nombre}"
        )

    def get_historia_resumen(self, obj) -> str | None:
        if not obj.historia_id:
            return None
        historia = obj.historia
        motivo = (historia.motivo_consulta or "").strip()
        texto = historia.fecha.strftime("%d/%m/%Y")
        return f"{texto} · {motivo[:60]}" if motivo else texto

    def validate(self, datos):
        paciente = datos.get("paciente")
        sede = datos.get("sede")
        atencion = datos.get("atencion")
        historia = datos.get("historia")

        if atencion is not None:
            if paciente is not None and atencion.paciente_id != paciente.pk:
                raise serializers.ValidationError(
                    {"atencion": "La atención pertenece a otro paciente."}
                )
            if sede is not None and atencion.sede_id != sede.pk:
                raise serializers.ValidationError(
                    {"atencion": "La atención es de otra sede."}
                )

        if historia is not None:
            if paciente is not None and historia.paciente_id != paciente.pk:
                raise serializers.ValidationError(
                    {"historia": "La historia clínica pertenece a otro paciente."}
                )
            if sede is not None and historia.sede_id != sede.pk:
                raise serializers.ValidationError(
                    {"historia": "La historia clínica es de otra sede."}
                )
            if (
                atencion is not None
                and historia.atencion_id
                and historia.atencion_id != atencion.pk
            ):
                raise serializers.ValidationError(
                    {"historia": "La historia clínica corresponde a otra atención."}
                )
        return datos

    def validate_paciente(self, paciente):
        request = self.context["request"]
        if not pacientes_visibles(request.user).filter(pk=paciente.pk).exists():
            raise serializers.ValidationError("No tienes acceso a ese paciente.")
        return paciente

    def validate_sede(self, sede):
        if not puede_usar_sede(self.context["request"].user, sede):
            raise serializers.ValidationError("No tienes acceso a esa sede.")
        return sede

    def validate_archivo(self, archivo):
        extension = Path(archivo.name).suffix.lower().lstrip(".")
        if extension not in EXTENSIONES_PERMITIDAS:
            raise serializers.ValidationError("Sube un PDF o una imagen JPG, PNG o WEBP.")
        validar_tamano(archivo)
        return archivo

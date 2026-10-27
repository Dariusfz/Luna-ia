from django.contrib.auth import get_user_model
from rest_framework import serializers

from config.validadores import MENSAJE_TELEFONO, normalizar_telefono_hn
from sedes.models import Sede

from servicios.models import Especialidad

from .mfa import tiene_2fa_confirmado
from .models import Doctor, Invitacion, Usuario
from .permisos import es_admin


class SedeResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sede
        fields = ["id", "nombre"]


class UsuarioSerializer(serializers.ModelSerializer):
    """Datos del usuario en sesión. Incluye sus sedes y si es administrador."""

    nombres = serializers.CharField(source="first_name")
    apellidos = serializers.CharField(source="last_name")
    sedes = SedeResumenSerializer(many=True, read_only=True)
    es_admin = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ["id", "username", "email", "nombres", "apellidos", "rol", "sedes", "es_admin"]
        read_only_fields = fields

    def get_es_admin(self, obj) -> bool:
        return es_admin(obj)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class InvitacionCrearSerializer(serializers.Serializer):
    email = serializers.EmailField()
    rol = serializers.ChoiceField(choices=Usuario.Rol.choices)
    sedes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Sede.objects.filter(activa=True), required=False
    )

    def validate_email(self, value):
        email = value.lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Ya existe un usuario con este correo.")
        return email

    def validate(self, data):
        # El admin ve todas las sedes; el resto necesita al menos una sede asignada.
        if data["rol"] != Usuario.Rol.ADMIN and not data.get("sedes"):
            raise serializers.ValidationError(
                {"sedes": "Debe asignar al menos una sede a este rol."}
            )
        return data


class InvitacionSerializer(serializers.ModelSerializer):
    sedes = SedeResumenSerializer(many=True, read_only=True)
    vigente = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invitacion
        fields = ["id", "email", "rol", "sedes", "creada", "expira", "aceptada_en", "vigente"]
        read_only_fields = fields


class DoctorSerializer(serializers.ModelSerializer):
    sedes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Sede.objects.filter(activa=True), required=False
    )
    usuario = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.all(), required=False, allow_null=True
    )
    especialidades = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Especialidad.objects.filter(activo=True), required=False
    )
    especialidades_nombres = serializers.SerializerMethodField()

    class Meta:
        model = Doctor
        fields = [
            "id",
            "usuario",
            "tipo",
            "nombres",
            "apellidos",
            "especialidades",
            "especialidades_nombres",
            "numero_colegiado",
            "telefono",
            "activo",
            "sedes",
            "observaciones",
            "creado",
        ]
        read_only_fields = ["id", "creado"]

    # Campos administrativos: solo los ve el admin.
    CAMPOS_SOLO_ADMIN = ("usuario", "observaciones")

    def get_especialidades_nombres(self, obj) -> list[str]:
        return [especialidad.nombre for especialidad in obj.especialidades.all()]

    def validate_telefono(self, valor):
        try:
            return normalizar_telefono_hn(valor)
        except ValueError:
            raise serializers.ValidationError(MENSAJE_TELEFONO)

    def to_representation(self, instance):
        datos = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not es_admin(request.user):
            for campo in self.CAMPOS_SOLO_ADMIN:
                datos.pop(campo, None)
        return datos

    def validate(self, data):
        tipo = data.get("tipo", getattr(self.instance, "tipo", None))
        usuario = data.get("usuario", getattr(self.instance, "usuario", None))
        if tipo == Doctor.Tipo.CONTRATADO and usuario is not None:
            raise serializers.ValidationError(
                {"usuario": "Los doctores contratados por sesión no tienen cuenta de acceso."}
            )
        return data


class SolicitarRecuperacionSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ConfirmarRecuperacionSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class UsuarioAdminSerializer(serializers.ModelSerializer):
    """Vista del administrador sobre el personal: incluye si tiene 2FA configurado."""

    tiene_2fa = serializers.SerializerMethodField()
    sedes = SedeResumenSerializer(many=True, read_only=True)

    class Meta:
        model = Usuario
        fields = [
            "id", "username", "email", "nombres", "apellidos", "rol",
            "is_active", "tiene_2fa", "sedes",
        ]
        read_only_fields = fields

    nombres = serializers.CharField(source="first_name", read_only=True)
    apellidos = serializers.CharField(source="last_name", read_only=True)

    def get_tiene_2fa(self, obj) -> bool:
        return tiene_2fa_confirmado(obj)


class UsuarioEditarSerializer(serializers.Serializer):
    """Cambios del administrador sobre una cuenta: rol, sedes y estado activo/inactivo."""

    rol = serializers.ChoiceField(choices=Usuario.Rol.choices, required=False)
    sedes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Sede.objects.all(), required=False
    )
    is_active = serializers.BooleanField(required=False)

    def validate(self, data):
        usuario = self.instance
        request = self.context["request"]
        if usuario.pk == request.user.pk and data.get("is_active") is False:
            raise serializers.ValidationError("No puedes desactivar tu propia cuenta.")
        if usuario.pk == request.user.pk and data.get("rol") not in (None, Usuario.Rol.ADMIN):
            raise serializers.ValidationError("No puedes quitarte el rol de administrador.")

        rol = data.get("rol", usuario.rol)
        sedes = data.get("sedes")
        if rol != Usuario.Rol.ADMIN:
            sedes_finales = sedes if sedes is not None else list(usuario.sedes.all())
            if not sedes_finales:
                raise serializers.ValidationError(
                    {"sedes": "Asigna al menos una sede a este rol."}
                )
        return data

    def update(self, instance, datos):
        sedes = datos.pop("sedes", None)
        for campo, valor in datos.items():
            setattr(instance, campo, valor)
        instance.save()
        if sedes is not None:
            instance.sedes.set(sedes)
        return instance


class AceptarInvitacionSerializer(serializers.Serializer):
    token = serializers.CharField()
    username = serializers.CharField(max_length=150)
    nombres = serializers.CharField(max_length=150)
    apellidos = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

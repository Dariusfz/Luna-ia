import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions as django_exceptions
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import Invitacion, Usuario

logger = logging.getLogger(__name__)


def crear_invitacion(*, email, rol, sedes, creada_por):
    """Crea la invitación y envía el enlace por correo. Devuelve la invitación (sin token)."""
    token = secrets.token_urlsafe(32)
    horas = settings.INVITACION_HORAS_VALIDEZ

    with transaction.atomic():
        invitacion = Invitacion.objects.create(
            email=email,
            rol=rol,
            token_hash=Invitacion.hash_token(token),
            creada_por=creada_por,
            expira=timezone.now() + timedelta(hours=horas),
        )
        invitacion.sedes.set(sedes)

    enlace = f"{settings.FRONTEND_URL}/aceptar-invitacion?token={token}"
    try:
        send_mail(
            subject="Invitación a LUNA-IA",
            message=(
                "Has sido invitado al sistema de la clínica.\n\n"
                f"Para crear tu cuenta abre este enlace (válido {horas} horas):\n{enlace}\n\n"
                "Si no esperabas este correo, ignóralo."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    except Exception as error:
        # Si el correo no sale, la invitación no sirve: se borra para no dejar basura
        # ni hacer creer al administrador que el enlace llegó.
        logger.exception("No se pudo enviar la invitación a %s", email)
        invitacion.delete()
        raise serializers.ValidationError(
            "No se pudo enviar el correo de invitación. Revisa la configuración SMTP "
            "(EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER y EMAIL_HOST_PASSWORD) y vuelve a intentarlo."
        ) from error
    return invitacion


def aceptar_invitacion(*, token, username, password, nombres, apellidos):
    """
    Crea el usuario a partir de una invitación vigente. Recibir el enlace en el correo
    es la verificación de que el email es del receptor.
    """
    invitacion = Invitacion.objects.filter(token_hash=Invitacion.hash_token(token)).first()
    if invitacion is None or not invitacion.vigente:
        raise serializers.ValidationError("La invitación no es válida o ya expiró.")

    if Usuario.objects.filter(username=username).exists():
        raise serializers.ValidationError({"username": "Ese nombre de usuario ya existe."})
    if Usuario.objects.filter(email__iexact=invitacion.email).exists():
        raise serializers.ValidationError("Ya existe una cuenta con este correo.")

    usuario = Usuario(
        username=username,
        email=invitacion.email,
        first_name=nombres,
        last_name=apellidos,
        rol=invitacion.rol,
    )
    try:
        validate_password(password, user=usuario)
    except django_exceptions.ValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})

    with transaction.atomic():
        usuario.set_password(password)
        usuario.save()
        usuario.sedes.set(invitacion.sedes.all())
        invitacion.aceptada_en = timezone.now()
        invitacion.save(update_fields=["aceptada_en"])

    return usuario

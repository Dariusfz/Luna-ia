import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core import exceptions as django_exceptions
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import CodigoRecuperacion, DispositivoTOTP, RecuperacionContrasena, Usuario

MENSAJE_SOLICITUD = (
    "Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña."
)


def cerrar_sesiones(usuario: Usuario) -> None:
    """Cierra todas las sesiones abiertas de un usuario."""
    ahora = timezone.now()
    for sesion in Session.objects.filter(expire_date__gt=ahora):
        if str(sesion.get_decoded().get("_auth_user_id")) == str(usuario.pk):
            sesion.delete()


def solicitar_recuperacion(email: str) -> None:
    """
    Envía el enlace si el correo pertenece a una cuenta activa. No revela si existe:
    el llamador responde siempre lo mismo.
    """
    usuario = Usuario.objects.filter(email__iexact=email.strip(), is_active=True).first()
    if usuario is None:
        return

    token = secrets.token_urlsafe(32)
    RecuperacionContrasena.objects.create(
        usuario=usuario,
        token_hash=RecuperacionContrasena.hash_token(token),
        expira=timezone.now() + timedelta(minutes=settings.RECUPERACION_MINUTOS),
    )
    enlace = f"{settings.FRONTEND_URL}/recuperar/confirmar?token={token}"
    send_mail(
        subject="Recuperar contraseña de LUNA-IA",
        message=(
            f"Recibimos una solicitud para restablecer tu contraseña.\n\n"
            f"Abre este enlace en los próximos {settings.RECUPERACION_MINUTOS} minutos:\n{enlace}\n\n"
            "Si no fuiste tú, ignora este correo; tu contraseña no cambiará."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[usuario.email],
    )


def confirmar_recuperacion(*, token: str, password: str) -> None:
    registro = (
        RecuperacionContrasena.objects.select_related("usuario")
        .filter(token_hash=RecuperacionContrasena.hash_token(token))
        .first()
    )
    if registro is None or not registro.vigente:
        raise serializers.ValidationError("El enlace no es válido o ya expiró.")

    usuario = registro.usuario
    try:
        validate_password(password, user=usuario)
    except django_exceptions.ValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})

    with transaction.atomic():
        usuario.set_password(password)
        usuario.save(update_fields=["password"])
        RecuperacionContrasena.objects.filter(
            usuario=usuario, usado_en__isnull=True
        ).update(usado_en=timezone.now())
        cerrar_sesiones(usuario)


def restablecer_2fa(usuario: Usuario) -> None:
    """
    Quita el 2FA de un usuario (p. ej. perdió el teléfono y sus códigos).
    Cierra sus sesiones: al volver a entrar deberá configurar un autenticador nuevo.
    """
    with transaction.atomic():
        DispositivoTOTP.objects.filter(usuario=usuario).delete()
        CodigoRecuperacion.objects.filter(usuario=usuario).delete()
        cerrar_sesiones(usuario)

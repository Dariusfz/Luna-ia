"""Envía un correo de prueba para comprobar la configuración SMTP."""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envía un correo de prueba al destino indicado para verificar el servidor SMTP."

    def add_arguments(self, parser):
        parser.add_argument("destino", help="Correo que recibirá la prueba, por ejemplo tu@gmail.com")

    def handle(self, *args, **opciones):
        destino = opciones["destino"]
        if not settings.EMAIL_HOST_USER:
            self.stdout.write(
                self.style.WARNING(
                    "EMAIL_HOST_USER está vacío: estás usando Mailpit o un SMTP sin autenticación."
                )
            )
        self.stdout.write(
            f"SMTP: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
            f"TLS={settings.EMAIL_USE_TLS} SSL={settings.EMAIL_USE_SSL} "
            f"remitente={settings.DEFAULT_FROM_EMAIL}"
        )
        try:
            enviados = send_mail(
                subject="Prueba de correo de LUNA-IA",
                message=(
                    "Si ves este mensaje, el envío de correos del ERP está funcionando.\n\n"
                    "Puedes borrar este correo."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destino],
                fail_silently=False,
            )
        except Exception as error:
            raise CommandError(f"No se pudo enviar el correo: {error}") from error
        if not enviados:
            raise CommandError("El backend de correo no envió el mensaje (0 enviados).")
        self.stdout.write(self.style.SUCCESS(f"Correo enviado a {destino}. Revisa la bandeja y el spam."))

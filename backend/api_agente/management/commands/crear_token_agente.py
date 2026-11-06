from django.core.management.base import BaseCommand, CommandError

from api_agente.models import TokenServicio


class Command(BaseCommand):
    help = "Crea un token de servicio para el agente. El valor se muestra una sola vez."

    def add_arguments(self, parser):
        parser.add_argument("nombre", help="Identificador del token, ej. agente-whatsapp-dev")

    def handle(self, *args, **opciones):
        nombre = opciones["nombre"].strip()
        if TokenServicio.objects.filter(nombre=nombre).exists():
            raise CommandError(f"Ya existe un token llamado '{nombre}'.")
        token = TokenServicio.crear(nombre)
        self.stdout.write(self.style.SUCCESS(f"Token creado para '{nombre}':"))
        self.stdout.write(token)
        self.stdout.write("Guárdalo en un lugar seguro: no se volverá a mostrar.")

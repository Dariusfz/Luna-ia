import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.core.validators import FileExtensionValidator
from django.db import models
from simple_history.models import HistoricalRecords

EXTENSIONES_PERMITIDAS = ["pdf", "jpg", "jpeg", "png", "webp"]


class AlmacenDocumentos(FileSystemStorage):
    """Archivos privados fuera de MEDIA_ROOT: solo se sirven por la API con permisos.

    La ubicación se lee de los settings en cada acceso (no se cachea) para que las
    pruebas puedan usar un directorio temporal.
    """

    @property
    def base_location(self):
        return Path(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        return None


almacen_documentos = AlmacenDocumentos()


def ruta_documento(instance, filename):
    """Ruta interna con UUID: no se adivina por el nombre que subió el usuario."""
    sufijo = Path(filename).suffix.lower()
    return f"documentos/{instance.paciente_id}/{uuid.uuid4().hex}{sufijo}"


def validar_tamano(archivo):
    maximo_mb = int(getattr(settings, "DOCUMENTOS_TAMANO_MAXIMO_MB", 20))
    if archivo and getattr(archivo, "size", 0) > maximo_mb * 1024 * 1024:
        raise ValidationError(f"El archivo no puede superar {maximo_mb} MB.")


class Documento(models.Model):
    """Radiografía, foto clínica, consentimiento o estudio de un paciente."""

    class Tipo(models.TextChoices):
        RADIOGRAFIA = "radiografia", "Radiografía"
        FOTO = "foto", "Foto clínica"
        CONSENTIMIENTO = "consentimiento", "Consentimiento"
        ESTUDIO = "estudio", "Estudio"
        OTRO = "otro", "Otro"

    paciente = models.ForeignKey(
        "pacientes.Paciente",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    sede = models.ForeignKey(
        "sedes.Sede",
        on_delete=models.PROTECT,
        related_name="documentos",
    )
    # Contexto clínico opcional: una cita/atención concreta o una historia clínica.
    # Así el mismo archivo no hay que duplicarlo en cada pantalla.
    atencion = models.ForeignKey(
        "agenda.Atencion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos",
    )
    historia = models.ForeignKey(
        "pacientes.HistoriaClinica",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos",
    )
    tipo = models.CharField(
        max_length=20, choices=Tipo.choices, default=Tipo.OTRO
    )
    titulo = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True)
    archivo = models.FileField(
        storage=almacen_documentos,
        upload_to=ruta_documento,
        validators=[
            FileExtensionValidator(
                EXTENSIONES_PERMITIDAS,
                message="Sube un PDF o una imagen JPG, PNG o WEBP.",
            ),
            validar_tamano,
        ],
    )
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos_subidos",
    )
    creado = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-creado"]
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        indexes = [models.Index(fields=["paciente", "-creado"])]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.titulo}"

    @property
    def es_imagen(self) -> bool:
        return Path(self.archivo.name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}

    @property
    def extension(self) -> str:
        return Path(self.archivo.name).suffix.lower()

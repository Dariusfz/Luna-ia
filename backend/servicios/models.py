from django.core.validators import MaxValueValidator
from django.db import models

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO


class Especialidad(models.Model):
    """Catálogo de especialidades de los doctores (ortodoncia, endodoncia, cirugía...)."""

    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "especialidad"
        verbose_name_plural = "especialidades"

    def __str__(self):
        return self.nombre


class TipoTrabajo(models.Model):
    """
    Catálogo de tipos de trabajo (ej. limpieza, extracción, ortodoncia).
    `precio` es el costo de referencia del tratamiento en HNL; cada atención
    registra además lo realmente cobrado.
    """

    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Costo de referencia (HNL)",
        validators=[MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO)],
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "tipo de trabajo"
        verbose_name_plural = "tipos de trabajo"

    def __str__(self):
        return self.nombre

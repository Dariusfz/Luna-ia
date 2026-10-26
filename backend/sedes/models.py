from django.db import models


class Organizacion(models.Model):
    """Capa superior (multi-tenant futuro). Hoy existe una sola."""

    nombre = models.CharField(max_length=150)
    creada = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre


class Sede(models.Model):
    """Sede propia de la clínica (3 sedes). Tiene pacientes, inventario y horarios propios."""

    organizacion = models.ForeignKey(
        Organizacion, on_delete=models.PROTECT, related_name="sedes"
    )
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True, help_text="Formato +504 ...")
    activa = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class LugarExterno(models.Model):
    """Lugar donde la doctora admin trabaja fuera de la clínica. No es una sede propia."""

    nombre = models.CharField(max_length=150, unique=True)
    direccion = models.CharField(max_length=255, blank=True)
    contacto = models.CharField(max_length=150, blank=True)
    activo = models.BooleanField(default=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "lugar externo"
        verbose_name_plural = "lugares externos"

    def __str__(self):
        return self.nombre

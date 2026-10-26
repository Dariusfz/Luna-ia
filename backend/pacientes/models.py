from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords


class Paciente(models.Model):
    """Paciente global de la clínica. Su historial solo lo ven las sedes donde se le atiende."""

    class Sexo(models.TextChoices):
        FEMENINO = "F", "Femenino"
        MASCULINO = "M", "Masculino"
        OTRO = "O", "Otro"

    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    identidad = models.CharField(max_length=13, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, choices=Sexo.choices, blank=True)
    telefono = models.CharField(max_length=20, blank=True, help_text="Formato +504 ...")
    email = models.EmailField(blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    sede_origen = models.ForeignKey(
        "sedes.Sede",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pacientes_origen",
    )
    alergias = models.TextField(blank=True)
    antecedentes_medicos = models.TextField(blank=True)
    medicamentos_actuales = models.TextField(blank=True)
    observaciones = models.TextField(blank=True)
    # Los pacientes no se borran (dato clínico): se desactivan.
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["apellidos", "nombres"]
        constraints = [
            models.UniqueConstraint(
                fields=["identidad"],
                condition=~Q(identidad=""),
                name="uniq_paciente_identidad_no_vacia",
            )
        ]

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"

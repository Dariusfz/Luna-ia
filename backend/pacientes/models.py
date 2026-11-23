from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
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
    # Obligatoria. Si el paciente no la da (p. ej. por WhatsApp), se usa la de la sede donde se atiende.
    direccion = models.CharField(max_length=255)
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
            ),
            # La dirección es obligatoria también a nivel de BD (no solo en formularios).
            models.CheckConstraint(
                condition=~Q(direccion=""),
                name="paciente_direccion_no_vacia",
            ),
        ]

    def __str__(self):
        return f"{self.nombres} {self.apellidos}"


def validar_diente_fdi(valor: int) -> None:
    """Acepta la numeración FDI: 11-48 (permanentes) y 51-85 (temporales)."""
    cuadrante, pieza = divmod(int(valor), 10)
    permanente = 1 <= cuadrante <= 4 and 1 <= pieza <= 8
    temporal = 5 <= cuadrante <= 8 and 1 <= pieza <= 5
    if not (permanente or temporal):
        raise ValidationError("Usa la numeración FDI: 11-48 o 51-85.")


class HistoriaClinica(models.Model):
    """Entrada de la historia clínica de un paciente (normalmente una por consulta)."""

    paciente = models.ForeignKey(
        Paciente, on_delete=models.PROTECT, related_name="historias"
    )
    atencion = models.OneToOneField(
        "agenda.Atencion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="historia",
        help_text="Cita que originó la consulta, si existe.",
    )
    sede = models.ForeignKey("sedes.Sede", on_delete=models.PROTECT, related_name="historias")
    doctor = models.ForeignKey(
        "users.Doctor", on_delete=models.PROTECT, related_name="historias"
    )
    fecha = models.DateField(default=timezone.localdate)
    motivo_consulta = models.TextField(blank=True)
    enfermedad_actual = models.TextField(blank=True)
    examen_clinico = models.TextField(blank=True)
    diagnostico = models.TextField(blank=True)
    plan_tratamiento = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "historia clínica"
        verbose_name_plural = "historias clínicas"
        indexes = [
            models.Index(fields=["paciente", "fecha"]),
            models.Index(fields=["sede", "fecha"]),
        ]

    def __str__(self):
        return f"{self.paciente} - {self.fecha}"


class Odontograma(models.Model):
    """Estado dental del paciente en una fecha (puede colgar de una historia clínica)."""

    paciente = models.ForeignKey(
        Paciente, on_delete=models.PROTECT, related_name="odontogramas"
    )
    historia = models.OneToOneField(
        HistoriaClinica,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="odontograma",
    )
    sede = models.ForeignKey("sedes.Sede", on_delete=models.PROTECT, related_name="odontogramas")
    doctor = models.ForeignKey(
        "users.Doctor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="odontogramas",
    )
    fecha = models.DateField(default=timezone.localdate)
    notas = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-pk"]
        indexes = [models.Index(fields=["paciente", "fecha"])]

    def __str__(self):
        return f"Odontograma de {self.paciente} ({self.fecha})"


class HallazgoDental(models.Model):
    """Hallazgo de una pieza dental (y opcionalmente de una cara) dentro de un odontograma."""

    class Cara(models.TextChoices):
        OCLUSAL = "oclusal", "Oclusal"
        MESIAL = "mesial", "Mesial"
        DISTAL = "distal", "Distal"
        VESTIBULAR = "vestibular", "Vestibular"
        LINGUAL = "lingual", "Lingual/Palatino"

    class Estado(models.TextChoices):
        SANO = "sano", "Sano"
        CARIES = "caries", "Caries"
        OBTURADO = "obturado", "Obturado"
        CORONA = "corona", "Corona"
        ENDODONCIA = "endodoncia", "Endodoncia"
        AUSENTE = "ausente", "Ausente"
        EXTRACCION_INDICADA = "extraccion_indicada", "Extracción indicada"
        IMPLANTE = "implante", "Implante"
        SELLANTE = "sellante", "Sellante"
        FRACTURA = "fractura", "Fractura"
        PROTESIS = "protesis", "Prótesis"

    odontograma = models.ForeignKey(
        Odontograma, on_delete=models.CASCADE, related_name="hallazgos"
    )
    diente = models.PositiveSmallIntegerField(
        validators=[validar_diente_fdi],
        help_text="Numeración FDI (11-48 o 51-85).",
    )
    cara = models.CharField(
        max_length=12,
        choices=Cara.choices,
        blank=True,
        help_text="Vacío si el hallazgo afecta toda la pieza.",
    )
    estado = models.CharField(max_length=20, choices=Estado.choices)
    observacion = models.CharField(max_length=200, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["diente", "cara"]
        verbose_name = "hallazgo dental"
        verbose_name_plural = "hallazgos dentales"
        constraints = [
            models.UniqueConstraint(
                fields=["odontograma", "diente", "cara"],
                name="hallazgo_unico_por_pieza_cara",
            )
        ]

    def __str__(self):
        cara = f" ({self.cara})" if self.cara else ""
        return f"{self.diente}{cara}: {self.get_estado_display()}"

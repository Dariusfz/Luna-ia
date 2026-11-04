from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO

MONTO_MINIMO = Decimal("0.01")
MENSAJE_MONTO_POSITIVO = "El monto debe ser mayor que cero."


class MetodoPago(models.TextChoices):
    EFECTIVO = "efectivo", "Efectivo"
    TRANSFERENCIA = "transferencia", "Transferencia"
    TARJETA = "tarjeta", "Tarjeta"
    OTRO = "otro", "Otro"


class Pago(models.Model):
    """Abono de un paciente a una cita. Una cita puede tener varios abonos."""

    atencion = models.ForeignKey(
        "agenda.Atencion",
        on_delete=models.PROTECT,
        related_name="pagos",
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(MONTO_MINIMO, message=MENSAJE_MONTO_POSITIVO),
            MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO),
        ],
        help_text="Monto del abono (HNL)",
    )
    metodo = models.CharField(
        max_length=20, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO
    )
    fecha = models.DateField(default=timezone.localdate, help_text="Fecha del cobro")
    nota = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        "users.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pagos_registrados",
    )
    creado = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-creado"]
        indexes = [
            models.Index(fields=["fecha"]),
            models.Index(fields=["atencion", "fecha"]),
        ]
        verbose_name = "pago"
        verbose_name_plural = "pagos"

    def __str__(self):
        return f"Abono L {self.monto} a {self.atencion}"


class PagoDoctor(models.Model):
    """Pago real a un doctor por una cita. Puede registrarse en varios abonos."""

    atencion = models.ForeignKey(
        "agenda.Atencion",
        on_delete=models.PROTECT,
        related_name="pagos_doctor",
    )
    doctor = models.ForeignKey(
        "users.Doctor",
        on_delete=models.PROTECT,
        related_name="pagos_recibidos",
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(MONTO_MINIMO, message=MENSAJE_MONTO_POSITIVO),
            MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO),
        ],
        help_text="Monto pagado al doctor (HNL)",
    )
    metodo = models.CharField(
        max_length=20, choices=MetodoPago.choices, default=MetodoPago.EFECTIVO
    )
    fecha = models.DateField(default=timezone.localdate, help_text="Fecha del pago")
    nota = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(
        "users.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pagos_doctor_registrados",
    )
    creado = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-creado"]
        indexes = [
            models.Index(fields=["fecha"]),
            models.Index(fields=["atencion", "fecha"]),
            models.Index(fields=["doctor", "fecha"]),
        ]
        verbose_name = "pago a doctor"
        verbose_name_plural = "pagos a doctores"

    def save(self, *args, **kwargs):
        if self.atencion_id:
            self.doctor_id = self.atencion.doctor_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Pago L {self.monto} a {self.doctor} por {self.atencion}"

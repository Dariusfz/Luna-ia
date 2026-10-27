from django.db import models
from django.db.models import F, Q


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


class HorarioSede(models.Model):
    """
    Turno de atención de una sede. Varias filas por día permiten pausas
    (por ejemplo, el almuerzo de 12:00 a 13:00).
    """

    class Dia(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, related_name="horarios")
    dia_semana = models.PositiveSmallIntegerField(choices=Dia.choices)
    hora_apertura = models.TimeField()
    hora_cierre = models.TimeField()

    class Meta:
        ordering = ["sede", "dia_semana", "hora_apertura"]
        verbose_name = "horario de sede"
        verbose_name_plural = "horarios de sede"
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_cierre__gt=F("hora_apertura")),
                name="horario_cierre_posterior",
            ),
            models.UniqueConstraint(
                fields=["sede", "dia_semana", "hora_apertura", "hora_cierre"],
                name="horario_turno_unico",
            ),
        ]

    def __str__(self):
        return f"{self.sede} - {self.get_dia_semana_display()} {self.hora_apertura}-{self.hora_cierre}"


class Feriado(models.Model):
    """
    Día o medio día cerrado. Si `sede` está vacía, aplica a todas las sedes.
    Con `todo_el_dia=False` se cierra solo el rango hora_inicio-hora_fin.
    """

    sede = models.ForeignKey(
        Sede,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="feriados",
        help_text="Vacío = aplica a todas las sedes.",
    )
    fecha = models.DateField()
    nombre = models.CharField(max_length=150)
    todo_el_dia = models.BooleanField(default=True)
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "sede__nombre"]
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(todo_el_dia=True)
                    | (
                        Q(hora_inicio__isnull=False)
                        & Q(hora_fin__isnull=False)
                        & Q(hora_fin__gt=F("hora_inicio"))
                    )
                ),
                name="feriado_horas_validas",
            )
        ]

    def __str__(self):
        return f"{self.fecha} - {self.nombre}"

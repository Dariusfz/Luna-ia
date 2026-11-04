from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from simple_history.models import HistoricalRecords

from config.validadores import MENSAJE_MONTO_MAXIMO, MONTO_MAXIMO


class Atencion(models.Model):
    """
    Cita o visita de un doctor a un paciente en una sede propia de la clínica.
    Mientras está pendiente o confirmada es una cita agendada; al completarse
    registra la atención realizada y lo que la clínica paga al doctor.
    """

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        CONFIRMADA = "confirmada", "Confirmada"
        COMPLETADA = "completada", "Completada"
        CANCELADA = "cancelada", "Cancelada"

    class Origen(models.TextChoices):
        PANEL = "panel", "Panel"
        AGENTE_WHATSAPP = "agente_whatsapp", "Agente WhatsApp"
        ASISTENTE_IA = "asistente_ia", "Asistente IA"
        SISTEMA = "sistema", "Sistema"

    sede = models.ForeignKey("sedes.Sede", on_delete=models.PROTECT, related_name="atenciones")
    doctor = models.ForeignKey("users.Doctor", on_delete=models.PROTECT, related_name="atenciones")
    paciente = models.ForeignKey(
        "pacientes.Paciente", on_delete=models.PROTECT, related_name="atenciones"
    )
    tipo_trabajo = models.ForeignKey(
        "servicios.TipoTrabajo",
        on_delete=models.PROTECT,
        related_name="atenciones",
        help_text="Tipo principal; se sincroniza con el primero de los trabajos.",
    )
    tipos_trabajo = models.ManyToManyField(
        "servicios.TipoTrabajo",
        through="AtencionTrabajo",
        related_name="atenciones_con_trabajo",
        blank=True,
        help_text="Tipos de trabajo incluidos en la cita.",
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        help_text="Pendiente/confirmada: cita agendada. Completada: visita realizada.",
    )
    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
        default=Origen.PANEL,
        db_index=True,
        help_text="Canal por el que se creó la cita.",
    )
    creado_por = models.ForeignKey(
        "users.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="atenciones_creadas",
        help_text="Usuario del panel que creó la cita; vacío si la creó el agente.",
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    procedimiento = models.CharField(
        max_length=200, blank=True, help_text="Detalle adicional del trabajo realizado"
    )
    precio_paciente = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Total calculado con los precios de los tipos de trabajo (HNL)",
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO),
        ],
    )
    honorario_doctor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Monto pagado al doctor (HNL)",
        validators=[MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO)],
    )
    observaciones = models.TextField(blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-hora_inicio"]
        indexes = [
            models.Index(fields=["sede", "fecha"]),
            models.Index(fields=["estado", "fecha"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_fin__gt=F("hora_inicio")),
                name="atencion_hora_fin_posterior",
            )
        ]

    def __str__(self):
        return f"{self.fecha} {self.hora_inicio} - {self.paciente} ({self.sede})"


class AtencionTrabajo(models.Model):
    """Tipo de trabajo incluido en una cita, con el precio vigente al crearla."""

    atencion = models.ForeignKey(
        Atencion,
        on_delete=models.CASCADE,
        related_name="trabajos",
    )
    tipo_trabajo = models.ForeignKey(
        "servicios.TipoTrabajo",
        on_delete=models.PROTECT,
        related_name="atenciones_trabajo",
    )
    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Precio del tipo de trabajo al momento de la cita (HNL)",
        validators=[
            MinValueValidator(Decimal("0")),
            MaxValueValidator(MONTO_MAXIMO, message=MENSAJE_MONTO_MAXIMO),
        ],
    )
    orden = models.PositiveSmallIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["atencion", "tipo_trabajo"],
                name="atencion_trabajo_unico",
            )
        ]
        verbose_name = "trabajo de atención"
        verbose_name_plural = "trabajos de atención"

    def __str__(self):
        return f"{self.atencion} - {self.tipo_trabajo}"


class JornadaExterna(models.Model):
    """
    Trabajo de la doctora administradora fuera de la clínica.
    Solo registra fecha, lugar, horas y cobro. No guarda datos de pacientes.
    """

    doctor = models.ForeignKey(
        "users.Doctor",
        on_delete=models.PROTECT,
        related_name="jornadas_externas",
    )
    lugar = models.ForeignKey(
        "sedes.LugarExterno", on_delete=models.PROTECT, related_name="jornadas"
    )
    tipo_trabajo = models.ForeignKey(
        "servicios.TipoTrabajo",
        on_delete=models.PROTECT,
        related_name="jornadas_externas",
        help_text="Tipo de trabajo realizado (obligatorio).",
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    monto_cobrado = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Cobro por la atención (HNL)"
    )
    observaciones = models.TextField(blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-fecha", "-hora_inicio"]
        verbose_name = "jornada externa"
        verbose_name_plural = "jornadas externas"
        constraints = [
            models.CheckConstraint(
                condition=Q(hora_fin__gt=F("hora_inicio")),
                name="jornada_hora_fin_posterior",
            )
        ]

    def __str__(self):
        return f"{self.fecha} - {self.lugar} ({self.hora_inicio}-{self.hora_fin})"


class ListaEspera(models.Model):
    """
    Paciente que espera un cupo en una sede. Puede convertirse en cita con la
    acción `agendar`, que crea la Atencion y deja el enlace guardado.
    """

    class Prioridad(models.IntegerChoices):
        BAJA = 1, "Baja"
        NORMAL = 2, "Normal"
        ALTA = 3, "Alta"

    class Estado(models.TextChoices):
        ESPERANDO = "esperando", "En espera"
        CONTACTADO = "contactado", "Contactado"
        AGENDADO = "agendado", "Agendado"
        CANCELADO = "cancelado", "Cancelado"

    sede = models.ForeignKey(
        "sedes.Sede", on_delete=models.PROTECT, related_name="lista_espera"
    )
    paciente = models.ForeignKey(
        "pacientes.Paciente", on_delete=models.PROTECT, related_name="lista_espera"
    )
    doctor = models.ForeignKey(
        "users.Doctor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lista_espera",
        help_text="Doctor preferido por el paciente (opcional).",
    )
    tipo_trabajo = models.ForeignKey(
        "servicios.TipoTrabajo",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="lista_espera",
        help_text="Trabajo que necesita el paciente (opcional).",
    )
    prioridad = models.PositiveSmallIntegerField(
        choices=Prioridad.choices, default=Prioridad.NORMAL
    )
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.ESPERANDO
    )
    fecha_deseada = models.DateField(
        null=True, blank=True, help_text="Fecha aproximada en la que quiere atenderse."
    )
    motivo = models.CharField(max_length=255, blank=True)
    atencion = models.OneToOneField(
        Atencion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lista_espera",
        help_text="Cita creada cuando se agenda esta espera.",
    )
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-prioridad", "creada"]
        verbose_name = "lista de espera"
        verbose_name_plural = "lista de espera"
        indexes = [models.Index(fields=["sede", "estado"])]

    def __str__(self):
        return f"{self.paciente} - {self.sede} ({self.get_estado_display()})"

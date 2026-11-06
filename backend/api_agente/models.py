import hashlib
import secrets

from django.db import models
from django.utils import timezone

from sedes.models import Sede


class TokenServicio(models.Model):
    """
    Credencial del agente de WhatsApp. No es una sesión de usuario: solo existe el
    hash del token en BD; el valor en claro se muestra una única vez al crearlo.
    """

    nombre = models.CharField(max_length=100, unique=True)
    token_hash = models.CharField(max_length=64, unique=True)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    ultimo_uso = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "token de servicio"
        verbose_name_plural = "tokens de servicio"

    # Atributos que DRF y los permisos leen de request.user. El agente opera
    # sobre todas las sedes activas (plan §5.2).
    is_authenticated = True
    is_anonymous = False
    is_superuser = False
    is_staff = False
    rol = "agente"

    @property
    def sedes(self):
        return Sede.objects.filter(activa=True)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def crear(cls, nombre: str) -> str:
        """Crea el token y devuelve su valor en claro (único momento en que existe)."""
        token = secrets.token_urlsafe(48)
        cls.objects.create(nombre=nombre, token_hash=cls.hash_token(token))
        return token

    def registrar_uso(self):
        # update() evita disparar auto_now ni historial en cada llamada del agente.
        TokenServicio.objects.filter(pk=self.pk).update(ultimo_uso=timezone.now())

    def __str__(self):
        return f"Token de servicio: {self.nombre}"


class ConversacionWhatsApp(models.Model):
    """Un hilo por número de WhatsApp. El paciente se identifica por el teléfono del remitente."""

    class Estado(models.TextChoices):
        INICIO = "inicio", "Inicio"
        ESPERANDO_SEDE = "esperando_sede", "Esperando sede"
        ESPERANDO_DATOS = "esperando_datos", "Esperando datos del paciente"
        ESPERANDO_CONFIRMACION = "esperando_confirmacion", "Esperando confirmación"
        CERRADA = "cerrada", "Cerrada"

    telefono = models.CharField(max_length=20, unique=True, help_text="E.164, ej. +50499999999")
    paciente = models.ForeignKey(
        "pacientes.Paciente",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversaciones_whatsapp",
    )
    sede = models.ForeignKey(
        "sedes.Sede",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversaciones_whatsapp",
    )
    estado = models.CharField(max_length=30, choices=Estado.choices, default=Estado.INICIO)
    # False = una persona de la clínica atiende este hilo. El agente no responde hasta reactivarlo.
    agente_activo = models.BooleanField(
        default=True,
        help_text="Desmárcalo para que una persona responda este hilo sin que el agente intervenga.",
    )
    # Borrador de la acción pendiente de confirmar (cita, paciente). Lo controla Django, no el prompt.
    borrador = models.JSONField(default=dict, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    ultima_actividad = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-ultima_actividad"]

    def __str__(self):
        return self.telefono


class MensajeWhatsApp(models.Model):
    """Mensaje de una conversación. El contenido se guarda cifrado (ver cifrado.py)."""

    class Rol(models.TextChoices):
        PACIENTE = "paciente", "Paciente"
        AGENTE = "agente", "Agente"
        HUMANO = "humano", "Personal de la clínica"
        SISTEMA = "sistema", "Sistema"

    class Tipo(models.TextChoices):
        TEXTO = "texto", "Texto"
        AUDIO = "audio", "Audio transcrito"

    conversacion = models.ForeignKey(
        ConversacionWhatsApp, on_delete=models.CASCADE, related_name="mensajes"
    )
    rol = models.CharField(max_length=20, choices=Rol.choices)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.TEXTO)
    # Id del mensaje en WhatsApp. Único: evita procesar dos veces un webhook reenviado.
    wa_message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    contenido_cifrado = models.BinaryField()
    creado = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["creado"]

    def __str__(self):
        return f"{self.get_rol_display()} ({self.conversacion})"

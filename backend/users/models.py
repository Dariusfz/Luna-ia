import hashlib

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Usuario(AbstractUser):
    """Usuario del personal de la clínica. Sin registro público (alta por invitación)."""

    class Rol(models.TextChoices):
        ADMIN = "admin", "Administrador"
        DOCTOR = "doctor", "Doctor"
        RECEPCIONISTA = "recepcionista", "Recepcionista"
        ASISTENTE = "asistente", "Asistente"

    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.RECEPCIONISTA)
    sedes = models.ManyToManyField("sedes.Sede", blank=True, related_name="usuarios")


class Invitacion(models.Model):
    """
    Invitación enviada por un admin por correo. El enlace contiene un token que
    solo existe en el correo; en la base de datos se guarda únicamente su hash.
    """

    email = models.EmailField()
    rol = models.CharField(max_length=20, choices=Usuario.Rol.choices)
    sedes = models.ManyToManyField("sedes.Sede", blank=True, related_name="invitaciones")
    token_hash = models.CharField(max_length=64, unique=True)
    creada_por = models.ForeignKey(
        Usuario,
        null=True,
        on_delete=models.SET_NULL,
        related_name="invitaciones_creadas",
    )
    creada = models.DateTimeField(auto_now_add=True)
    expira = models.DateTimeField()
    aceptada_en = models.DateTimeField(null=True, blank=True)
    cancelada = models.BooleanField(default=False)

    class Meta:
        ordering = ["-creada"]

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @property
    def vigente(self) -> bool:
        return (
            not self.cancelada
            and self.aceptada_en is None
            and self.expira > timezone.now()
        )

    def __str__(self):
        return f"Invitación a {self.email} ({self.rol})"


class DispositivoTOTP(models.Model):
    """
    Autenticador TOTP (Google/Microsoft Authenticator) de un usuario.
    El secreto se guarda cifrado (Fernet); nunca en texto plano.
    """

    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="totp"
    )
    secreto_cifrado = models.TextField()
    confirmado = models.BooleanField(default=False)
    # Último paso de tiempo aceptado: impide reutilizar el mismo código (anti-replay).
    ultimo_paso = models.BigIntegerField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"TOTP de {self.usuario.username}"


class CodigoRecuperacion(models.Model):
    """Código de respaldo de un solo uso. Solo se guarda su hash."""

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="codigos_recuperacion"
    )
    hash_codigo = models.CharField(max_length=64)
    usado_en = models.DateTimeField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["usuario", "hash_codigo"])]

    def __str__(self):
        return f"Código de recuperación de {self.usuario.username}"


class RecuperacionContrasena(models.Model):
    """
    Enlace de recuperación de contraseña enviado por correo. Un solo uso y con vencimiento.
    Solo se guarda el hash del token.
    """

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="recuperaciones"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expira = models.DateTimeField()
    usado_en = models.DateTimeField(null=True, blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @property
    def vigente(self) -> bool:
        return self.usado_en is None and self.expira > timezone.now()

    def __str__(self):
        return f"Recuperación de {self.usuario.username}"


class Doctor(models.Model):
    """
    Profesional que atiende. No todos tienen cuenta:
    - propio: personal interno de la clínica (puede tener usuario y sedes asignadas).
    - contratado: doctores por sesión; solo se registran sus visitas y cobros, sin acceso al sistema.
    """

    class Tipo(models.TextChoices):
        PROPIO = "propio", "Interno (personal de la clínica)"
        CONTRATADO = "contratado", "Contratado por sesión"

    usuario = models.OneToOneField(
        Usuario,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="doctor",
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    especialidad = models.ForeignKey(
        "servicios.Especialidad",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="doctores",
    )
    numero_colegiado = models.CharField(max_length=30, blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)
    sedes = models.ManyToManyField("sedes.Sede", blank=True, related_name="doctores")
    observaciones = models.TextField(blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"Dr(a). {self.nombres} {self.apellidos}"

from django.db import models


class ConversacionAsistente(models.Model):
    """
    Conversación del asistente IA interno. Es privada: solo la ve el usuario que la creó,
    incluido el admin (ver `AsistenteView` y las vistas de conversaciones).
    """

    usuario = models.ForeignKey(
        "users.Usuario",
        on_delete=models.CASCADE,
        related_name="conversaciones_asistente",
    )
    titulo = models.CharField(max_length=200, blank=True)
    creada = models.DateTimeField(auto_now_add=True)
    actualizada = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-actualizada", "-id"]
        verbose_name = "conversación del asistente"
        verbose_name_plural = "conversaciones del asistente"

    def __str__(self):
        return f"{self.titulo or 'Conversación'} ({self.usuario})"


class MensajeAsistente(models.Model):
    class Rol(models.TextChoices):
        USUARIO = "usuario", "Usuario"
        ASISTENTE = "asistente", "Asistente"

    conversacion = models.ForeignKey(
        ConversacionAsistente,
        on_delete=models.CASCADE,
        related_name="mensajes",
    )
    rol = models.CharField(max_length=10, choices=Rol.choices)
    texto = models.TextField()
    # Resultado de la consulta analítica que acompaña la respuesta (o None).
    grafica = models.JSONField(null=True, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado", "id"]
        verbose_name = "mensaje del asistente"
        verbose_name_plural = "mensajes del asistente"

    def __str__(self):
        return f"{self.get_rol_display()}: {self.texto[:40]}"

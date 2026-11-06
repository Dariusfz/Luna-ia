from django.contrib import admin

from .models import ConversacionWhatsApp, MensajeWhatsApp, TokenServicio


@admin.register(TokenServicio)
class TokenServicioAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo", "creado", "ultimo_uso"]
    list_filter = ["activo"]
    readonly_fields = ["token_hash", "creado", "ultimo_uso"]
    # El hash no se edita a mano; para revocar se desmarca "activo".
    exclude = ["token_hash"]


@admin.register(ConversacionWhatsApp)
class ConversacionWhatsAppAdmin(admin.ModelAdmin):
    list_display = ["telefono", "paciente", "sede", "estado", "agente_activo", "ultima_actividad"]
    list_filter = ["estado", "agente_activo"]
    search_fields = ["telefono"]
    actions = ["pausar_agente", "reactivar_agente"]

    @admin.action(description="Pausar el agente (responde una persona)")
    def pausar_agente(self, request, queryset):
        queryset.update(agente_activo=False)

    @admin.action(description="Reactivar el agente en estos hilos")
    def reactivar_agente(self, request, queryset):
        queryset.update(agente_activo=True)


@admin.register(MensajeWhatsApp)
class MensajeWhatsAppAdmin(admin.ModelAdmin):
    # El contenido está cifrado: el admin solo muestra metadatos.
    list_display = ["conversacion", "rol", "tipo", "creado"]
    list_filter = ["rol", "tipo"]
    exclude = ["contenido_cifrado"]

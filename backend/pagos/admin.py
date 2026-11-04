from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Pago, PagoDoctor


@admin.register(Pago)
class PagoAdmin(SimpleHistoryAdmin):
    list_display = (
        "fecha",
        "atencion",
        "monto",
        "metodo",
        "registrado_por",
        "creado",
    )
    list_filter = ("metodo", "fecha", "atencion__sede")
    search_fields = (
        "atencion__paciente__nombres",
        "atencion__paciente__apellidos",
        "nota",
    )
    date_hierarchy = "fecha"
    readonly_fields = ("registrado_por", "creado")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)


@admin.register(PagoDoctor)
class PagoDoctorAdmin(SimpleHistoryAdmin):
    list_display = (
        "fecha",
        "doctor",
        "atencion",
        "monto",
        "metodo",
        "registrado_por",
        "creado",
    )
    list_filter = ("metodo", "fecha", "doctor", "atencion__sede")
    search_fields = (
        "doctor__nombres",
        "doctor__apellidos",
        "atencion__paciente__nombres",
        "atencion__paciente__apellidos",
        "nota",
    )
    date_hierarchy = "fecha"
    readonly_fields = ("registrado_por", "creado")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import HallazgoDental, HistoriaClinica, Odontograma, Paciente


@admin.register(Paciente)
class PacienteAdmin(SimpleHistoryAdmin):
    list_display = ("apellidos", "nombres", "identidad", "telefono", "sede_origen")
    list_filter = ("sede_origen", "sexo")
    search_fields = ("nombres", "apellidos", "identidad", "telefono")


class HallazgoDentalInline(admin.TabularInline):
    model = HallazgoDental
    extra = 1
    fields = ("diente", "cara", "estado", "observacion")


@admin.register(HistoriaClinica)
class HistoriaClinicaAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "paciente", "doctor", "sede", "diagnostico")
    list_filter = ("sede", "doctor", "fecha")
    search_fields = ("paciente__nombres", "paciente__apellidos", "diagnostico")
    date_hierarchy = "fecha"
    readonly_fields = ("creado", "actualizado")


@admin.register(Odontograma)
class OdontogramaAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "paciente", "sede", "doctor")
    list_filter = ("sede", "doctor", "fecha")
    search_fields = ("paciente__nombres", "paciente__apellidos")
    date_hierarchy = "fecha"
    inlines = [HallazgoDentalInline]
    readonly_fields = ("creado", "actualizado")

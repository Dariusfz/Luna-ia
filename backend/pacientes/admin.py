from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Paciente


@admin.register(Paciente)
class PacienteAdmin(SimpleHistoryAdmin):
    list_display = ("apellidos", "nombres", "identidad", "telefono", "sede_origen")
    list_filter = ("sede_origen", "sexo")
    search_fields = ("nombres", "apellidos", "identidad", "telefono")

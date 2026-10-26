from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Atencion, JornadaExterna


@admin.register(Atencion)
class AtencionAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "hora_inicio", "hora_fin", "paciente", "doctor", "sede", "tipo_trabajo", "estado", "honorario_doctor")
    list_filter = ("estado", "sede", "fecha", "doctor", "tipo_trabajo")
    search_fields = ("paciente__nombres", "paciente__apellidos", "procedimiento")
    date_hierarchy = "fecha"


@admin.register(JornadaExterna)
class JornadaExternaAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "hora_inicio", "hora_fin", "lugar", "tipo_trabajo", "monto_cobrado")
    list_filter = ("lugar", "tipo_trabajo", "fecha")
    date_hierarchy = "fecha"

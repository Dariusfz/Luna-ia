from django.contrib import admin
from django.db.models import Sum
from simple_history.admin import SimpleHistoryAdmin

from .models import Atencion, AtencionTrabajo, JornadaExterna, ListaEspera


class AtencionTrabajoInline(admin.TabularInline):
    model = AtencionTrabajo
    extra = 1
    fields = ("tipo_trabajo", "precio", "orden")
    ordering = ("orden", "id")


@admin.register(Atencion)
class AtencionAdmin(SimpleHistoryAdmin):
    list_display = (
        "fecha",
        "hora_inicio",
        "hora_fin",
        "paciente",
        "doctor",
        "sede",
        "tipo_trabajo",
        "estado",
        "origen",
        "creado_por",
        "precio_paciente",
        "honorario_doctor",
    )
    list_filter = ("estado", "origen", "sede", "fecha", "doctor", "tipo_trabajo")
    search_fields = ("paciente__nombres", "paciente__apellidos", "procedimiento")
    date_hierarchy = "fecha"
    readonly_fields = ("origen", "creado_por")
    inlines = [AtencionTrabajoInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.origen = Atencion.Origen.PANEL
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        atencion = form.instance
        total = atencion.trabajos.aggregate(total=Sum("precio"))["total"]
        if total is None:
            total = atencion.tipo_trabajo.precio
        if atencion.precio_paciente != total:
            atencion.precio_paciente = total
            atencion.save(update_fields=["precio_paciente"])


@admin.register(JornadaExterna)
class JornadaExternaAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "hora_inicio", "hora_fin", "lugar", "tipo_trabajo", "monto_cobrado")
    list_filter = ("lugar", "tipo_trabajo", "fecha")
    date_hierarchy = "fecha"


@admin.register(ListaEspera)
class ListaEsperaAdmin(admin.ModelAdmin):
    list_display = (
        "paciente",
        "sede",
        "prioridad",
        "estado",
        "doctor",
        "tipo_trabajo",
        "fecha_deseada",
        "creada",
    )
    list_filter = ("estado", "prioridad", "sede", "doctor", "tipo_trabajo")
    search_fields = ("paciente__nombres", "paciente__apellidos", "motivo")

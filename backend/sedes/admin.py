from django.contrib import admin

from .models import Feriado, HorarioSede, LugarExterno, Organizacion, Sede


@admin.register(Organizacion)
class OrganizacionAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creada")


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono", "activa")
    list_filter = ("activa",)


@admin.register(LugarExterno)
class LugarExternoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "direccion", "activo")
    list_filter = ("activo",)


@admin.register(HorarioSede)
class HorarioSedeAdmin(admin.ModelAdmin):
    list_display = ("sede", "dia_semana", "hora_apertura", "hora_cierre")
    list_filter = ("sede", "dia_semana")


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "nombre", "sede", "todo_el_dia", "hora_inicio", "hora_fin")
    list_filter = ("todo_el_dia", "sede")
    search_fields = ("nombre",)

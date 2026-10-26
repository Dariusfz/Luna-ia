from django.contrib import admin

from .models import LugarExterno, Organizacion, Sede


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

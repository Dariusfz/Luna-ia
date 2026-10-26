from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Doctor, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("LUNA-IA", {"fields": ("rol", "sedes")}),)
    list_display = ("username", "email", "rol", "is_active")
    list_filter = ("rol", "is_active")


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("apellidos", "nombres", "tipo", "especialidad", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("nombres", "apellidos", "numero_colegiado")
    filter_horizontal = ("sedes",)

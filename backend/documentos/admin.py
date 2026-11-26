from django.contrib import admin

from .models import Documento


@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = ["titulo", "tipo", "paciente", "sede", "subido_por", "creado"]
    list_filter = ["tipo", "sede"]
    search_fields = ["titulo", "paciente__nombres", "paciente__apellidos"]
    readonly_fields = ["creado"]
    date_hierarchy = "creado"

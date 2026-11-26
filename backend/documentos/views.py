import mimetypes
from urllib.parse import quote

from django.db.models import Q
from django.http import FileResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.permisos import EsAdmin, filtrar_por_sede

from .models import Documento
from .serializers import DocumentoSerializer


class DocumentoViewSet(viewsets.ModelViewSet):
    """Documentos clínicos del paciente. Los archivos se descargan por la API con sesión."""

    serializer_class = DocumentoSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == "destroy":
            return [EsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        consulta = Documento.objects.select_related(
            "paciente", "sede", "subido_por", "atencion__tipo_trabajo", "historia"
        )
        consulta = filtrar_por_sede(consulta, self.request.user)
        if self.action != "list":
            return consulta

        parametros = self.request.query_params
        paciente = parametros.get("paciente", "")
        if str(paciente).isdigit():
            consulta = consulta.filter(paciente_id=int(paciente))

        tipo = parametros.get("tipo", "")
        if tipo in dict(Documento.Tipo.choices):
            consulta = consulta.filter(tipo=tipo)

        sede = parametros.get("sede", "")
        if str(sede).isdigit():
            consulta = consulta.filter(sede_id=int(sede))

        atencion = parametros.get("atencion", "")
        if str(atencion).isdigit():
            consulta = consulta.filter(atencion_id=int(atencion))

        historia = parametros.get("historia", "")
        if str(historia).isdigit():
            consulta = consulta.filter(historia_id=int(historia))

        texto = (parametros.get("q") or "").strip()
        if texto:
            consulta = consulta.filter(
                Q(titulo__icontains=texto)
                | Q(descripcion__icontains=texto)
                | Q(paciente__nombres__icontains=texto)
                | Q(paciente__apellidos__icontains=texto)
            )
        return consulta

    def perform_create(self, serializer):
        serializer.save(subido_por=self.request.user)

    def perform_destroy(self, instance):
        archivo = instance.archivo
        instance.delete()
        if archivo:
            archivo.delete(save=False)

    @action(detail=True, methods=["get"], url_path="archivo")
    def archivo(self, request, pk=None):
        documento = self.get_object()
        try:
            manejador = documento.archivo.open("rb")
        except (FileNotFoundError, OSError):
            return Response({"detail": "El archivo no está disponible."}, status=404)

        tipo_contenido, _ = mimetypes.guess_type(documento.archivo.name)
        descargar = request.query_params.get("descargar") in ("1", "true", "si", "sí")
        respuesta = FileResponse(
            manejador, content_type=tipo_contenido or "application/octet-stream"
        )
        nombre = f"{documento.titulo}{documento.extension}"
        disposicion = "attachment" if descargar else "inline"
        respuesta["Content-Disposition"] = (
            f"{disposicion}; filename*=UTF-8''{quote(nombre)}"
        )
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta

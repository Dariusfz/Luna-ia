from rest_framework import generics
from rest_framework.serializers import ModelSerializer

from sedes.models import Sede

from .autenticacion import EsAgente, TokenServicioAuthentication


class SedeAgenteSerializer(ModelSerializer):
    class Meta:
        model = Sede
        fields = ["id", "nombre", "direccion", "telefono"]


class SedesAgenteView(generics.ListAPIView):
    """Tool `consultar_sedes`: sedes activas, para que el agente resuelva la sede del paciente."""

    authentication_classes = [TokenServicioAuthentication]
    permission_classes = [EsAgente]
    serializer_class = SedeAgenteSerializer
    pagination_class = None

    def get_queryset(self):
        return Sede.objects.filter(activa=True).order_by("nombre")

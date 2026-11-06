from rest_framework import authentication, exceptions
from rest_framework.permissions import BasePermission

from .models import TokenServicio

PREFIJO = "Bearer "


class TokenServicioAuthentication(authentication.BaseAuthentication):
    """
    Autentica al agente con `Authorization: Bearer <token>`.
    Solo se usa en los endpoints de api_agente; el resto del ERP sigue con sesión.
    """

    keyword = PREFIJO

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        cabecera = request.META.get("HTTP_AUTHORIZATION", "")
        if not cabecera.startswith(PREFIJO):
            return None  # Sin credencial de agente: que decidan otros autenticadores.
        token = cabecera[len(PREFIJO):].strip()
        if not token:
            raise exceptions.AuthenticationFailed("Token vacío.")

        servicio = (
            TokenServicio.objects.filter(token_hash=TokenServicio.hash_token(token), activo=True)
            .first()
        )
        if servicio is None:
            raise exceptions.AuthenticationFailed("Token inválido o revocado.")
        servicio.registrar_uso()
        return (servicio, token)


class EsAgente(BasePermission):
    message = "Solo el agente de WhatsApp puede usar este endpoint."

    def has_permission(self, request, view):
        return isinstance(request.user, TokenServicio)

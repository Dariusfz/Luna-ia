from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, serializers, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.viewsets import GenericViewSet

from .invitaciones import aceptar_invitacion, crear_invitacion
from .recuperacion import (
    MENSAJE_SOLICITUD,
    cerrar_sesiones,
    confirmar_recuperacion,
    restablecer_2fa,
    solicitar_recuperacion,
)
from .mfa import (
    consumir_codigo_recuperacion,
    generar_codigos_recuperacion,
    preparar_dispositivo,
    requiere_2fa,
    tiene_2fa_confirmado,
    verificar_totp,
)
from .models import Doctor, DispositivoTOTP, Invitacion, Usuario
from .permisos import EsAdmin, LecturaTodosEscrituraAdmin, es_admin
from .serializers import (
    AceptarInvitacionSerializer,
    ConfirmarRecuperacionSerializer,
    DoctorSerializer,
    InvitacionCrearSerializer,
    InvitacionSerializer,
    LoginSerializer,
    SolicitarRecuperacionSerializer,
    UsuarioAdminSerializer,
    UsuarioEditarSerializer,
    UsuarioSerializer,
)

BACKEND_SESION = "django.contrib.auth.backends.ModelBackend"
CLAVE_PENDIENTE = "auth_2fa_pendiente"


class CodigoSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)


# --- Sesión pendiente de 2FA -------------------------------------------------
# Tras la contraseña, el usuario NO queda autenticado: solo se guarda en la sesión
# quién intenta entrar. La sesión real se crea al verificar el segundo factor.

def _guardar_pendiente(request, usuario):
    request.session[CLAVE_PENDIENTE] = {
        "user_id": usuario.pk,
        "intentos": 0,
        "desde": timezone.now().timestamp(),
    }


def _obtener_pendiente(request):
    """Devuelve el usuario pendiente o None si no existe o ya expiró."""
    datos = request.session.get(CLAVE_PENDIENTE)
    if not datos:
        return None
    vencio = timezone.now().timestamp() - datos["desde"] > settings.TWO_FACTOR_PENDIENTE_MINUTOS * 60
    if vencio:
        request.session.pop(CLAVE_PENDIENTE, None)
        return None
    return Usuario.objects.filter(pk=datos["user_id"], is_active=True).first()


def _registrar_fallo(request):
    """Cuenta un intento fallido. Al llegar al límite, cancela el inicio de sesión."""
    datos = request.session.get(CLAVE_PENDIENTE, {})
    datos["intentos"] = datos.get("intentos", 0) + 1
    if datos["intentos"] >= settings.TWO_FACTOR_MAX_INTENTOS:
        request.session.pop(CLAVE_PENDIENTE, None)
        return "Demasiados intentos. Inicia sesión de nuevo."
    request.session[CLAVE_PENDIENTE] = datos
    return "Código incorrecto."


def _iniciar_sesion(request, usuario):
    request.session.pop(CLAVE_PENDIENTE, None)
    login(request, usuario, backend=BACKEND_SESION)


@api_view(["GET"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request):
    """Entrega la cookie CSRF que necesita el frontend antes de hacer login."""
    return Response({"detail": "ok"})


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        datos = LoginSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = authenticate(
            request,
            username=datos.validated_data["username"],
            password=datos.validated_data["password"],
        )
        # Mensaje genérico para no revelar qué usuarios existen.
        if usuario is None:
            return Response(
                {"detail": "Usuario o contraseña incorrectos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if requiere_2fa(usuario):
            _guardar_pendiente(request, usuario)
            paso = "verificar_2fa" if tiene_2fa_confirmado(usuario) else "configurar_2fa"
            return Response({"paso": paso})

        _iniciar_sesion(request, usuario)
        return Response({"paso": "completo", "usuario": UsuarioSerializer(usuario).data})


class Verificar2FAView(APIView):
    """Segundo paso del login: código de la app o código de recuperación."""

    permission_classes = [AllowAny]

    def post(self, request):
        usuario = _obtener_pendiente(request)
        if usuario is None:
            return Response(
                {"detail": "No hay un inicio de sesión pendiente. Inicia sesión de nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        datos = CodigoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        codigo = datos.validated_data["codigo"]

        dispositivo = DispositivoTOTP.objects.filter(usuario=usuario, confirmado=True).first()
        if dispositivo is None:
            return Response(
                {"detail": "Debes configurar la autenticación de dos pasos primero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valido = verificar_totp(dispositivo, codigo) or consumir_codigo_recuperacion(usuario, codigo)
        if not valido:
            return Response({"detail": _registrar_fallo(request)}, status=status.HTTP_400_BAD_REQUEST)

        _iniciar_sesion(request, usuario)
        return Response({"paso": "completo", "usuario": UsuarioSerializer(usuario).data})


class Configurar2FAView(APIView):
    """Genera el secreto y la URI para el código QR. Requiere un inicio de sesión pendiente."""

    permission_classes = [AllowAny]

    def post(self, request):
        usuario = _obtener_pendiente(request)
        if usuario is None:
            return Response(
                {"detail": "No hay un inicio de sesión pendiente. Inicia sesión de nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not requiere_2fa(usuario):
            return Response(
                {"detail": "Este usuario no requiere autenticación de dos pasos."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if tiene_2fa_confirmado(usuario):
            return Response(
                {"detail": "Ya tienes la autenticación de dos pasos configurada."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        _, secreto, uri = preparar_dispositivo(usuario)
        return Response({"secreto": secreto, "uri": uri})


class Confirmar2FAView(APIView):
    """Confirma el autenticador con un código real, inicia sesión y muestra los códigos de recuperación."""

    permission_classes = [AllowAny]

    def post(self, request):
        usuario = _obtener_pendiente(request)
        if usuario is None:
            return Response(
                {"detail": "No hay un inicio de sesión pendiente. Inicia sesión de nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        datos = CodigoSerializer(data=request.data)
        datos.is_valid(raise_exception=True)

        dispositivo = DispositivoTOTP.objects.filter(usuario=usuario, confirmado=False).first()
        if dispositivo is None:
            return Response(
                {"detail": "No hay una configuración pendiente. Solicítala de nuevo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not verificar_totp(dispositivo, datos.validated_data["codigo"]):
            return Response({"detail": _registrar_fallo(request)}, status=status.HTTP_400_BAD_REQUEST)

        dispositivo.confirmado = True
        dispositivo.save(update_fields=["confirmado"])
        codigos = generar_codigos_recuperacion(usuario)
        _iniciar_sesion(request, usuario)
        return Response(
            {
                "paso": "completo",
                "usuario": UsuarioSerializer(usuario).data,
                # Se muestran una sola vez; luego no pueden recuperarse.
                "codigos_recuperacion": codigos,
            }
        )


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)


class InvitacionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet):
    """Solo el administrador puede invitar personal y ver las invitaciones."""

    permission_classes = [EsAdmin]
    serializer_class = InvitacionSerializer
    queryset = Invitacion.objects.prefetch_related("sedes")

    def create(self, request, *args, **kwargs):
        datos = InvitacionCrearSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        invitacion = crear_invitacion(
            email=datos.validated_data["email"],
            rol=datos.validated_data["rol"],
            sedes=datos.validated_data.get("sedes", []),
            creada_por=request.user,
        )
        # El token nunca se devuelve en la respuesta; solo viaja por correo.
        return Response(
            InvitacionSerializer(invitacion).data, status=status.HTTP_201_CREATED
        )


class AceptarInvitacionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        datos = AceptarInvitacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = aceptar_invitacion(**datos.validated_data)
        return Response(UsuarioSerializer(usuario).data, status=status.HTTP_201_CREATED)


class DoctorViewSet(viewsets.ModelViewSet):
    """
    Doctores de la clínica. Cualquier usuario ve los de sus sedes; solo el admin crea
    o modifica. No se borran: se desactivan (campo activo).
    """

    serializer_class = DoctorSerializer
    permission_classes = [LecturaTodosEscrituraAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = Doctor.objects.select_related("usuario").prefetch_related(
            "especialidades", "sedes"
        )
        user = self.request.user
        if not es_admin(user):
            qs = qs.filter(sedes__in=user.sedes.all()).distinct()
        # Filtros solo en el listado. Query: q (nombre/especialidad), tipo, activo, sede.
        if self.action != "list":
            return qs
        params = self.request.query_params
        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(nombres__icontains=texto)
                | Q(apellidos__icontains=texto)
                | Q(especialidades__nombre__icontains=texto)
            )
        tipo = params.get("tipo", "")
        if tipo in Doctor.Tipo.values:
            qs = qs.filter(tipo=tipo)
        activo = params.get("activo", "todos")
        if activo == "true":
            qs = qs.filter(activo=True)
        elif activo == "false":
            qs = qs.filter(activo=False)
        sede = params.get("sede", "")
        if sede.isdigit():
            qs = qs.filter(sedes__id=int(sede))
        return qs.distinct()


class SolicitarRecuperacionView(APIView):
    """Envía el enlace de recuperación. Responde igual exista o no la cuenta."""

    permission_classes = [AllowAny]

    def post(self, request):
        datos = SolicitarRecuperacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        solicitar_recuperacion(datos.validated_data["email"])
        return Response({"detail": MENSAJE_SOLICITUD})


class ConfirmarRecuperacionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        datos = ConfirmarRecuperacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        confirmar_recuperacion(**datos.validated_data)
        return Response({"detail": "Contraseña actualizada. Inicia sesión de nuevo."})


class UsuarioViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    GenericViewSet,
):
    """
    Personal de la clínica. Solo el admin lo consulta y lo modifica (rol, sedes, activo).
    No se borra: se desactiva. Filtros: q (nombre o usuario), rol, activo (true|false|todos).
    """

    permission_classes = [EsAdmin]
    serializer_class = UsuarioAdminSerializer
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        qs = Usuario.objects.prefetch_related("sedes").order_by("first_name", "last_name")
        params = self.request.query_params

        texto = params.get("q", "").strip()
        if texto:
            qs = qs.filter(
                Q(first_name__icontains=texto)
                | Q(last_name__icontains=texto)
                | Q(username__icontains=texto)
            )
        rol = params.get("rol", "")
        if rol in Usuario.Rol.values:
            qs = qs.filter(rol=rol)
        activo = params.get("activo", "todos")
        if activo == "true":
            qs = qs.filter(is_active=True)
        elif activo == "false":
            qs = qs.filter(is_active=False)
        return qs

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return UsuarioEditarSerializer
        return UsuarioAdminSerializer

    def update(self, request, *args, **kwargs):
        usuario = self.get_object()
        datos = UsuarioEditarSerializer(usuario, data=request.data, partial=True, context={"request": request})
        datos.is_valid(raise_exception=True)
        datos.save()
        if usuario.is_active is False:
            # Una cuenta desactivada no debe conservar sesiones abiertas.
            cerrar_sesiones(usuario)
        return Response(UsuarioAdminSerializer(usuario).data)

    @action(detail=True, methods=["post"], url_path="restablecer-2fa")
    def restablecer_2fa_view(self, request, pk=None):
        usuario = self.get_object()
        restablecer_2fa(usuario)
        return Response(
            {"detail": f"Se restableció el 2FA de {usuario.username}. Deberá configurarlo al entrar."}
        )

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from agenda.views import AtencionViewSet, JornadaExternaViewSet, ListaEsperaViewSet
from pacientes.views import PacienteViewSet
from pagos.views import PagoDoctorViewSet, PagoViewSet, ResumenCajaView
from sedes.views import FeriadoViewSet, HorarioSedeViewSet, LugarExternoViewSet, SedeViewSet
from servicios.views import EspecialidadViewSet, TipoTrabajoViewSet
from users.views import (
    AceptarInvitacionView,
    Configurar2FAView,
    ConfirmarRecuperacionView,
    Confirmar2FAView,
    DoctorViewSet,
    InvitacionViewSet,
    LoginView,
    LogoutView,
    MeView,
    SolicitarRecuperacionView,
    UsuarioViewSet,
    Verificar2FAView,
    csrf,
)

router = DefaultRouter()
router.register("invitaciones", InvitacionViewSet, basename="invitacion")
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("doctores", DoctorViewSet, basename="doctor")
router.register("pacientes", PacienteViewSet, basename="paciente")
router.register("atenciones", AtencionViewSet, basename="atencion")
router.register("lista-espera", ListaEsperaViewSet, basename="lista-espera")
router.register("jornadas-externas", JornadaExternaViewSet, basename="jornada-externa")
router.register("pagos", PagoViewSet, basename="pago")
router.register("pagos-doctores", PagoDoctorViewSet, basename="pago-doctor")
router.register("sedes", SedeViewSet, basename="sede")
router.register("horarios-sede", HorarioSedeViewSet, basename="horario-sede")
router.register("feriados", FeriadoViewSet, basename="feriado")
router.register("lugares-externos", LugarExternoViewSet, basename="lugar-externo")
router.register("tipos-trabajo", TipoTrabajoViewSet, basename="tipo-trabajo")
router.register("especialidades", EspecialidadViewSet, basename="especialidad")

urlpatterns = [
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/auth/csrf/", csrf, name="auth-csrf"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/auth/2fa/verificar/", Verificar2FAView.as_view(), name="auth-2fa-verificar"),
    path("api/auth/2fa/configurar/", Configurar2FAView.as_view(), name="auth-2fa-configurar"),
    path("api/auth/2fa/confirmar/", Confirmar2FAView.as_view(), name="auth-2fa-confirmar"),
    path(
        "api/auth/aceptar-invitacion/",
        AceptarInvitacionView.as_view(),
        name="auth-aceptar-invitacion",
    ),
    path(
        "api/auth/recuperar/",
        SolicitarRecuperacionView.as_view(),
        name="auth-recuperar",
    ),
    path(
        "api/auth/recuperar/confirmar/",
        ConfirmarRecuperacionView.as_view(),
        name="auth-recuperar-confirmar",
    ),
    path("api/caja/resumen/", ResumenCajaView.as_view(), name="caja-resumen"),
    path("api/agente/", include("api_agente.urls")),
    path("api/", include(router.urls)),
]

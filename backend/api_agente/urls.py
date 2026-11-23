from django.urls import path

from .panel import (
    ConversacionPanelActualizarView,
    ConversacionPanelDetalleView,
    ConversacionesPanelView,
    ResumenAgenteView,
)
from .views import SedesAgenteView
from .webhook import WebhookEvolutionView

urlpatterns = [
    path("sedes/", SedesAgenteView.as_view(), name="agente-sedes"),
    path(
        "webhook/evolution/<str:secreto>/",
        WebhookEvolutionView.as_view(),
        name="agente-webhook-evolution",
    ),
    path(
        "panel/resumen/",
        ResumenAgenteView.as_view(),
        name="agente-panel-resumen",
    ),
    path(
        "panel/conversaciones/",
        ConversacionesPanelView.as_view(),
        name="agente-panel-conversaciones",
    ),
    path(
        "panel/conversaciones/<int:pk>/",
        ConversacionPanelDetalleView.as_view(),
        name="agente-panel-conversacion",
    ),
    path(
        "panel/conversaciones/<int:pk>/actualizar/",
        ConversacionPanelActualizarView.as_view(),
        name="agente-panel-conversacion-actualizar",
    ),
]

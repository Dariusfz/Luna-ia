from django.urls import path

from .views import SedesAgenteView
from .webhook import WebhookEvolutionView

urlpatterns = [
    path("sedes/", SedesAgenteView.as_view(), name="agente-sedes"),
    path(
        "webhook/evolution/<str:secreto>/",
        WebhookEvolutionView.as_view(),
        name="agente-webhook-evolution",
    ),
]

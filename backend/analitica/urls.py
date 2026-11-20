from django.urls import path

from .asistente import AsistenteView, ConversacionDetalleView, ConversacionesView
from .views import (
    AtendidosMesView,
    CitasHoyView,
    IngresosView,
    PorHoraView,
    PorSedeView,
    PorServicioView,
)

urlpatterns = [
    path("citas-hoy/", CitasHoyView.as_view(), name="analitica-citas-hoy"),
    path("atendidos-mes/", AtendidosMesView.as_view(), name="analitica-atendidos-mes"),
    path("por-servicio/", PorServicioView.as_view(), name="analitica-por-servicio"),
    path("por-hora/", PorHoraView.as_view(), name="analitica-por-hora"),
    path("por-sede/", PorSedeView.as_view(), name="analitica-por-sede"),
    path("ingresos/", IngresosView.as_view(), name="analitica-ingresos"),
    path("asistente/", AsistenteView.as_view(), name="analitica-asistente"),
    path(
        "asistente/conversaciones/",
        ConversacionesView.as_view(),
        name="analitica-asistente-conversaciones",
    ),
    path(
        "asistente/conversaciones/<int:pk>/",
        ConversacionDetalleView.as_view(),
        name="analitica-asistente-conversacion",
    ),
]



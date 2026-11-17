from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from servicios.models import TipoTrabajo

from . import herramientas
from .models import ConversacionWhatsApp


class TratamientoMencionadoTests(SimpleTestCase):
    def test_acepta_el_tratamiento_que_pidio_el_paciente(self):
        self.assertTrue(herramientas._tratamiento_mencionado(["quiero una extracción"], "Extraccion"))
        self.assertTrue(herramientas._tratamiento_mencionado(["limpieza por favor"], "Limpieza de dientes"))

    def test_tolera_errores_de_ortografia(self):
        self.assertTrue(herramientas._tratamiento_mencionado(["quiero una estraccion"], "Extraccion"))

    def test_rechaza_un_tratamiento_que_no_pidio(self):
        self.assertFalse(herramientas._tratamiento_mencionado(["quiero cita mañana"], "Ondodoncia"))
        self.assertFalse(herramientas._tratamiento_mencionado(["sí, confirmo"], "Limpieza de dientes"))


class ConsultaTratamientosTests(TestCase):
    def setUp(self):
        self.conversacion = ConversacionWhatsApp.objects.create(telefono="+50499999999")
        TipoTrabajo.objects.create(nombre="Limpieza dental", precio=Decimal("500.00"))
        TipoTrabajo.objects.create(nombre="Extracción", precio=Decimal("800"), activo=False)
        self.herramientas = herramientas.Herramientas(self.conversacion)

    def test_lista_solo_tratamientos_activos_con_precio(self):
        resultado = self.herramientas.consultar_tratamientos({})
        self.assertEqual(
            resultado,
            [{"tratamiento": "Limpieza dental", "precio_referencia_hnl": "500.00", "descripcion": ""}],
        )

    def test_filtra_por_texto(self):
        self.assertEqual(self.herramientas.consultar_tratamientos({"texto": "limp"})[0]["tratamiento"], "Limpieza dental")
        self.assertEqual(self.herramientas.consultar_tratamientos({"texto": "ortodoncia"}), [])

    def test_ejecutar_despacha_las_nuevas_herramientas(self):
        resultado = self.herramientas.ejecutar("consultar_tratamientos", {"texto": "limpieza"})
        self.assertIn("resultado", resultado)
        revision = self.herramientas.ejecutar("solicitar_revision_administrador", {"motivo": "ortodoncia"})
        self.assertEqual(revision, {"resultado": {"registrado": True}})

    def test_respuesta_ambigua_no_confirma_y_pide_sí_o_no(self):
        from django.utils import timezone

        from .cifrado import cifrar
        from .models import MensajeWhatsApp

        self.conversacion.borrador = {
            "tipo": "cita", "datos": {}, "resumen": "Cita", "creado": timezone.now().isoformat(),
        }
        self.conversacion.estado = ConversacionWhatsApp.Estado.ESPERANDO_CONFIRMACION
        self.conversacion.save()
        MensajeWhatsApp.objects.create(
            conversacion=self.conversacion, rol=MensajeWhatsApp.Rol.PACIENTE,
            contenido_cifrado=cifrar("so"),
        )
        resultado = self.herramientas.ejecutar("confirmar_accion", {})
        self.assertIn("sí o no", resultado["error"])

    def test_solicitud_al_administrador_registra_el_motivo(self):
        with self.assertLogs("api_agente.herramientas", level="WARNING") as capturado:
            self.herramientas.solicitar_revision_administrador({"motivo": "Ortodoncia completa"})
        self.assertIn("Ortodoncia completa", capturado.output[0])

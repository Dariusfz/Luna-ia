from decimal import Decimal

from django.test import SimpleTestCase
from rest_framework import serializers

from config.validadores import MONTO_MAXIMO

from .serializers import TipoTrabajoSerializer


class TipoTrabajoSerializerTests(SimpleTestCase):
    def test_precio_en_el_limite_se_acepta(self):
        validador = TipoTrabajoSerializer()
        self.assertEqual(validador.validate_precio(MONTO_MAXIMO), MONTO_MAXIMO)

    def test_precio_mayor_al_limite_se_rechaza(self):
        validador = TipoTrabajoSerializer()
        with self.assertRaises(serializers.ValidationError):
            validador.validate_precio(MONTO_MAXIMO + Decimal("0.01"))

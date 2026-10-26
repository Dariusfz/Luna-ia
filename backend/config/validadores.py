import re
from decimal import Decimal

MENSAJE_TELEFONO = "Escribe 8 dígitos después de +504, por ejemplo +504 9999-9999."

MONTO_MAXIMO = Decimal("500000.00")
MENSAJE_MONTO_MAXIMO = "El monto no puede superar L 500,000.00."


def normalizar_telefono_hn(valor: str) -> str:
    """
    Devuelve el teléfono como '+504 XXXX-XXXX'. Acepta '9999-9999', '99999999',
    '504 9999 9999' o '+504 9999-9999'. Vacío se permite (campo opcional).
    Lanza ValueError si no tiene exactamente 8 dígitos locales.
    """
    if not valor:
        return ""
    digitos = re.sub(r"\D", "", valor)
    if digitos.startswith("504") and len(digitos) == 11:
        digitos = digitos[3:]
    if len(digitos) != 8:
        raise ValueError(MENSAJE_TELEFONO)
    return f"+504 {digitos[:4]}-{digitos[4:]}"

"""
Cifrado de contenido de mensajes (Fernet). La clave viene de MENSAJES_ENCRYPTION_KEY.
Si no se define (solo desarrollo), se deriva de DJANGO_SECRET_KEY, igual que TOTP.
"""

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(settings.MENSAJES_ENCRYPTION_KEY.encode("ascii"))


def cifrar(texto: str) -> bytes:
    return _fernet().encrypt(texto.encode("utf-8"))


def descifrar(token: bytes) -> str:
    return _fernet().decrypt(bytes(token)).decode("utf-8")

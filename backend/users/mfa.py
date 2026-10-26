"""
Autenticación de dos pasos (TOTP) para admin y doctor (plan §6, AGENTS.md regla 5).

- El secreto TOTP se guarda cifrado con Fernet (TOTP_ENCRYPTION_KEY).
- Un código TOTP no se puede reutilizar (anti-replay por paso de tiempo).
- Los códigos de recuperación son de un solo uso y solo se guardan como hash.
"""

import hashlib
import hmac
import secrets
import time

import pyotp
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone

from .models import CodigoRecuperacion, DispositivoTOTP, Usuario

ALFABETO_RECUPERACION = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sin caracteres ambiguos
CANTIDAD_CODIGOS_RECUPERACION = 10


def requiere_2fa(usuario) -> bool:
    return bool(
        usuario.is_superuser or usuario.rol in (Usuario.Rol.ADMIN, Usuario.Rol.DOCTOR)
    )


def _fernet() -> Fernet:
    return Fernet(settings.TOTP_ENCRYPTION_KEY.encode("ascii"))


def _normalizar(codigo: str) -> str:
    return codigo.replace(" ", "").strip()


def _ahora() -> float:
    """Reloj del TOTP. Se separa para poder simularlo en las pruebas."""
    return time.time()


def tiene_2fa_confirmado(usuario) -> bool:
    return DispositivoTOTP.objects.filter(usuario=usuario, confirmado=True).exists()


def preparar_dispositivo(usuario):
    """
    Crea (o reemplaza, si aún no está confirmado) el autenticador del usuario.
    Devuelve (dispositivo, secreto en claro, uri para el código QR).
    """
    secreto = pyotp.random_base32()
    cifrado = _fernet().encrypt(secreto.encode("utf-8")).decode("ascii")
    dispositivo, _ = DispositivoTOTP.objects.update_or_create(
        usuario=usuario,
        defaults={"secreto_cifrado": cifrado, "confirmado": False, "ultimo_paso": None},
    )
    uri = pyotp.TOTP(secreto).provisioning_uri(
        name=usuario.username, issuer_name=settings.TOTP_EMISOR
    )
    return dispositivo, secreto, uri


def verificar_totp(dispositivo: DispositivoTOTP, codigo: str) -> bool:
    """Valida un código de 6 dígitos con tolerancia de ±1 paso (30 s) y sin repetir pasos."""
    codigo = _normalizar(codigo)
    if not codigo.isdigit() or len(codigo) != 6:
        return False

    secreto = _fernet().decrypt(dispositivo.secreto_cifrado.encode("ascii")).decode("utf-8")
    totp = pyotp.TOTP(secreto)
    paso_actual = int(_ahora()) // totp.interval

    for paso in range(paso_actual - 1, paso_actual + 2):
        if dispositivo.ultimo_paso is not None and paso <= dispositivo.ultimo_paso:
            continue
        esperado = totp.at(paso * totp.interval)
        if hmac.compare_digest(esperado, codigo):
            dispositivo.ultimo_paso = paso
            dispositivo.save(update_fields=["ultimo_paso"])
            return True
    return False


def _hash_recuperacion(codigo: str) -> str:
    """Hash independiente de mayúsculas, espacios y guion: 'ab12c-d3ef4' == 'AB12CD3EF4'."""
    limpio = _normalizar(codigo).replace("-", "").upper()
    return hashlib.sha256(limpio.encode("utf-8")).hexdigest()


def generar_codigos_recuperacion(usuario) -> list[str]:
    """Reemplaza los códigos anteriores. Devuelve los códigos en claro (se muestran una sola vez)."""
    CodigoRecuperacion.objects.filter(usuario=usuario).delete()
    codigos = []
    for _ in range(CANTIDAD_CODIGOS_RECUPERACION):
        bruto = "".join(secrets.choice(ALFABETO_RECUPERACION) for _ in range(10))
        codigo = f"{bruto[:5]}-{bruto[5:]}"
        CodigoRecuperacion.objects.create(usuario=usuario, hash_codigo=_hash_recuperacion(codigo))
        codigos.append(codigo)
    return codigos


def consumir_codigo_recuperacion(usuario, codigo: str) -> bool:
    registro = CodigoRecuperacion.objects.filter(
        usuario=usuario,
        hash_codigo=_hash_recuperacion(codigo),
        usado_en__isnull=True,
    ).first()
    if registro is None:
        return False
    registro.usado_en = timezone.now()
    registro.save(update_fields=["usado_en"])
    return True

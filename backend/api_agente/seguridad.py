"""
Reglas de seguridad del agente que se aplican en código, no en el prompt.

- Mensajes de emergencia: se responden con un texto fijo y el teléfono de la clínica.
- Intentos de manipulación (pedir reglas, contraseñas, cambiar de rol): se responden
  con un rechazo fijo y no llegan al modelo.
- Revisión de la salida: si el modelo intenta mostrar identificadores internos,
  credenciales o datos personales que no estaban en la conversación, se bloquea.
"""

import re

# ---- confirmación explícita -------------------------------------------------

AFIRMATIVO = re.compile(
    r"\b(s[ií]|confirmo|confirmado|correcto|dale|ok|okay|de acuerdo|est[aá] bien|perfecto)\b",
    re.IGNORECASE,
)


NEGACION = re.compile(
    r"\b(no\s+quiero|no\s+gracias|mejor\s+no|olv[ií]dalo|d[eé]jalo|cancela|cancelar|cancelamos)\b",
    re.IGNORECASE,
)
SOLO_NO = {"no", "nop", "nope", "nel"}


def es_afirmativo(texto: str) -> bool:
    return bool(AFIRMATIVO.search(texto or ""))


def es_negacion(texto: str) -> bool:
    limpio = (texto or "").strip().lower()
    return limpio in SOLO_NO or bool(NEGACION.search(limpio))


# ---- respuestas fijas -------------------------------------------------------

RESPUESTA_MANIPULACION = (
    "No puedo darte esa información. Solo puedo ayudarte con citas, sedes y horarios "
    "de la clínica."
)

RESPUESTA_BLOQUEADA = (
    "No puedo compartir esa información. Si necesitas algo sobre tu cita, con gusto te ayudo."
)


def mensaje_emergencia(telefonos) -> str:
    contacto = f" El teléfono de la clínica es {telefonos[0]}." if telefonos else ""
    return (
        "Lamento mucho lo que te pasa. Por tu seguridad no puedo darte indicaciones médicas. "
        "Si hay dolor intenso, sangrado o hinchazón, acude a urgencias o llama a la clínica."
        f"{contacto}"
    )


# ---- detección de intención ------------------------------------------------

EMERGENCIA = re.compile(
    r"("
    r"dolor\s+(muy\s+)?(fuerte|intenso|insoportable)"
    r"|sangr(a|ado|ando)\s+(mucho|bastante|sin\s+parar)"
    r"|no\s+puedo\s+respirar"
    r"|se\s+me\s+rompi[oó]\s+un?\s+diente"
    r"|diente\s+roto"
    r"|golpe\s+(fuerte\s+)?en\s+(la\s+)?(cara|boca|mand[ií]bula)"
    r"|hinchaz[oó]n\s+(fuerte|grande)"
    r"|fiebre\s+alta"
    r")",
    re.IGNORECASE,
)

MANIPULACION = re.compile(
    r"("
    r"ignora\s+(tus|las)\s+(instrucciones|reglas)"
    r"|olvida\s+(tus|las)\s+(instrucciones|reglas)"
    r"|system\s*prompt|prompt\s+del\s+sistema"
    r"|act[uú]a\s+como|modo\s+desarrollador|developer\s+mode|jailbreak"
    r"|revela\s+(tus|el)\s+(instrucciones|prompt)"
    r"|dime\s+tus\s+reglas"
    r"|contrase[ñn]a|password|passwd|api\s*key|token\s+de\s+acceso"
    r"|usuario\s+del\s+administrador"
    r")",
    re.IGNORECASE,
)


def detectar_emergencia(texto: str) -> bool:
    return bool(EMERGENCIA.search(texto or ""))


def es_manipulacion(texto: str) -> bool:
    return bool(MANIPULACION.search(texto or ""))


# ---- revisión de la salida del modelo --------------------------------------

_ID_INTERNO = re.compile(r"\b(?:id|ID)\s*[:#]?\s*\d+")
_DNI = re.compile(r"\b\d{13}\b")
_CREDENCIALES = re.compile(
    r"\b(contrase[ñn]a|password|passwd|api\s*key|token\s+de\s+acceso)\b", re.IGNORECASE
)
_ADMINISTRACION = re.compile(r"\b(usuario|cuenta)\s+del\s+administrador\b", re.IGNORECASE)


def _aparece_en(texto: str, permitidos) -> bool:
    return any(texto in permitido for permitido in permitidos)


def revisar_salida(texto: str, permitidos) -> str | None:
    """Devuelve el motivo del bloqueo, o None si la respuesta se puede enviar."""
    if _ID_INTERNO.search(texto):
        return "identificador interno"
    if _CREDENCIALES.search(texto) or _ADMINISTRACION.search(texto):
        return "credenciales o administración"
    for dni in _DNI.finditer(texto):
        if not _aparece_en(dni.group(), permitidos):
            return "dato personal no solicitado"
    return None

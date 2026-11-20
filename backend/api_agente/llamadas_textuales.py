"""
Llamadas a herramientas escritas como texto.

Algunos modelos, en vez de devolver `tool_calls` estructurado, escriben la llamada en el
contenido con marcas DSML. Aquí se reconoce ese formato y se convierte al formato estándar,
y se limpian las marcas para que nunca lleguen al usuario.
"""

import json
import re

_MARCA = r"[｜|]DSML[｜|]"
_RE_INVOKE = re.compile(
    rf"<{_MARCA}\s*invoke\s+name=\"([^\"]+)\"\s*>(.*?)</{_MARCA}\s*invoke\s*>", re.DOTALL
)
_RE_PARAMETRO = re.compile(
    rf"<{_MARCA}\s*parameter\s+name=\"([^\"]+)\"([^>]*)>(.*?)</{_MARCA}\s*parameter\s*>",
    re.DOTALL,
)
_RE_MARCAS = re.compile(rf"</?{_MARCA}[^>]*>")


def llamadas_textuales(texto) -> list[dict]:
    """Convierte las llamadas escritas como texto en el formato de `tool_calls`."""
    llamadas = []
    for indice, invocacion in enumerate(_RE_INVOKE.finditer(texto or "")):
        argumentos = {}
        for parametro in _RE_PARAMETRO.finditer(invocacion.group(2)):
            nombre, atributos, valor = parametro.group(1), parametro.group(2), parametro.group(3).strip()
            if 'string="false"' in atributos:
                try:
                    valor = json.loads(valor)
                except json.JSONDecodeError:
                    pass
            argumentos[nombre] = valor
        llamadas.append(
            {
                "id": f"texto_{indice}",
                "type": "function",
                "function": {
                    "name": invocacion.group(1),
                    "arguments": json.dumps(argumentos, ensure_ascii=False),
                },
            }
        )
    return llamadas


def sin_marcas(texto) -> str:
    """Quita las llamadas y marcas DSML que el modelo pudo dejar en el texto."""
    limpio = _RE_INVOKE.sub("", texto or "")
    return _RE_MARCAS.sub("", limpio).strip()

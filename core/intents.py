import re

from .numbers import norm


def intencion(texto):
    """Preguntas que se responden con código (sin LLM): cuota o resumen de caja."""
    n = norm(texto)
    if re.search(r"cuota|prestamo|credito|pagar al mes|cuanto puedo pagar", n):
        return "cuota"
    if re.search(r"cuanto (he |has )?(gane|ganado|vendi|llevo|tengo|me queda)|resumen|como voy|mi caja|flujo", n):
        return "resumen"
    return None

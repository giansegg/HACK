import re

from .numbers import norm


def intencion(texto):
    """Preguntas que se responden con código (sin LLM): cuota o resumen de caja."""
    n = norm(texto)
    if re.search(r"cuota|prestamo|(puedo|podria|alcanza para) pagar|pagar al mes|me prestan|sacar un credito|pedir un credito", n):
        return "cuota"
    if re.search(r"cuanto (he |has )?(gane|ganado|vendi|llevo|tengo|me queda)|resumen|como voy|mi caja|flujo", n):
        return "resumen"
    return None

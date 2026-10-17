"""Textos para Doña Rosa: cortos y en lenguaje simple."""
from .export import fmt_cant

ETIQUETA = {"venta": "Venta", "gasto": "Gasto", "fiado": "Fiado", "cobro_fiado": "Cobro de fiado"}


def describe(r):
    monto = "falta el monto" if r["monto"] is None else f"S/ {r['monto']:.2f}"
    quien = f" ({r['cliente']})" if r.get("cliente") else ""
    return f"{ETIQUETA[r['tipo']]}: {fmt_cant(r['cantidad'])} {r['producto']}{quien} — {monto}"


def pregunta_para(r):
    cant, prod = fmt_cant(r["cantidad"]), r["producto"]
    quien = r.get("cliente") or "el cliente"
    return {
        "venta": f"¿Cuánto cobraste por {cant} {prod}? Dime el precio de cada uno o el total.",
        "gasto": f"¿Cuánto pagaste por {prod}?",
        "fiado": f"¿Cuánto debe {quien} por {cant} {prod}?",
        "cobro_fiado": f"¿Cuánto te pagó {quien}?",
    }[r["tipo"]]


def lineas(res, ledger):
    """res: resultado de extractor.procesar. Devuelve [(tipo, texto)] con tipo ok | falta | info | pregunta."""
    out = [("ok" if r["monto"] is not None else "falta", describe(r)) for r in res["nuevas"]]
    out += [("ok", f"Completé: {describe(r)}") for r in res["completadas"]]
    if res.get("nota"):
        out.append(("info", res["nota"]))
    out += [("info", a) for a in res["avisos"]]
    if not res["nuevas"] and not res["completadas"] and not res.get("nota"):
        out.append(("info", "No encontré nada para anotar ahí. Cuéntame una venta, un gasto o un fiado."))
    pend = ledger.pendientes()
    if pend:
        out.append(("pregunta", pregunta_para(pend[-1])))
    return out


def respuesta(res, ledger):
    return "\n\n".join(t for _, t in lineas(res, ledger))

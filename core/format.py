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


def pend_nuevas(res):
    return [r for r in res["nuevas"] if r["monto"] is None]


def respuesta(res, ledger):
    """res: resultado de extractor.procesar para un mensaje."""
    lineas = [f"✅ Anoté: {describe(r)}" for r in res["nuevas"] if r["monto"] is not None]
    lineas += [f"✅ Listo, completé: {describe(r)}" for r in res["completadas"]]
    if res.get("nota"):
        lineas.append(f"ℹ️ {res['nota']}")
    lineas += [f"ℹ️ {a}" for a in res["avisos"]]
    if not res["nuevas"] and not res["completadas"] and not res.get("nota") and not pend_nuevas(res):
        lineas.append("No encontré nada para anotar en ese mensaje. ¿Me lo repites?")
    pend = ledger.pendientes()
    if pend:
        lineas.append("🤔 Me falta un dato. " + pregunta_para(pend[0]))
    return "\n\n".join(lineas)

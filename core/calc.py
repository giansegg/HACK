"""Flujo de caja y cuota: todo se calcula en código, el LLM no interviene."""
import math

from . import config


def money(x):
    return f"S/ {x:,.2f}"


def resumen(ledger):
    rows = ledger.rows
    def suma(tipo):
        return round(sum(r["monto"] for r in rows if r["tipo"] == tipo and r["monto"] is not None), 2)

    ventas, cobros, gastos = suma("venta"), suma("cobro_fiado"), suma("gasto")
    return {
        "ventas": ventas, "cobros": cobros, "gastos": gastos,
        "flujo": round(ventas + cobros - gastos, 2),
        "pendientes": sum(1 for r in rows if r["monto"] is None),
        "dias": len({r.get("dia") for r in rows if r.get("dia")}),
    }


def por_cobrar(ledger):
    ab = ledger.abiertos()
    return round(sum(e["restante"] for e in ab if e["restante"] is not None), 2), sum(1 for e in ab if e["restante"] is None)


def resumen_texto(ledger):
    r = resumen(ledger)
    pc, desconocidos = por_cobrar(ledger)
    t = [f"Vendiste {money(r['ventas'])}, cobraste fiados por {money(r['cobros'])} y gastaste {money(r['gastos'])}.",
         f"**Te quedan {money(r['flujo'])}** (ventas + cobros − gastos)."]
    if pc or desconocidos:
        extra = f" y {desconocidos} fiado(s) sin monto" if desconocidos else ""
        t.append(f"Por cobrar en fiados: {money(pc)}{extra} (no entra a la caja todavía).")
    if r["pendientes"]:
        t.append(f"Ojo: hay {r['pendientes']} movimiento(s) sin monto que todavía no conté.")
    return "\n\n".join(t)


def estimar_cuota(ledger, pct=None):
    pct = config.CUOTA_PCT if pct is None else pct
    r = resumen(ledger)
    dias = 7 if r["dias"] >= 5 else max(r["dias"], 1)
    mensual = r["flujo"] / dias * 30
    base = max(mensual * pct, 0.0)
    cuota = math.floor(base / 5) * 5
    t = [f"En la semana vendiste {money(r['ventas'])}, cobraste fiados por {money(r['cobros'])} y gastaste {money(r['gastos'])}.",
         f"Te quedan {money(r['flujo'])} (ventas + cobros − gastos)."]
    if r["flujo"] <= 0:
        t.append("Con lo registrado, la caja todavía no alcanza para pagar una cuota.")
        cuota = 0
    else:
        t.append(f"En un mes (30 días) serían unos {money(mensual)}  ({money(r['flujo'])} ÷ {dias} días × 30).")
        t.append(f"Para que la cuota no te ahogue, usaría como máximo el {int(round(pct * 100))}% de eso: {money(base)}.")
        t.append(f"**Cuota sugerida: unos {money(cuota)} al mes** (redondeado hacia abajo).")
    if r["dias"] < 5:
        t.append(f"Solo tengo {r['dias']} día(s) de datos; la estimación es poco confiable.")
    if r["pendientes"]:
        t.append(f"No conté {r['pendientes']} movimiento(s) que están sin monto.")
    t.append("Esto es solo una estimación para ayudarte a organizarte; no es un crédito aprobado ni una promesa de aprobación.")
    return {"cuota": cuota, "base": round(base, 2), "mensual": round(mensual, 2), "texto": "\n\n".join(t), **r}

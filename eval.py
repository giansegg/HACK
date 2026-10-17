"""Mide la exactitud contra la clave del kit (necesita una clave de IA).

python eval.py               # evalúa los 30 mensajes sin usar sus propias respuestas como ejemplos
python eval.py --desde E16   # solo desde ese mensaje (los anteriores se cargan de la clave)
"""
import argparse
import sys

from core import calc, extractor
from core.ledger import Ledger

sys.stdout.reconfigure(encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("--desde", default="E01")
args = ap.parse_args()

mensajes = extractor._leer("ejemplos_mensajes.csv")
clave = {}
for r in extractor._leer("ejemplos_respuestas.csv"):
    clave.setdefault(r["id_mensaje"], []).append(r)

led = Ledger()
a_evaluar = []
for m in mensajes:
    if m["id_mensaje"] < args.desde:
        for r in clave.get(m["id_mensaje"], []):  # contexto previo tomado de la clave
            led.add(id_mensaje=m["id_mensaje"], dia=m["dia"], tipo=r["tipo"], producto=r["producto"], cantidad=float(r["cantidad"]),
                    monto=float(r["monto"]) if r["monto"] else None, cliente=extractor.CLIENTES_EJEMPLO.get(m["id_mensaje"], ""))
    else:
        a_evaluar.append({"id": m["id_mensaje"], "dia": m["dia"], "mensaje": m["mensaje"]})

previas = len(led.rows)
extractor.procesar(a_evaluar, led, modo="lote", excluir=[m["id"] for m in a_evaluar])
pred = led.rows[previas:]

bien = total = extra = 0
for m in a_evaluar:
    k = [dict(r) for r in clave.get(m["id"], [])]
    p = [r for r in pred if r["id_mensaje"] == m["id"]]
    resto = list(p)
    for r in k:
        total += 1
        hit = next((x for x in resto if x["tipo"] == r["tipo"] and (
            (x["monto"] is None and not r["monto"]) or (x["monto"] is not None and r["monto"] and abs(x["monto"] - float(r["monto"])) < 0.011))), None)
        if hit:
            bien += 1
            resto.remove(hit)
        else:
            print(f"✗ {m['id']} «{m['mensaje']}»\n    esperado: {r['tipo']} {r['producto']} {r['monto'] or '(vacío)'}")
    for x in resto:
        extra += 1
        print(f"+ {m['id']} fila de más: {x['tipo']} {x['producto']} {x['monto']}")

print(f"\nFilas correctas: {bien}/{total} ({100 * bien / max(total, 1):.0f}%) · filas de más: {extra}")
print(f"Flujo del modelo: {calc.resumen(led)['flujo']:.2f}  (clave: 788.90 si evalúas los 30)")

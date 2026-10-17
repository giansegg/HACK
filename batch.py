"""Procesa un CSV de mensajes (id_mensaje,dia,mensaje) y escribe el CSV de entrega.

python batch.py set_oculto.csv resultados_miequipo.csv
"""
import csv
import sys

from core import calc, export, extractor
from core.ledger import Ledger

sys.stdout.reconfigure(encoding="utf-8")

if len(sys.argv) != 3:
    sys.exit("Uso: python batch.py entrada.csv salida.csv")

with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
    msgs = [{"id": r["id_mensaje"], "dia": r.get("dia", ""), "mensaje": r["mensaje"]} for r in csv.DictReader(f)]

led = Ledger()
extractor.procesar(msgs, led, modo="lote", progreso=lambda i, n: print(f"{i}/{n}", end="\r"))
with open(sys.argv[2], "wb") as f:
    f.write(export.a_csv_bytes(led.rows))
print(f"\n{len(led.rows)} filas -> {sys.argv[2]} · flujo semanal: {calc.resumen(led)['flujo']:.2f}")

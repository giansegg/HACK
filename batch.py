"""Procesa un CSV de mensajes (id_mensaje,dia,mensaje) y escribe el CSV de entrega.

python batch.py set_oculto.csv resultados_miequipo.csv
"""
import csv
import sys

from core import calc, config, export, extractor
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
c = calc.estimar_cuota(led)
resumen_csv = sys.argv[2].removesuffix(".csv") + "_cuota.csv"
with open(resumen_csv, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["concepto", "valor"])
    for k, v in [("ventas_semana", c["ventas"]), ("cobros_fiado_semana", c["cobros"]), ("gastos_semana", c["gastos"]),
                 ("flujo_semanal", c["flujo"]), ("flujo_mensual_estimado", c["mensual"]),
                 ("porcentaje_del_flujo_para_cuota", config.CUOTA_PCT), ("cuota_mensual_sugerida", c["cuota"])]:
        w.writerow([k, f"{v:.2f}"])
print(f"\n{len(led.rows)} filas -> {sys.argv[2]} · flujo semanal: {calc.resumen(led)['flujo']:.2f}")

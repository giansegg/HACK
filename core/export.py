"""Salida en el formato exacto de la plantilla de entrega."""
import pandas as pd

COLUMNAS = ["id_mensaje", "tipo", "producto", "cantidad", "monto", "requiere_confirmacion"]


def fmt_cant(c):
    return int(c) if float(c).is_integer() else float(c)


def a_df(rows):
    data = [{"id_mensaje": r["id_mensaje"], "tipo": r["tipo"], "producto": r["producto"],
             "cantidad": fmt_cant(r["cantidad"]),
             "monto": "" if r["monto"] is None else f"{r['monto']:.2f}",
             "requiere_confirmacion": "SI" if r["monto"] is None else "NO"} for r in rows]
    return pd.DataFrame(data, columns=COLUMNAS)


def a_csv_bytes(rows):
    return a_df(rows).to_csv(index=False).encode("utf-8")

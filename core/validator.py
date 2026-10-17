"""Capa determinista entre el LLM y el libro: nada se guarda sin pasar por aquí."""
import math

from .numbers import candidatos, grounded, norm, numeros

TIPOS = {"venta", "gasto", "fiado", "cobro_fiado"}


def _num(x):
    if x is None or x == "":
        return None
    try:
        v = float(str(x).replace(",", ".").replace("S/", "").strip())
    except ValueError:
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def validar(raw_filas, mensaje, ledger, strict=True):
    """Devuelve (filas_validas, avisos). Un monto que no se puede justificar con lo
    que dijo la usuaria se deja vacío y se pide confirmación."""
    cands = candidatos(numeros(mensaje))
    filas, avisos = [], []
    for f in raw_filas or []:
        if not isinstance(f, dict):
            continue
        tipo = norm(str(f.get("tipo", ""))).strip().replace(" ", "_")
        if tipo not in TIPOS:
            avisos.append(f"Ignoré una fila con tipo desconocido: {f.get('tipo')!r}.")
            continue
        producto = str(f.get("producto") or "").strip()
        cantidad = _num(f.get("cantidad"))
        if cantidad is None or cantidad <= 0:
            cantidad = 1
        cliente = str(f.get("cliente") or "").strip()
        monto = _num(f.get("monto"))
        if monto is not None and monto <= 0:
            monto = None
        if tipo == "cobro_fiado":
            recordado = ledger.recall(cliente, producto)
            if monto is None and recordado is not None:
                monto = recordado
            elif monto is not None and strict and not grounded(monto, cands, [recordado] if recordado else []):
                avisos.append(f"No pude comprobar el monto {monto:.2f} de «{producto}»; prefiero preguntarte.")
                monto = None
        elif monto is not None and strict and not grounded(monto, cands):
            avisos.append(f"No pude comprobar el monto {monto:.2f} de «{producto}» con lo que dijiste; prefiero preguntarte.")
            monto = None
        filas.append({
            "tipo": tipo, "producto": producto, "cantidad": cantidad,
            "monto": None if monto is None else round(monto, 2),
            "requiere_confirmacion": "SI" if monto is None else "NO",
            "cliente": cliente,
        })
    return filas, avisos


def aplicar_completar(items, respuesta, ledger):
    """Aplica las respuestas de la usuaria a filas pendientes (monto o precio unitario)."""
    nums = numeros(respuesta)
    base = candidatos(nums)
    hechas = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        ref = "".join(ch for ch in str(it.get("ref", "")) if ch.isdigit())
        row = ledger.get(int(ref)) if ref else None
        if row is None or row["monto"] is not None:
            continue
        extra = {round(row["cantidad"] * n, 2) for n in nums}
        monto, pu = _num(it.get("monto")), _num(it.get("precio_unitario"))
        if monto is None and pu is not None and grounded(pu, nums):
            monto = round(pu * row["cantidad"], 2)
        elif monto is not None and not grounded(monto, base, extra):
            monto = None
        if monto is not None and monto > 0:
            hechas.append(ledger.update(row["uid"], monto=round(monto, 2), requiere_confirmacion="NO"))
    return hechas

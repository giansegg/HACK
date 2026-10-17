"""Servidor de Mi Caja: API sobre core/ y la interfaz web (web/).

    python -m uvicorn server:app --port 8000      (desde la carpeta mvp)
"""
import csv
import io
import os
import threading
import time

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import calc, config, export, extractor, llm
from core.format import respuesta
from core.intents import intencion
from core.ledger import Ledger
from core.numbers import norm

WEB = config.BASE / "web"
ASSETS = config.BASE / "assets"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIA_NORM = {norm(d): d for d in DIAS}
CAMPOS = {"id_mensaje", "dia", "tipo", "producto", "cantidad", "monto", "requiere_confirmacion", "cliente"}
ERROR_TXT = "Uy, no pude procesar eso ahora 😅 ¿Me lo repites en un momento?"

app = FastAPI(title="Mi Caja")
ledger = Ledger(config.DATA / "ledger.json")
if os.getenv("MANTENER_DATOS") != "1":  # cada arranque empieza con el libro vacío
    ledger.reset()
SESION = str(int(time.time()))  # el navegador borra su chat si el servidor se reinició
lock = threading.Lock()
estado = {"msg_n": len({r["id_mensaje"] for r in ledger.rows if str(r.get("id_mensaje", "")).startswith("C")})}


# ------------------------------------------------------------------ estado del libro para el dashboard
def libro():
    r = calc.resumen(ledger)
    pc, sin_monto = calc.por_cobrar(ledger)
    c = calc.estimar_cuota(ledger)
    por_dia = {d: {"dia": d, "ventas": 0.0, "gastos": 0.0} for d in DIAS}
    conceptos, conteo = {}, {"venta": 0, "gasto": 0, "fiado": 0, "cobro_fiado": 0}
    for row in ledger.rows:
        conteo[row["tipo"]] = conteo.get(row["tipo"], 0) + 1
        if row["monto"] is None:
            continue
        d = _DIA_NORM.get(norm(row.get("dia", "")))
        if d and row["tipo"] in ("venta", "cobro_fiado"):
            por_dia[d]["ventas"] += row["monto"]
        elif d and row["tipo"] == "gasto":
            por_dia[d]["gastos"] += row["monto"]
        if row["tipo"] == "gasto":
            conceptos[row["producto"]] = conceptos.get(row["producto"], 0) + row["monto"]
    top = sorted(conceptos.items(), key=lambda kv: -kv[1])
    if len(top) > 6:
        top = top[:5] + [("Otros", sum(v for _, v in top[5:]))]
    return {
        "rows": ledger.rows,
        "resumen": r,
        "por_cobrar": pc,
        "fiados_sin_monto": sin_monto,
        "fiados": [{"cliente": e["cliente"], "producto": e["producto"], "debe": e["restante"]} for e in ledger.abiertos()],
        "cuota": {"cuota": c["cuota"], "base": c["base"], "mensual": c["mensual"], "pct": config.CUOTA_PCT,
                  "dias": 7 if r["dias"] >= 5 else max(r["dias"], 1), "texto": c["texto"]},
        "por_dia": [{**v, "ventas": round(v["ventas"], 2), "gastos": round(v["gastos"], 2)} for v in por_dia.values()],
        "gastos_concepto": [{"concepto": k, "monto": round(v, 2)} for k, v in top],
        "conteo": conteo,
    }


def _responder(texto, dia):
    """Devuelve (burbujas de respuesta, movimientos anotados)."""
    quiere = intencion(texto)
    if quiere == "cuota":
        out, movs = calc.estimar_cuota(ledger)["texto"], []
    elif quiere == "resumen":
        out, movs = calc.resumen_texto(ledger), []
    else:
        estado["msg_n"] += 1
        res = extractor.procesar([{"id": f"C{estado['msg_n']:03d}", "dia": dia, "mensaje": texto}], ledger, modo="chat")[0]
        out = respuesta(res, ledger)
        movs = [m for m in res["completadas"] + res["nuevas"] if m["monto"] is not None]
    return [p for p in out.split("\n\n") if p.strip()], movs


# ------------------------------------------------------------------ chat
class Mensaje(BaseModel):
    texto: str
    dia: str = ""


@app.post("/api/mensaje")
def mensaje(m: Mensaje):
    with lock:
        try:
            burbujas, movs = _responder(m.texto.strip(), m.dia)
            error = None
        except Exception as e:  # noqa: BLE001
            burbujas, movs, error = [ERROR_TXT], [], f"{type(e).__name__}: {e}"
        return {"respuestas": burbujas, "movimientos": movs, "error": error, "libro": libro()}


@app.post("/api/audio")
def audio(archivo: UploadFile = File(...), dia: str = Form("")):
    data = archivo.file.read()
    with lock:
        try:
            texto = llm.transcribir(data, archivo.filename or "nota.webm")
        except Exception as e:  # noqa: BLE001
            return {"transcripcion": "", "respuestas": ["No pude escuchar el audio 🙈 ¿Me lo repites?"], "movimientos": [],
                    "error": f"{type(e).__name__}: {e}", "libro": libro()}
        if not texto:
            return {"transcripcion": "", "respuestas": ["No alcancé a escucharte bien 🙈 ¿Me lo repites?"], "movimientos": [],
                    "error": None, "libro": libro()}
        try:
            burbujas, movs = _responder(texto, dia)
            error = None
        except Exception as e:  # noqa: BLE001
            burbujas, movs, error = [ERROR_TXT], [], f"{type(e).__name__}: {e}"
        return {"transcripcion": texto, "respuestas": burbujas, "movimientos": movs, "error": error, "libro": libro()}


# ------------------------------------------------------------------ libro / dashboard
@app.get("/api/libro")
def get_libro():
    return libro()


@app.delete("/api/registro/{uid}")
def borrar(uid: int):
    with lock:
        fila = ledger.get(uid)
        if fila is None:
            return JSONResponse({"error": "No existe ese registro"}, status_code=404)
        fila = dict(fila)
        ledger.delete(uid)
        return {"borrado": fila, "libro": libro()}


@app.post("/api/registro")
def restaurar(fila: dict):
    """Vuelve a agregar un registro (para el botón Deshacer)."""
    with lock:
        ledger.add(**{k: v for k, v in fila.items() if k in CAMPOS})
        return {"libro": libro()}


@app.post("/api/ejemplo")
def cargar_ejemplo():
    with lock:
        ledger.reset()
        dias = {m["id_mensaje"]: m["dia"] for m in extractor._leer("ejemplos_mensajes.csv")}
        for r in extractor._leer("ejemplos_respuestas.csv"):
            ledger.add(id_mensaje=r["id_mensaje"], dia=dias[r["id_mensaje"]], tipo=r["tipo"], producto=r["producto"],
                       cantidad=float(r["cantidad"]), monto=float(r["monto"]) if r["monto"] else None,
                       cliente=extractor.CLIENTES_EJEMPLO.get(r["id_mensaje"], ""))
        return {"libro": libro()}


@app.post("/api/reset")
def reset():
    with lock:
        ledger.reset()
        estado["msg_n"] = 0
        return {"libro": libro()}


# ------------------------------------------------------------------ lote (set oculto)
@app.post("/api/lote")
def lote(archivo: UploadFile | None = File(None), usar_ejemplos: bool = Form(False)):
    if archivo is not None and archivo.filename:
        filas = list(csv.DictReader(io.StringIO(archivo.file.read().decode("utf-8-sig"))))
        msgs = [{"id": f["id_mensaje"], "dia": f.get("dia", ""), "mensaje": f["mensaje"]} for f in filas]
    elif usar_ejemplos:
        msgs = [{"id": m["id_mensaje"], "dia": m["dia"], "mensaje": m["mensaje"]} for m in extractor._leer("ejemplos_mensajes.csv")]
    else:
        return JSONResponse({"error": "Sube un CSV o marca 'usar ejemplos'"}, status_code=400)
    with lock:
        nuevo = Ledger()
        try:
            extractor.procesar(msgs, nuevo, modo="lote", excluir=[m["id"] for m in msgs] if usar_ejemplos and archivo is None else ())
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)
        ledger.reset()
        for row in nuevo.rows:
            row.pop("uid", None)
            ledger.add(**row)
        return {"mensajes": len(msgs), "filas": len(ledger.rows), "libro": libro()}


@app.get("/api/resultados.csv")
def resultados(equipo: str = "equipo"):
    nombre = "".join(ch for ch in equipo if ch.isalnum() or ch in "-_") or "equipo"
    return Response(export.a_csv_bytes(ledger.rows), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="resultados_{nombre}.csv"'})


# ------------------------------------------------------------------ varios
@app.get("/api/estado")
def get_estado():
    return {"groq": bool(config.get_key()), "modelo": config.MODEL, "voz": config.STT_MODEL, "sesion": SESION}


@app.get("/api/avatar")
def avatar():
    """La foto del bot: assets/bot.png|jpg|webp si existe; si no, assets/bot.svg."""
    for n in ("bot.png", "bot.jpg", "bot.jpeg", "bot.webp", "bot.svg"):
        p = ASSETS / n
        if p.exists():
            return FileResponse(p, headers={"Cache-Control": "no-cache"})
    return Response(status_code=404)


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")

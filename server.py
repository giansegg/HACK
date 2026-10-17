"""Servidor de la Caja de Doña Rosa: API en FastAPI + interfaz web estática (carpeta web/).

    uvicorn server:app --reload
"""
import csv
import datetime as dt
import io
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from typing import Optional

from pydantic import BaseModel

from core import calc, config, export, extractor, llm
from core.export import fmt_cant
from core.format import lineas
from core.intents import intencion
from core.ledger import Ledger
from core.numbers import norm

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
WEB = Path(__file__).parent / "web"
SESIONES = config.DATA / "sesiones"

app = FastAPI(title="Caja de Doña Rosa")
_libros: dict[str, Ledger] = {}
_lock = threading.Lock()


def libro(request: Request) -> Ledger:
    """Cada navegador tiene su propio libro (id guardado en el dispositivo)."""
    sid = request.headers.get("x-sesion", "")
    if not re.fullmatch(r"[A-Za-z0-9-]{8,64}", sid):
        raise HTTPException(400, "Sesión inválida")
    with _lock:
        if sid not in _libros:
            _libros[sid] = Ledger(SESIONES / f"{sid}.json")
        return _libros[sid]


def hoy():
    return DIAS[dt.datetime.now().weekday()]


def graficas(led: Ledger):
    """Datos para las gráficas: entradas y salidas por día, y productos que más venden / más se gastan."""
    dias = {norm(d): d for d in DIAS}
    por_dia = {d: {"dia": d, "entro": 0.0, "salio": 0.0} for d in DIAS}
    ventas, gastos = {}, {}
    for r in led.rows:
        if r["monto"] is None:
            continue
        d = dias.get(norm(r.get("dia", "")))
        if r["tipo"] in ("venta", "cobro_fiado") and d:
            por_dia[d]["entro"] += r["monto"]
        elif r["tipo"] == "gasto" and d:
            por_dia[d]["salio"] += r["monto"]
        nombre = (r["producto"] or "").strip().capitalize()
        if r["tipo"] == "venta" and "suelt" not in norm(nombre):
            ventas[nombre] = ventas.get(nombre, 0) + r["monto"]
        elif r["tipo"] == "gasto":
            gastos[nombre] = gastos.get(nombre, 0) + r["monto"]
    top = lambda d: [{"nombre": k, "monto": round(v, 2)} for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:5]]
    return {"dias": [{**v, "entro": round(v["entro"], 2), "salio": round(v["salio"], 2)} for v in por_dia.values()],
            "ventas": top(ventas), "gastos": top(gastos)}


def serializar(led: Ledger):
    r = calc.resumen(led)
    cuota = calc.estimar_cuota(led)
    pc, _ = calc.por_cobrar(led)
    return {
        "resumen": {**r, "entro": round(r["ventas"] + r["cobros"], 2), "por_cobrar": pc},
        "movimientos": [{"tipo": x["tipo"], "producto": x["producto"], "cantidad": fmt_cant(x["cantidad"]),
                         "cliente": x.get("cliente", ""), "dia": x.get("dia", ""), "monto": x["monto"]}
                        for x in reversed(led.rows)],
        "fiados": [{"cliente": e["cliente"], "producto": e["producto"], "debe": e["restante"]} for e in led.abiertos()],
        "graficas": graficas(led),
        "cuota": {"valor": cuota["cuota"], "texto": cuota["texto"]},
    }


class Mensaje(BaseModel):
    texto: str
    dia: Optional[str] = None


@app.get("/api/estado")
def estado(request: Request):
    return {"ia": config.proveedores_activos(), **serializar(libro(request))}


@app.post("/api/chat")
def chat(m: Mensaje, request: Request):
    led = libro(request)
    texto = m.texto.strip()[:1000]
    if not texto:
        raise HTTPException(400, "Mensaje vacío")
    quiere = intencion(texto)
    if quiere == "cuota":
        out = [("texto", calc.estimar_cuota(led)["texto"])]
    elif quiere == "resumen":
        out = [("texto", calc.resumen_texto(led))]
    else:
        try:
            led_id = f"C{sum(1 for r in led.rows if str(r['id_mensaje']).startswith('C')) + 1:03d}"
            res = extractor.procesar([{"id": led_id, "dia": m.dia or hoy(), "mensaje": texto}], led, modo="chat")[0]
            out = lineas(res, led)
        except Exception as e:  # noqa: BLE001
            print(f"[error chat] {type(e).__name__}: {e}")
            out = [("info", "No pude anotar eso ahora mismo. Inténtalo de nuevo en un momento.")]
    return {"lineas": [{"tipo": t, "texto": x} for t, x in out], "proveedor": llm.ultimo_proveedor, **serializar(led)}


@app.post("/api/voz")
async def voz(request: Request):
    libro(request)
    audio = await request.body()
    if len(audio) < 800:
        raise HTTPException(400, "Audio vacío")
    if len(audio) > 8_000_000:
        raise HTTPException(413, "Audio muy largo")
    tipo = request.headers.get("content-type", "")
    nombre = "nota.mp4" if "mp4" in tipo else "nota.ogg" if "ogg" in tipo else "nota.webm" if "webm" in tipo else "nota.wav"
    try:
        return {"texto": llm.transcribir(audio, nombre)}
    except Exception as e:  # noqa: BLE001
        print(f"[error voz] {type(e).__name__}: {e}")
        raise HTTPException(502, "No pude escuchar el audio")


@app.post("/api/reset")
def reset(request: Request):
    led = libro(request)
    led.reset()
    return serializar(led)


@app.post("/api/ejemplo")
def ejemplo(request: Request):
    led = libro(request)
    led.reset()
    dias = {m["id_mensaje"]: m["dia"] for m in extractor._leer("ejemplos_mensajes.csv")}
    for x in extractor._leer("ejemplos_respuestas.csv"):
        led.add(id_mensaje=x["id_mensaje"], dia=dias[x["id_mensaje"]], tipo=x["tipo"], producto=x["producto"],
                cantidad=float(x["cantidad"]), monto=float(x["monto"]) if x["monto"] else None,
                cliente=extractor.CLIENTES_EJEMPLO.get(x["id_mensaje"], ""))
    return serializar(led)


@app.post("/api/lote")
async def lote(request: Request):
    """Cuerpo: CSV con columnas id_mensaje,dia,mensaje. Devuelve el CSV de entrega."""
    led = libro(request)
    texto = (await request.body()).decode("utf-8-sig")
    msgs = [{"id": f["id_mensaje"], "dia": f.get("dia", ""), "mensaje": f["mensaje"]} for f in csv.DictReader(io.StringIO(texto))]
    if not msgs:
        raise HTTPException(400, "CSV vacío")
    nuevo = Ledger()
    try:
        extractor.procesar(msgs, nuevo, modo="lote")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"No se pudo procesar: {e}")
    led.reset()
    for row in nuevo.rows:
        row.pop("uid", None)
        led.add(**row)
    return Response(export.a_csv_bytes(led.rows), media_type="text/csv")


@app.exception_handler(HTTPException)
async def _http(_, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.get("/")
def raiz():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")

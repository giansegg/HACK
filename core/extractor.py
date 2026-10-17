"""Mensaje -> filas contables: LLM (Groq) + validación y libro en código."""
import csv
import json
import re

from . import config, llm
from .ledger import Ledger
from .numbers import norm
from .validator import aplicar_completar, validar

CLIENTES_EJEMPLO = {"E03": "Rosa María", "E12": "Rosa María", "E14": "don Pepe", "E21": "don Pepe"}
CASOS_FIJOS = ["E06", "E09", "E11", "E12", "E14", "E26"]

REGLAS = """Eres el módulo de registro contable de la bodega de Doña Rosa (Lima, Perú). Ella manda mensajes de voz transcritos o escritos, con errores de tipeo y lenguaje coloquial. Conviertes cada mensaje en filas de movimientos. Respondes SOLO con JSON válido.

TIPOS:
- venta: venta cobrada en el momento (entra plata).
- gasto: compras de mercadería, servicios (agua, luz, gas), pagos a proveedores o ayudantes, y devoluciones de dinero a clientes (sale plata).
- fiado: venta a crédito; el cliente se lleva el producto y paga después. No mueve la caja.
- cobro_fiado: un cliente paga algo que debía (entra plata).

REGLAS:
1. "monto" es el TOTAL en soles de esa fila: cantidad x precio unitario, restando descuentos o rebajas. Número con punto decimal, sin "S/".
2. Una fila por producto u operación. Un mensaje puede dar varias filas, o ninguna (gastos personales o de la casa que no son del negocio, saludos).
3. Si el mensaje se corrige ("no perdón, fueron 8"), usa solo la versión corregida.
4. Si dice un total del día sin detalle ("salieron 210 en ventas sueltas"), es UNA fila venta con producto "ventas sueltas" (o el nombre dicho) y cantidad 1.
5. NUNCA inventes ni supongas datos que no dijo. Si falta el precio o el monto, pon "monto": null. Jamás uses 0.
6. Si dice un precio por unidad ("a 4 soles el kilo"), monto = cantidad x precio. Los números pueden venir en letras ("seis cincuenta" = 6.50).
7. Normaliza el producto a su nombre simple y corrige typos ("guevos" = huevos).
8. En fiado y cobro_fiado completa "cliente" con el nombre o referencia (don Pepe, vecina).
9. cobro_fiado sin monto: deja "monto": null (el sistema lo completa con el fiado ya registrado). Si dice cuánto pagó, ese es el monto.
10. Devolución de dinero a un cliente = gasto.
11. Si recibes "filas_pendientes" (movimientos que esperan un dato) y el mensaje responde a ese dato, devuelve "completar" con {"ref","monto"} (total) o {"ref","precio_unitario"} y NO repitas la fila en "filas". Si el mensaje es otro movimiento, ignora las pendientes y usa "filas".
12. "nota": una frase corta solo si dejaste algo fuera (ej. gasto personal); si no, null.

FORMATO DE SALIDA (siempre así, un elemento por mensaje recibido, en el mismo orden y con el mismo id):
{"resultados":[{"id":"<id>","filas":[{"tipo":"venta","producto":"pan","cantidad":10,"cliente":"","monto":3.0}],"completar":[],"nota":null}]}
"""

_STOP = {"de", "la", "el", "los", "las", "a", "y", "en", "un", "una", "que", "me", "se", "lo", "al", "del", "por", "para", "mi"}


def _toks(s):
    return {t for t in re.findall(r"[a-z]+", norm(s)) if t not in _STOP} | ({"#num"} if re.search(r"\d", s) else set())


def _leer(nombre):
    with open(config.DATA / nombre, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num_o_none(x):
    return None if x == "" else float(x)


def cargar_ejemplos():
    resp = {}
    for r in _leer("ejemplos_respuestas.csv"):
        fila = {"tipo": r["tipo"], "producto": r["producto"],
                "cantidad": int(float(r["cantidad"])) if float(r["cantidad"]).is_integer() else float(r["cantidad"]),
                "monto": _num_o_none(r["monto"]), "cliente": CLIENTES_EJEMPLO.get(r["id_mensaje"], "")}
        resp.setdefault(r["id_mensaje"], []).append(fila)
    return [{"id": m["id_mensaje"], "dia": m["dia"], "mensaje": m["mensaje"], "filas": resp.get(m["id_mensaje"], [])}
            for m in _leer("ejemplos_mensajes.csv")]


def seleccionar_ejemplos(mensajes, k=None, excluir=()):
    """Casos difíciles fijos + los ejemplos más parecidos a los mensajes recibidos."""
    k = config.N_SHOTS_SIMILARES if k is None else k
    todos = [e for e in cargar_ejemplos() if e["id"] not in set(excluir)]
    elegidos = [e for e in todos if e["id"] in CASOS_FIJOS]
    ya = {e["id"] for e in elegidos}
    objetivo = set().union(*[_toks(m) for m in mensajes]) if mensajes else set()
    resto = sorted((e for e in todos if e["id"] not in ya),
                   key=lambda e: -len(_toks(e["mensaje"]) & objetivo) / (len(_toks(e["mensaje"]) | objetivo) or 1))
    return elegidos + resto[:k]


def _shot(e):
    filas = [{k: v for k, v in f.items() if not (k == "cliente" and not v)} for f in e["filas"]]
    return f'Mensaje: {e["mensaje"]}\nSalida: {json.dumps({"filas": filas}, ensure_ascii=False, separators=(",", ":"))}'


def build_system(mensajes=(), excluir=()):
    ejemplos = seleccionar_ejemplos(list(mensajes), excluir=excluir)
    return REGLAS + "\nEJEMPLOS (cada uno es un mensaje y su lista de filas):\n" + "\n\n".join(_shot(e) for e in ejemplos)


def _pedir(grupo, ledger, modo, excluir):
    payload = {"mensajes": [{"id": m["id"], "dia": m["dia"], "mensaje": m["mensaje"]} for m in grupo]}
    pend = ledger.pendientes() if modo == "chat" else []
    if pend:
        payload["filas_pendientes"] = [{"ref": f"P{p['uid']}", "tipo": p["tipo"], "producto": p["producto"],
                                        "cantidad": p["cantidad"], "cliente": p["cliente"]} for p in pend]
    data = llm.chat_json(build_system([m["mensaje"] for m in grupo], excluir),
                         json.dumps(payload, ensure_ascii=False), max_tokens=4000)
    return {str(r.get("id")): r for r in data.get("resultados", []) if isinstance(r, dict)}


def procesar(mensajes, ledger, modo="lote", progreso=None, strict=True, excluir=()):
    """Procesa mensajes [{id, dia, mensaje}] en orden y los guarda en el libro.

    modo 'chat': un mensaje; las filas con monto vacío se pueden completar con la respuesta.
    modo 'lote': varios mensajes por llamada (cuida el límite de tokens por minuto); los fiados
    se recuerdan en código, así que las dependencias entre mensajes se respetan al validar.
    Devuelve una lista de {id, nuevas, completadas, nota, avisos, pendientes}."""
    tam = 1 if modo == "chat" else max(config.BATCH_SIZE, 1)
    salida, hechos = [], 0
    for i in range(0, len(mensajes), tam):
        grupo = mensajes[i:i + tam]
        try:
            resp = _pedir(grupo, ledger, modo, excluir)
        except Exception:
            if modo == "chat":
                raise
            resp = {}
        for m in grupo:
            r = resp.get(str(m["id"]))
            if r is None:  # el modelo se saltó este mensaje o falló el lote: se pide solo
                r = _pedir([m], ledger, modo, excluir).get(str(m["id"]), {})
            completadas = aplicar_completar(r.get("completar"), m["mensaje"], ledger) if modo == "chat" else []
            filas, avisos = validar(r.get("filas"), m["mensaje"], ledger, strict)
            nuevas = [ledger.add(**f, id_mensaje=m["id"], dia=m["dia"]) for f in filas]
            salida.append({"id": m["id"], "nuevas": nuevas, "completadas": completadas, "nota": r.get("nota"),
                           "avisos": avisos, "pendientes": ledger.pendientes()})
            hechos += 1
            if progreso:
                progreso(hechos, len(mensajes))
    return salida

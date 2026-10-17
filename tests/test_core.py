"""Pruebas offline (sin API): python tests/test_core.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from core import calc, config, extractor, llm
from core.ledger import Ledger
from core.numbers import candidatos, grounded, numeros
from core.validator import aplicar_completar, validar


def ok(monto, texto):
    return grounded(monto, candidatos(numeros(texto)))


def test_numeros_y_grounding():
    assert numeros("vendi dos kilos de azucar a cuatro soles el kilo") == [2, 4]
    assert numeros("treinta y cinco") == [35]
    assert ok(8, "vendi dos kilos de azucar a cuatro soles el kilo")
    assert ok(19.5, "vendí tres cervezas a seis cincuenta")
    assert ok(180, "compré al mayorista 1 saco de arroz a 190, me rebajó 10")
    assert ok(2.4, "vendí 5 panes a 0.30, no perdón, fueron 8")
    assert ok(13, "vendí 12 panes a 0.30 y 2 detergentes a 6.50")
    assert not ok(12, "vendí 3 atunes")  # monto inventado


def test_validador_blanquea_montos_inventados():
    led = Ledger()
    filas, avisos = validar([{"tipo": "venta", "producto": "atún", "cantidad": 3, "monto": 12}], "vendí 3 atunes", led)
    assert filas[0]["monto"] is None and filas[0]["requiere_confirmacion"] == "SI" and avisos


def test_recordar_fiado():
    led = Ledger()
    led.add(id_mensaje="E03", tipo="fiado", producto="aceite primor", cantidad=1, monto=11.0, cliente="Rosa María")
    filas, _ = validar([{"tipo": "cobro_fiado", "producto": "aceite", "cliente": "la señora Rosa María", "monto": None}],
                       "la señora Rosa María me pagó lo del aceite", led)
    assert filas[0]["monto"] == 11.0 and filas[0]["requiere_confirmacion"] == "NO"


def test_fiado_sin_monto_no_se_inventa():
    led = Ledger()
    led.add(id_mensaje="E14", tipo="fiado", producto="cerveza", cantidad=2, monto=None, cliente="don Pepe")
    filas, _ = validar([{"tipo": "cobro_fiado", "producto": "", "cliente": "don Pepe", "monto": None}],
                       "don Pepe me pagó", led)
    assert filas[0]["monto"] is None and filas[0]["requiere_confirmacion"] == "SI"


def test_pago_parcial_reduce_deuda():
    led = Ledger()
    led.add(tipo="fiado", producto="arroz", cantidad=1, monto=30.0, cliente="don Pepe")
    led.add(tipo="cobro_fiado", producto="pago", cantidad=1, monto=10.0, cliente="don Pepe")
    assert led.recall("don Pepe", "") == 20.0


def test_completar_repregunta():
    led = Ledger()
    f = led.add(id_mensaje="C01", tipo="venta", producto="atún", cantidad=3, monto=None, requiere_confirmacion="SI")
    hechas = aplicar_completar([{"ref": f"P{f['uid']}", "precio_unitario": 4}], "a 4 soles cada uno", led)
    assert hechas and led.get(f["uid"])["monto"] == 12.0
    g = led.add(id_mensaje="C02", tipo="venta", producto="atún", cantidad=3, monto=None)
    assert not aplicar_completar([{"ref": f"P{g['uid']}", "monto": 99}], "mmm no sé", led)  # inventado: se ignora


def test_flujo_de_la_semana_de_ejemplo():
    clave = pd.read_csv(config.DATA / "ejemplos_respuestas.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    msgs = pd.read_csv(config.DATA / "ejemplos_mensajes.csv", dtype=str, encoding="utf-8-sig").set_index("id_mensaje").dia
    led = Ledger()
    for _, r in clave.iterrows():
        led.add(id_mensaje=r.id_mensaje, dia=msgs[r.id_mensaje], tipo=r.tipo, producto=r.producto,
                cantidad=float(r.cantidad), monto=float(r.monto) if r.monto else None)
    res = calc.resumen(led)
    assert (res["ventas"], res["cobros"], res["gastos"], res["flujo"]) == (1323.4, 21.0, 555.5, 788.9), res
    assert res["pendientes"] == 3 and res["dias"] == 7
    c = calc.estimar_cuota(led)
    assert c["cuota"] == 1010 and "no es un crédito aprobado" in c["texto"], c


def test_prompt_compacto():
    s = extractor.build_system()
    assert "no perdón" in s and len(s) < 9000, len(s)
    print("   prompt:", len(s), "caracteres (~", len(s) // 3, "tokens )")


def test_pipeline_con_llm_simulado():
    """Simula la respuesta de Groq para probar chat con repregunta y lote con dependencias."""
    respuestas = iter([
        {"resultados": [{"id": "C01", "filas": [{"tipo": "venta", "producto": "atún", "cantidad": 3, "monto": None}]}]},
        {"resultados": [{"id": "C02", "filas": [], "completar": [{"ref": "P1", "precio_unitario": 4}]}]},
        {"resultados": [
            {"id": "L1", "filas": [{"tipo": "fiado", "producto": "aceite", "cantidad": 1, "cliente": "Rosa", "monto": 11}]},
            {"id": "L2", "filas": [{"tipo": "cobro_fiado", "producto": "aceite", "cantidad": 1, "cliente": "Rosa", "monto": None}]},
            {"id": "L3", "filas": [{"tipo": "venta", "producto": "pan", "cantidad": 4, "monto": 999}]},
        ]},
    ])
    original = llm.chat_json
    llm.chat_json = lambda *a, **k: next(respuestas)
    try:
        led = Ledger()
        r1 = extractor.procesar([{"id": "C01", "dia": "lunes", "mensaje": "vendí 3 atunes"}], led, modo="chat")[0]
        assert r1["nuevas"][0]["requiere_confirmacion"] == "SI"
        r2 = extractor.procesar([{"id": "C02", "dia": "lunes", "mensaje": "a 4 soles"}], led, modo="chat")[0]
        assert r2["completadas"] and led.rows[0]["monto"] == 12.0
        lote = Ledger()
        msgs = [{"id": "L1", "dia": "lunes", "mensaje": "la señora Rosa se llevó 1 aceite fiado, está 11 soles"},
                {"id": "L2", "dia": "martes", "mensaje": "Rosa me pagó lo del aceite"},
                {"id": "L3", "dia": "martes", "mensaje": "vendí 4 panes"}]
        extractor.procesar(msgs, lote, modo="lote")
        assert [r["monto"] for r in lote.rows] == [11.0, 11.0, None]
    finally:
        llm.chat_json = original


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", nombre)
            except Exception as e:  # noqa: BLE001
                fallos += 1
                print("FALLA", nombre, "->", repr(e))
    sys.exit(1 if fallos else 0)

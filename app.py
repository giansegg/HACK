"""Agente de caja para Doña Rosa - MVP web (Streamlit + Groq)."""
import csv
import datetime as dt
import hashlib
import io

import pandas as pd
import streamlit as st

from core import calc, config, export, extractor, llm
from core.format import respuesta
from core.intents import intencion
from core.ledger import Ledger

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

st.set_page_config(page_title="Caja de Doña Rosa", page_icon="🧾", layout="centered")

ss = st.session_state
ss.setdefault("ledger", Ledger(config.DATA / "ledger.json"))
ss.setdefault("chat", [{"role": "assistant", "content": "¡Hola, Doña Rosa! Cuéntame tus ventas, gastos y fiados "
                        "con tu voz o escribiendo, y yo los anoto. Pregúntame también cuánto te queda o cuánto puedes pagar de cuota."}])
ss.setdefault("audio_n", 0)
ss.setdefault("msg_n", 0)
ss.setdefault("lote_df", None)
ledger: Ledger = ss.ledger

with st.sidebar:
    st.header("Ajustes")
    dia = st.selectbox("Día de hoy", DIAS, index=dt.datetime.now().weekday())
    if config.get_key():
        st.success("Groq conectado")
    else:
        st.error("Falta GROQ_API_KEY (archivo .env)")
    st.caption(f"Modelo: {config.MODEL}\n\nVoz: {config.STT_MODEL}")
    st.divider()
    if st.button("Cargar semana de ejemplo (sin IA)"):
        ledger.reset()
        dias = {m["id_mensaje"]: m["dia"] for m in extractor._leer("ejemplos_mensajes.csv")}
        for r in extractor._leer("ejemplos_respuestas.csv"):
            ledger.add(id_mensaje=r["id_mensaje"], dia=dias[r["id_mensaje"]], tipo=r["tipo"], producto=r["producto"],
                       cantidad=float(r["cantidad"]), monto=float(r["monto"]) if r["monto"] else None,
                       cliente=extractor.CLIENTES_EJEMPLO.get(r["id_mensaje"], ""))
        st.rerun()
    if st.button("Borrar todo y empezar de cero"):
        ledger.reset()
        ss.chat = ss.chat[:1]
        ss.lote_df = None
        st.rerun()


def manejar(texto, mostrar=None):
    """Un mensaje de Doña Rosa -> respuesta del agente."""
    ss.chat.append({"role": "user", "content": mostrar or texto})
    quiere = intencion(texto)
    if quiere == "cuota":
        out = calc.estimar_cuota(ledger)["texto"]
    elif quiere == "resumen":
        out = calc.resumen_texto(ledger)
    else:
        ss.msg_n += 1
        try:
            res = extractor.procesar([{"id": f"C{ss.msg_n:03d}", "dia": dia, "mensaje": texto}], ledger, modo="chat")[0]
            out = respuesta(res, ledger)
        except Exception as e:  # noqa: BLE001
            out = f"No pude procesar eso ahora. ¿Me lo repites en un momento? \n\n`{type(e).__name__}: {e}`"
    ss.chat.append({"role": "assistant", "content": out})


tab_chat, tab_libro, tab_lote = st.tabs(["💬 Hablar con el agente", "📒 Libro de caja", "📥 Procesar lote (CSV)"])

with tab_chat:
    for m in ss.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    audio = st.audio_input("🎤 Toca para grabar tu nota de voz", key=f"audio{ss.audio_n}")
    if audio is not None:
        with st.spinner("Escuchando..."):
            try:
                texto = llm.transcribir(audio.getvalue(), "nota.wav")
            except Exception as e:  # noqa: BLE001
                texto = ""
                ss.chat.append({"role": "assistant", "content": f"No pude escuchar el audio: `{type(e).__name__}: {e}`"})
        if texto:
            with st.spinner("Anotando..."):
                manejar(texto, mostrar=f"🎤 _{texto}_")
        ss.audio_n += 1
        st.rerun()

    entrada = st.chat_input("O escríbeme aquí: vendí 3 gaseosas a 2.50...")
    if entrada:
        with st.spinner("Anotando..."):
            manejar(entrada)
        st.rerun()

with tab_libro:
    r = calc.resumen(ledger)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas", calc.money(r["ventas"]))
    c2.metric("Cobros fiado", calc.money(r["cobros"]))
    c3.metric("Gastos", calc.money(r["gastos"]))
    c4.metric("Te queda", calc.money(r["flujo"]))
    if r["pendientes"]:
        st.warning(f"{r['pendientes']} movimiento(s) sin monto: no se cuentan hasta que Doña Rosa los confirme.")
    if ledger.rows:
        st.dataframe(export.a_df(ledger.rows), width="stretch", hide_index=True)
        ab = ledger.abiertos()
        if ab:
            st.subheader("Fiados por cobrar")
            st.dataframe(pd.DataFrame([{"cliente": e["cliente"], "producto": e["producto"],
                                        "debe": "sin monto" if e["restante"] is None else f"S/ {e['restante']:.2f}"} for e in ab]),
                         width="stretch", hide_index=True)
        st.subheader("¿Cuánto puedo pagar de cuota al mes?")
        st.markdown(calc.estimar_cuota(ledger)["texto"])
    else:
        st.info("Todavía no hay movimientos. Habla con el agente o carga la semana de ejemplo.")

with tab_lote:
    st.write("Sube el `set_oculto.csv` (columnas `id_mensaje,dia,mensaje`) y descarga el resultado en el formato de entrega.")
    equipo = st.text_input("Nombre del equipo", "equipo")
    subido = st.file_uploader("CSV de mensajes", type="csv")
    usar_ej = st.checkbox("Usar los 30 ejemplos del kit (para probar)")
    if st.button("Procesar lote", type="primary") and (subido or usar_ej):
        if subido:
            filas = list(csv.DictReader(io.StringIO(subido.getvalue().decode("utf-8-sig"))))
            msgs = [{"id": f["id_mensaje"], "dia": f.get("dia", ""), "mensaje": f["mensaje"]} for f in filas]
        else:
            msgs = [{"id": m["id_mensaje"], "dia": m["dia"], "mensaje": m["mensaje"]} for m in extractor._leer("ejemplos_mensajes.csv")]
        nuevo = Ledger()
        barra = st.progress(0.0, text="Procesando...")
        try:
            extractor.procesar(msgs, nuevo, modo="lote", progreso=lambda i, n: barra.progress(i / n, text=f"{i}/{n} mensajes"),
                               excluir=[m["id"] for m in msgs] if usar_ej else ())
            ledger.reset()
            for row in nuevo.rows:
                row.pop("uid", None)
                ledger.add(**row)
            ss.lote_df = export.a_df(ledger.rows)
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo procesar: {type(e).__name__}: {e}")
    if ss.lote_df is not None:
        st.dataframe(ss.lote_df, width="stretch", hide_index=True)
        st.download_button("⬇️ Descargar resultados", export.a_csv_bytes(ledger.rows),
                           file_name=f"resultados_{equipo}.csv", mime="text/csv")

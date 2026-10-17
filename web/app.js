"use strict";
const $ = (s) => document.querySelector(s);
const SVG_OK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const SALUDO = "Hola, Doña Rosa. Cuéntame lo que vendiste, compraste o fiaste, con tu voz o escribiendo, y yo lo anoto.\n\nTambién puedes preguntarme cuánto te queda o cuánto puedes pagar de cuota.";
const MAX_SEG = 90;

/* ---------- utilidades ---------- */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rich = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
const parrafos = (s) => String(s).split(/\n{2,}/).map((p) => `<p>${rich(p)}</p>`).join("");
const money = (x) => "S/ " + Number(x).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } },
};
let sesion = store.get("sesion");
if (!sesion) {
  sesion = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9-]/g, "");
  store.set("sesion", sesion);
}
let aviso_t;
function avisar(txt) {
  const a = $("#aviso");
  a.textContent = txt; a.hidden = false;
  clearTimeout(aviso_t); aviso_t = setTimeout(() => (a.hidden = true), 4500);
}
async function api(ruta, opts = {}) {
  const r = await fetch(ruta, { ...opts, headers: { "x-sesion": sesion, ...(opts.headers || {}) } });
  if (!r.ok) {
    let m = "Algo salió mal. Inténtalo otra vez.";
    try { m = (await r.json()).error || m; } catch { /* sin cuerpo */ }
    throw new Error(m);
  }
  return r;
}

/* ---------- vistas ---------- */
$("#fecha").textContent = new Date().toLocaleDateString("es-PE", { weekday: "long", day: "numeric", month: "long" });
function vista(v) {
  for (const b of document.querySelectorAll(".seg button")) b.setAttribute("aria-selected", String(b.dataset.vista === v));
  $("#v-chat").hidden = v !== "chat";
  $("#v-caja").hidden = v !== "caja";
  $("#dock").hidden = v !== "chat";
  $("#screen").scrollTo({ top: 0 });
  if (v === "chat") scrollAbajo();
}
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => vista(b.dataset.vista)));

/* ---------- conversación ---------- */
let historial = [];
try { historial = JSON.parse(store.get("chat") || "[]"); } catch { historial = []; }
if (!historial.length) historial = [{ de: "agente", lineas: [{ tipo: "texto", texto: SALUDO }] }];

function htmlMsg(m) {
  if (m.de === "yo") return `<div class="msg yo">${m.voz ? '<span class="via">Nota de voz</span>' : ""}${esc(m.texto)}</div>`;
  const filas = m.lineas.map((l) => {
    if (l.tipo === "texto") return parrafos(l.texto);
    if (l.tipo === "ok") return `<div class="fila ok">${SVG_OK}<span>${esc(l.texto)}</span></div>`;
    if (l.tipo === "falta") return `<div class="fila falta"><span class="pto"></span><span>${esc(l.texto)}</span></div>`;
    if (l.tipo === "pregunta") return `<div class="pregunta">${esc(l.texto)}</div>`;
    return `<div class="fila info"><span>${esc(l.texto)}</span></div>`;
  });
  return `<div class="msg agente">${filas.join("")}</div>`;
}
function pintarChat(extra = "") {
  $("#mensajes").innerHTML = historial.map(htmlMsg).join("") + extra;
  scrollAbajo();
}
function scrollAbajo() { requestAnimationFrame(() => { const sc = $("#screen"); sc.scrollTo({ top: sc.scrollHeight, behavior: "smooth" }); }); }

/* ---------- marco de teléfono: se ajusta a la altura de la ventana ---------- */
function ajustar() {
  const d = $("#device");
  d.style.transform = innerWidth <= 600 ? "" : `scale(${Math.min(1, (innerHeight - 24) / 868)})`;
}
addEventListener("resize", ajustar); ajustar();
function reloj() { $("#hora").textContent = new Date().toLocaleTimeString("es-PE", { hour: "numeric", minute: "2-digit", hour12: false }); }
reloj(); setInterval(reloj, 30000);
function guardar() { store.set("chat", JSON.stringify(historial.slice(-40))); }

let ocupado = false;
async function enviarTexto(texto, voz = false) {
  texto = texto.trim();
  if (!texto || ocupado) return;
  ocupado = true;
  historial.push({ de: "yo", texto, voz });
  pintarChat('<div class="msg agente"><span class="escribiendo"><i></i><i></i><i></i></span></div>');
  try {
    const r = await (await api("/api/chat", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ texto }) })).json();
    historial.push({ de: "agente", lineas: r.lineas });
    caja = r;
  } catch (e) {
    historial.push({ de: "agente", lineas: [{ tipo: "info", texto: "No pude anotar eso ahora mismo. Inténtalo de nuevo en un momento." }] });
  }
  ocupado = false;
  guardar(); pintarChat(); pintarCaja();
}

$("#form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("#texto").value;
  $("#texto").value = "";
  enviarTexto(t);
});
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => enviarTexto(c.dataset.q)));

/* ---------- voz: grabar, cancelar, enviar ---------- */
let rec = null; // { stream, mr, trozos, ctx, timer, raf, t0, cancelado }
let abort = null;
const paneles = { normal: $("#d-normal"), grabando: $("#d-grabando"), proceso: $("#d-proceso") };
function panel(n) { for (const k in paneles) paneles[k].hidden = k !== n; $("#chips").hidden = n !== "normal"; }

async function empezar() {
  if (ocupado) return;
  if (!navigator.mediaDevices || !window.MediaRecorder) { avisar("Este navegador no puede grabar. Puedes escribirme el mensaje."); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch { avisar("No tengo permiso para usar el micrófono. Actívalo en el navegador o escríbeme el mensaje."); return; }
  const mr = new MediaRecorder(stream);
  rec = { stream, mr, trozos: [], cancelado: false, t0: Date.now() };
  mr.ondataavailable = (e) => e.data.size && rec && rec.trozos.push(e.data);
  mr.onstop = terminar;
  mr.start();
  // medidor de nivel
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const an = ctx.createAnalyser(); an.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(an);
    rec.ctx = ctx;
    const datos = new Uint8Array(an.frequencyBinCount), cv = $("#nivel"), g = cv.getContext("2d");
    const dibujar = () => {
      if (!rec) return;
      an.getByteTimeDomainData(datos);
      let m = 0; for (const v of datos) m = Math.max(m, Math.abs(v - 128));
      rec.hist = (rec.hist || []).concat(m / 128).slice(-40);
      g.clearRect(0, 0, cv.width, cv.height);
      g.fillStyle = getComputedStyle(document.documentElement).getPropertyValue("--verde");
      rec.hist.forEach((v, i) => { const h = Math.max(6, v * cv.height * 1.6); g.fillRect(i * 8, (cv.height - h) / 2, 4, h); });
      rec.raf = requestAnimationFrame(dibujar);
    };
    dibujar();
  } catch { /* sin medidor */ }
  $("#tiempo").textContent = "0:00";
  rec.timer = setInterval(() => {
    const s = Math.floor((Date.now() - rec.t0) / 1000);
    $("#tiempo").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    if (s >= MAX_SEG) pararYEnviar();
  }, 250);
  panel("grabando");
}
function liberar() {
  if (!rec) return;
  clearInterval(rec.timer); cancelAnimationFrame(rec.raf);
  rec.stream.getTracks().forEach((t) => t.stop());
  if (rec.ctx) rec.ctx.close().catch(() => {});
}
function cancelarGrabacion() {
  if (!rec) return;
  rec.cancelado = true;
  if (rec.mr.state !== "inactive") rec.mr.stop();
  liberar(); rec = null;
  panel("normal");
}
function pararYEnviar() { if (rec && rec.mr.state !== "inactive") rec.mr.stop(); }

async function terminar() {
  const r = rec; liberar(); rec = null;
  if (!r || r.cancelado) return;
  if (Date.now() - r.t0 < 700) { panel("normal"); avisar("Fue muy corto. Toca el botón y cuéntame un poco más."); return; }
  panel("proceso");
  abort = new AbortController();
  try {
    const wav = await aWav(new Blob(r.trozos, { type: r.mr.mimeType }));
    const res = await (await api("/api/voz", { method: "POST", headers: { "content-type": "audio/wav" }, body: wav, signal: abort.signal })).json();
    abort = null;
    panel("normal");
    if (!res.texto) { avisar("No te escuché bien. ¿Me lo repites más cerca del micrófono?"); return; }
    await enviarTexto(res.texto, true);
  } catch (e) {
    abort = null; panel("normal");
    if (e.name !== "AbortError") avisar("No pude escucharte bien. Inténtalo otra vez o escríbeme el mensaje.");
  }
}
$("#btn-hablar").addEventListener("click", empezar);
$("#btn-cancelar").addEventListener("click", cancelarGrabacion);
$("#btn-enviar").addEventListener("click", pararYEnviar);
$("#btn-abortar").addEventListener("click", () => { if (abort) abort.abort(); panel("normal"); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && rec) cancelarGrabacion(); });

/* Convierte lo grabado a WAV mono de 16 kHz: lo entienden todos los navegadores y el servidor. */
async function aWav(blob) {
  const buf = await blob.arrayBuffer();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const audio = await new Promise((ok, no) => ctx.decodeAudioData(buf, ok, no));
  ctx.close().catch(() => {});
  const N = Math.ceil(audio.duration * 16000);
  const off = new OfflineAudioContext(1, N, 16000);
  const src = off.createBufferSource(); src.buffer = audio; src.connect(off.destination); src.start();
  const pcm = (await off.startRendering()).getChannelData(0);
  const out = new DataView(new ArrayBuffer(44 + N * 2));
  const w = (o, s) => [...s].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  w(0, "RIFF"); out.setUint32(4, 36 + N * 2, true); w(8, "WAVEfmt "); out.setUint32(16, 16, true); out.setUint16(20, 1, true);
  out.setUint16(22, 1, true); out.setUint32(24, 16000, true); out.setUint32(28, 32000, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
  w(36, "data"); out.setUint32(40, N * 2, true);
  for (let i = 0; i < N; i++) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 0x7fff, true);
  return out.buffer;
}

/* ---------- mi caja ---------- */
let caja = null;
const ETQ = { venta: "Venta", gasto: "Gasto", fiado: "Fiado", cobro_fiado: "Cobro de fiado" };
function filaMov(m) {
  const cls = m.monto == null ? "falta" : { venta: "entra", cobro_fiado: "entra", gasto: "sale", fiado: "neutro" }[m.tipo];
  const signo = m.monto == null ? "" : { venta: "+ ", cobro_fiado: "+ ", gasto: "− ", fiado: "" }[m.tipo];
  const txt = m.monto == null ? "falta el monto" : signo + money(m.monto);
  const sub = [ETQ[m.tipo], m.cliente, m.dia].filter(Boolean).join(" · ");
  return `<div class="mov"><div class="q"><b>${esc(m.cantidad)} ${esc(m.producto)}</b><small>${esc(sub)}</small></div><div class="m ${cls}">${txt}</div></div>`;
}

/* ---------- gráficas ---------- */
const ABR = { lunes: "Lun", martes: "Mar", "miércoles": "Mié", jueves: "Jue", viernes: "Vie", "sábado": "Sáb", domingo: "Dom" };
const corto = (n) => (n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(".0", "") + " mil" : String(Math.round(n)));
function graficaSemana(dias) {
  const con = dias.filter((d) => d.entro || d.salio);
  if (!con.length) return "";
  const W = 340, H = 170, base = 140, izq = 4, ancho = (W - izq * 2) / 7;
  const max = Math.max(...dias.map((d) => Math.max(d.entro, d.salio)), 1);
  const alto = (v) => Math.max(v > 0 ? 3 : 0, (v / max) * (base - 22));
  const mejor = con.reduce((a, b) => (b.entro > a.entro ? b : a));
  let g = `<line class="eje" x1="0" x2="${W}" y1="${base}" y2="${base}"/>`;
  dias.forEach((d, i) => {
    const x = izq + i * ancho, cx = x + ancho / 2, bw = 12;
    const e = alto(d.entro), sl = alto(d.salio);
    g += `<rect x="${cx - bw - 1}" y="${base - e}" width="${bw}" height="${e}" rx="3" fill="#1F6B45"/>`;
    g += `<rect x="${cx + 1}" y="${base - sl}" width="${bw}" height="${sl}" rx="3" fill="#B9564A"/>`;
    const es = d === mejor;
    if (es) g += `<text class="fuerte" x="${cx}" y="${base - e - 6}" text-anchor="middle">${corto(d.entro)}</text>`;
    g += `<text class="${es ? "fuerte" : ""}" x="${cx}" y="${base + 18}" text-anchor="middle">${ABR[d.dia]}</text>`;
  });
  const dato = mejor.entro ? `Tu mejor día fue el <b>${esc(mejor.dia)}</b>: entraron <b>${money(mejor.entro)}</b>.` : "";
  return `<h2>Tu semana</h2><div class="graf"><p class="dato">${dato}</p>
    <svg class="barras" viewBox="0 0 ${W} ${H}" role="img" aria-label="Entradas y salidas por día">${g}</svg>
    <div class="leyenda"><span><i style="background:#1F6B45"></i>Entró</span><span><i style="background:#B9564A"></i>Salió</span></div></div>`;
}
function topBarras(titulo, lista, clase, frase) {
  if (!lista.length) return "";
  const max = lista[0].monto || 1, total = lista.reduce((a, b) => a + b.monto, 0);
  const filas = lista.map((x) => `<div><div class="l"><b>${esc(x.nombre)}</b><span>${money(x.monto)}</span></div><div class="p"><i style="width:${Math.max(4, (x.monto / max) * 100)}%"></i></div></div>`).join("");
  return `<h2>${titulo}</h2><div class="graf"><p class="dato">${frase(lista[0], total)}</p><div class="top5 ${clase}">${filas}</div></div>`;
}
const graficasHtml = (g) =>
  graficaSemana(g.dias) +
  topBarras("Lo que más vendes", g.ventas, "venta", (t, tot) => `<b>${esc(t.nombre)}</b> es lo que más te deja: ${Math.round((t.monto / tot) * 100)}% de lo mostrado.`) +
  topBarras("En qué gastas", g.gastos, "gasto", (t, tot) => `Tu mayor gasto es <b>${esc(t.nombre)}</b>: ${Math.round((t.monto / tot) * 100)}% de lo mostrado.`);
function pintarCaja() {
  const el = $("#caja");
  if (!caja) { el.innerHTML = ""; return; }
  const r = caja.resumen;
  let h = "";
  if (!caja.movimientos.length) {
    h += '<div class="vacio"><b>Todavía no hay nada anotado</b>Ve a Conversación y cuéntame tu primera venta.</div>';
  } else {
    h += `<div class="queda"><small>Te queda</small><strong>${money(r.flujo)}</strong><span>ventas y cobros menos gastos</span></div>`;
    h += `<div class="dos"><div class="cifra entra"><small>Entró</small><b>${money(r.entro)}</b></div><div class="cifra sale"><small>Salió</small><b>${money(r.gastos)}</b></div></div>`;
    if (r.pendientes) h += `<p style="color:var(--ambar)">Hay ${r.pendientes} anotación(es) sin monto. No las cuento hasta que me digas cuánto fue.</p>`;
    if (caja.fiados.length) {
      h += "<h2>Te deben</h2><div class='lista'>" + caja.fiados.map((f) =>
        `<div class="mov"><div class="q"><b>${esc(f.cliente || "Cliente")}</b><small>${esc(f.producto)}</small></div><div class="m neutro">${f.debe == null ? "falta el monto" : money(f.debe)}</div></div>`).join("") + "</div>";
    }
    h += graficasHtml(caja.graficas);
    const partes = caja.cuota.texto.split(/\n{2,}/);
    const legal = partes.pop();
    h += "<h2>¿Cuánto puedo pagar de cuota?</h2><div class='cuota'>";
    if (caja.cuota.valor > 0) h += `<p class="grande">${money(caja.cuota.valor)}</p><p class="etq">cuota sugerida al mes</p>`;
    h += partes.map((p) => `<p>${rich(p)}</p>`).join("") + `<p class="legal">${esc(legal)}</p></div>`;
    h += "<h2>Lo que has anotado</h2><div class='lista'>" + caja.movimientos.map(filaMov).join("") + "</div>";
  }
  h += `<details class="mas"><summary>Más opciones</summary><div class="btns">
      <button id="b-ejemplo" type="button">Cargar semana de ejemplo</button>
      <button id="b-reset" type="button">Borrar todo y empezar de cero</button>
      <label class="btn">Procesar CSV<input id="b-lote" type="file" accept=".csv" hidden></label></div>
      <small>${caja.ia && caja.ia.length ? "IA conectada: " + esc(caja.ia.join(", ")) : "Sin clave de IA configurada"}</small></details>`;
  el.innerHTML = h;
  $("#b-ejemplo").onclick = () => accion("/api/ejemplo", "Semana de ejemplo cargada.");
  $("#b-reset").onclick = () => { if (confirm("¿Borrar todo lo anotado?")) accion("/api/reset", "Listo, empezamos de cero.", true); };
  $("#b-lote").onchange = lote;
}
async function accion(ruta, msg, limpiarChat) {
  try {
    caja = { ...caja, ...(await (await api(ruta, { method: "POST" })).json()) };
    if (limpiarChat) { historial = historial.slice(0, 1); guardar(); pintarChat(); }
    pintarCaja(); avisar(msg);
  } catch (e) { avisar(e.message); }
}
async function lote(e) {
  const f = e.target.files[0]; if (!f) return;
  avisar("Procesando el archivo…");
  try {
    const r = await api("/api/lote", { method: "POST", headers: { "content-type": "text/csv" }, body: await f.text() });
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "resultados_equipo.csv"; a.click();
    caja = { ...caja, ...(await (await api("/api/estado")).json()) }; pintarCaja(); avisar("Listo, se descargó el resultado.");
  } catch (err) { avisar(err.message); }
}

/* ---------- inicio ---------- */
pintarChat();
api("/api/estado").then((r) => r.json()).then((d) => { caja = d; pintarCaja(); }).catch(() => avisar("No me pude conectar. Revisa tu internet."));

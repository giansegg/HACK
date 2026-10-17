"use strict";
/* Mi Caja: chat estilo WhatsApp + dashboard del libro de caja. Sin dependencias. */

const $ = (s, r = document) => r.querySelector(s);
const DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"];
const CORTO = { lunes: "Lun", martes: "Mar", "miércoles": "Mié", jueves: "Jue", viernes: "Vie", "sábado": "Sáb", domingo: "Dom" };
const C1 = "#2a78d6", C2 = "#eb6834", C3 = "#6250d6"; // entró · salió · fiado (paleta validada)
const TIPOS = {
  venta: { label: "Venta", color: C1, signo: "+", clase: "pos" },
  cobro_fiado: { label: "Cobro de fiado", color: C1, signo: "+", clase: "pos" },
  gasto: { label: "Gasto", color: C2, signo: "−", clase: "neg" },
  fiado: { label: "Fiado", color: C3, signo: "", clase: "neu" },
};
const SALUDO = [
  "¡Hola, Doña Rosa! 👋 Soy **Mi Caja**.",
  "Cuéntame lo que vendiste, gastaste o fiaste, escribiendo o con una nota de voz 🎤, y yo lo anoto en tu libro.",
  "También puedes preguntarme _«¿cuánto me queda?»_ o _«¿cuánto puedo pagar de cuota al mes?»_",
];
const REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;

const sleep = (ms) => new Promise((r) => setTimeout(r, REDUCIDO ? 0 : ms));
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^\w])_(.+?)_(?=[^\w]|$)/g, "$1<i>$2</i>").replace(/\n/g, "<br>");
const money = (n) => "S/ " + Number(n || 0).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cant = (c) => (Number.isInteger(+c) ? String(+c) : String(c));
const hora = () => new Date().toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit", hour12: false });
const fmtDur = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

async function api(url, body, method = "POST") {
  const opt = { method };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(url, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  return data;
}

/* ================================================================ estado general */
let libro = null;
let vista = "chat";
let pendientesBadge = 0;

function diaActual() { return $("#dia").value; }

/* ================================================================ pestañas */
function moverIndicador() {
  const b = document.querySelector(".tab.activo"), ind = $(".tab-ind");
  if (!b) return;
  ind.style.left = b.offsetLeft + "px";
  ind.style.width = b.offsetWidth + "px";
}
function setVista(v) {
  vista = v;
  document.querySelectorAll(".tab").forEach((b) => {
    const on = b.dataset.vista === v;
    b.classList.toggle("activo", on);
    b.setAttribute("aria-selected", on);
  });
  $("#vista-chat").classList.toggle("activa", v === "chat");
  $("#vista-dash").classList.toggle("activa", v === "dash");
  if (v === "dash") { pendientesBadge = 0; $("#badge").hidden = true; }
  moverIndicador();
  if (v === "dash") {
    renderDash(true);
  } else {
    bajarChat();
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* ================================================================ VENTANA 1: chat */
const chat = $("#chat"), lista = $("#mensajes"), entrada = $("#entrada"), fab = $("#fab");
let msgs = store.get("micaja.chat", null);
const audios = new Map(); // id -> objectURL (solo en esta sesión)

function guardarChat() { store.set("micaja.chat", msgs.slice(-120)); }
function bajarChat() {
  requestAnimationFrame(() => { chat.scrollTop = chat.scrollHeight; });
  setTimeout(() => { chat.scrollTop = chat.scrollHeight; }, 460);
}
function estadoHeader(txt, vivo = false) { const e = $("#estado"); e.textContent = txt; e.classList.toggle("vivo", vivo); }

const TICKS = '<svg class="ticks" viewBox="0 0 16 11"><path class="t1" d="M1 6.2 3.9 9.1 9.6 2"/><path class="t2" d="M6.6 8.3 7.4 9.1 13.6 2"/></svg>';
const RELOJ = '<svg class="reloj-ico" viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.6"/><path d="M6 3.4V6l1.8 1.1"/></svg>';
const PLAY = '<svg viewBox="0 0 24 24"><path d="M8 5.1v13.8L19 12 8 5.1Z"/></svg>';
const PAUSA = '<svg viewBox="0 0 24 24"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>';

function metaHTML(m) {
  const marca = m.de === "yo" ? (m.st === "enviando" ? RELOJ : TICKS) : "";
  return `<span class="meta">${m.hora}${marca}</span>`;
}

function contenidoHTML(m) {
  if (m.tipo === "voz") {
    const barras = (m.ondas || []).map((v) => `<i style="height:${Math.round(4 + v * 24)}px"></i>`).join("");
    const t = m.texto ? `<div class="transcripcion">📝 ${esc(m.texto)}</div>` : `<div class="transcripcion cargando">Transcribiendo…</div>`;
    return `<div class="voz"><button class="play" aria-label="Reproducir" ${audios.has(m.id) ? "" : "disabled"}>${PLAY}</button>
      <div class="ondas">${barras}</div><div class="mic-av"><svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-3.3 0-8 1.7-8 5v1h16v-1c0-3.3-4.7-5-8-5Z"/></svg></div></div>
      <div class="voz-dur">${fmtDur(m.dur || 0)}</div>${t}`;
  }
  return md(m.texto);
}

function pintar(m, animar = true) {
  const prev = lista.lastElementChild;
  const el = document.createElement("div");
  el.className = `msg ${m.de === "yo" ? "out" : "in"}`;
  if (!prev || prev.dataset.de !== m.de) el.classList.add("first");
  if (!animar) el.style.animation = "none";
  el.dataset.de = m.de;
  el.dataset.id = m.id;
  if (m.st) el.dataset.st = m.st;
  el.innerHTML = contenidoHTML(m) + metaHTML(m);
  lista.appendChild(el);
  if (m.tipo === "voz") conectarVoz(el, m);
  bajarChat();
  return el;
}

function agregar(m) {
  const msg = { id: Date.now() + Math.random().toString(16).slice(2, 6), hora: hora(), tipo: "texto", ...m };
  msgs.push(msg);
  guardarChat();
  pintar(msg);
  return msg;
}

function setSt(m, st) {
  m.st = st;
  const el = lista.querySelector(`[data-id="${m.id}"]`);
  if (!el) return;
  el.dataset.st = st;
  el.querySelector(".meta").outerHTML = metaHTML(m);
  guardarChat();
}

let escribiendoEl = null;
function mostrarEscribiendo() {
  if (escribiendoEl) return;
  escribiendoEl = document.createElement("div");
  escribiendoEl.className = "msg in first";
  escribiendoEl.innerHTML = '<div class="escribiendo"><i></i><i></i><i></i></div>';
  lista.appendChild(escribiendoEl);
  estadoHeader("escribiendo…", true);
  bajarChat();
}
function ocultarEscribiendo() { escribiendoEl?.remove(); escribiendoEl = null; }

async function botDice(burbujas, movs = []) {
  for (let i = 0; i < burbujas.length; i++) {
    if (i > 0) { mostrarEscribiendo(); await sleep(Math.min(1300, 380 + burbujas[i].length * 12)); }
    ocultarEscribiendo();
    agregar({ de: "bot", texto: burbujas[i] });
    await sleep(140);
  }
  ocultarEscribiendo();
  estadoHeader("en línea");
  if (movs.length) volarChips(movs);
}

async function ciclo(m, promesa) {
  await sleep(280); setSt(m, "enviado");
  await sleep(380); setSt(m, "entregado");
  await sleep(320); setSt(m, "leido");
  mostrarEscribiendo();
  let r;
  try { r = await promesa; } catch {
    r = { respuestas: ["No me pude conectar con el servidor 😅 ¿Está prendido?"], movimientos: [] };
  }
  await sleep(420);
  return r;
}

async function enviarTexto(texto) {
  texto = texto.trim();
  if (!texto) return;
  entrada.value = "";
  fab.classList.remove("enviar");
  const m = agregar({ de: "yo", texto, st: "enviando" });
  const r = await ciclo(m, api("/api/mensaje", { texto, dia: diaActual() }));
  if (r.libro) recibirLibro(r.libro);
  if (r.error) console.warn("Mi Caja:", r.error);
  await botDice(r.respuestas || [], r.movimientos || []);
}

/* ---------------- notas de voz */
let rec = null;
async function iniciarGrabacion() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { toast("Este navegador no permite grabar audio aquí 😕"); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch { toast("Necesito permiso para usar el micrófono 🎤"); return; }
  const tipo = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((t) => MediaRecorder.isTypeSupported(t)) || "";
  const mr = new MediaRecorder(stream, tipo ? { mimeType: tipo } : undefined);
  const chunks = [];
  mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const an = ctx.createAnalyser();
  an.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(an);
  const buf = new Uint8Array(an.fftSize), niveles = [], t0 = performance.now(), wave = $("#recWave");
  wave.innerHTML = "";
  rec = { mr, stream, ctx, chunks, niveles, t0, tipo };
  mr.start(250);
  $("#composer").hidden = true;
  $("#recbar").hidden = false;
  estadoHeader("grabando audio…", true);
  rec.timer = setInterval(() => {
    an.getByteTimeDomainData(buf);
    let s = 0;
    for (const v of buf) { const x = (v - 128) / 128; s += x * x; }
    const nivel = Math.min(1, Math.sqrt(s / buf.length) * 5);
    niveles.push(nivel);
    const i = document.createElement("i");
    i.style.height = 4 + nivel * 28 + "px";
    wave.appendChild(i);
    if (wave.children.length > 90) wave.firstChild.remove();
    const seg = (performance.now() - t0) / 1000;
    $("#recTime").textContent = fmtDur(seg);
    if (seg > 60) terminarGrabacion(true);
  }, 100);
}

function terminarGrabacion(enviar) {
  if (!rec) return;
  const r = rec;
  rec = null;
  clearInterval(r.timer);
  const dur = (performance.now() - r.t0) / 1000;
  r.mr.onstop = () => {
    r.stream.getTracks().forEach((t) => t.stop());
    r.ctx.close?.();
    $("#recbar").hidden = true;
    $("#composer").hidden = false;
    estadoHeader("en línea");
    if (!enviar) return;
    if (dur < 0.7) { toast("Graba un poquito más 🎤"); return; }
    enviarAudio(new Blob(r.chunks, { type: r.tipo || "audio/webm" }), r.niveles, dur, r.tipo);
  };
  r.mr.stop();
}

function resumirOndas(niveles, n = 34) {
  if (!niveles.length) return Array(n).fill(0.2);
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = Math.floor((i * niveles.length) / n), b = Math.max(a + 1, Math.floor(((i + 1) * niveles.length) / n));
    const seg = niveles.slice(a, b);
    out.push(seg.reduce((x, y) => x + y, 0) / seg.length);
  }
  const max = Math.max(...out, 0.05);
  return out.map((v) => Math.max(0.12, v / max));
}

async function enviarAudio(blob, niveles, dur, tipo) {
  const ext = tipo.includes("mp4") ? "mp4" : tipo.includes("ogg") ? "ogg" : "webm";
  const id = Date.now() + "v";
  audios.set(id, URL.createObjectURL(blob));
  const m = agregar({ id, de: "yo", tipo: "voz", texto: "", ondas: resumirOndas(niveles), dur, st: "enviando" });
  const fd = new FormData();
  fd.append("archivo", blob, `nota.${ext}`);
  fd.append("dia", diaActual());
  const r = await ciclo(m, api("/api/audio", fd));
  m.texto = r.transcripcion || "";
  const t = lista.querySelector(`[data-id="${m.id}"] .transcripcion`);
  if (t) { t.classList.remove("cargando"); t.textContent = m.texto ? "📝 " + m.texto : "📝 (no se entendió el audio)"; }
  guardarChat();
  if (r.libro) recibirLibro(r.libro);
  if (r.error) console.warn("Mi Caja:", r.error);
  await botDice(r.respuestas || [], r.movimientos || []);
}

function conectarVoz(el, m) {
  const btn = el.querySelector(".play"), barras = [...el.querySelectorAll(".ondas i")];
  let audio = null;
  btn.addEventListener("click", () => {
    const url = audios.get(m.id);
    if (!url) return;
    if (!audio) {
      audio = new Audio(url);
      audio.addEventListener("timeupdate", () => {
        const p = audio.currentTime / (audio.duration && isFinite(audio.duration) ? audio.duration : m.dur || 1);
        barras.forEach((b, i) => b.classList.toggle("on", i / barras.length <= p));
      });
      audio.addEventListener("ended", () => { btn.innerHTML = PLAY; barras.forEach((b) => b.classList.remove("on")); });
    }
    if (audio.paused) { audio.play(); btn.innerHTML = PAUSA; } else { audio.pause(); btn.innerHTML = PLAY; }
  });
}

/* ---------------- chips que vuelan al dashboard */
function volarChips(movs) {
  const desde = $("#phone").getBoundingClientRect();
  const hacia = document.querySelector('.tab[data-vista="dash"]').getBoundingClientRect();
  movs.slice(0, 4).forEach((mv, i) => {
    const t = TIPOS[mv.tipo] || TIPOS.venta;
    const el = document.createElement("div");
    el.className = "vuela";
    el.innerHTML = `<i style="background:${t.color}"></i>${t.label} ${t.signo} ${money(mv.monto)}`;
    document.body.appendChild(el);
    const x0 = desde.left + desde.width / 2 - 70, y0 = desde.bottom - 170;
    const x1 = hacia.left + hacia.width / 2 - 40, y1 = hacia.top;
    const anim = el.animate([
      { transform: `translate(${x0}px, ${y0}px) scale(.6)`, opacity: 0 },
      { transform: `translate(${x0}px, ${y0 - 60}px) scale(1)`, opacity: 1, offset: 0.3 },
      { transform: `translate(${x1}px, ${y1}px) scale(.35)`, opacity: 0.3 },
    ], { duration: REDUCIDO ? 1 : 1400, delay: REDUCIDO ? 0 : i * 220, easing: "cubic-bezier(.55,0,.25,1)", fill: "both" });
    anim.onfinish = () => {
      el.remove();
      if (vista !== "dash") {
        pendientesBadge += 1;
        const b = $("#badge");
        b.textContent = pendientesBadge;
        b.hidden = false;
        b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop");
        moverIndicador();
      }
    };
  });
}

/* ---------------- composer */
entrada.addEventListener("input", () => fab.classList.toggle("enviar", entrada.value.trim().length > 0));
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); enviarTexto(entrada.value); });
fab.addEventListener("click", () => { if (entrada.value.trim()) enviarTexto(entrada.value); else iniciarGrabacion(); });
$("#recSend").addEventListener("click", () => terminarGrabacion(true));
$("#recCancel").addEventListener("click", () => terminarGrabacion(false));
$("#btnEmoji").addEventListener("click", () => { entrada.value += "👍"; entrada.dispatchEvent(new Event("input")); entrada.focus(); });
$("#sugerencias").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) enviarTexto(b.textContent); });

/* ---------------- celular grande (390x844 ampliado); se puede bajar con el scroll para verlo entero */
const ZOOM_CELULAR = 1.18;
function ajustarCelular() {
  const phone = $("#phone");
  if (innerWidth <= 520) { phone.style.zoom = ""; return; }
  phone.style.zoom = Math.min(ZOOM_CELULAR, (innerWidth - 32) / 414).toFixed(3);
}
addEventListener("resize", ajustarCelular);
ajustarCelular();

setInterval(() => { $("#reloj").textContent = hora(); }, 15000);
$("#reloj").textContent = hora();

/* ================================================================ VENTANA 2: dashboard */
const tip = $("#tip");
function mostrarTip(html, e) {
  tip.innerHTML = html;
  tip.classList.add("on");
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(innerWidth - w - 8, e.clientX + 14) + "px";
  tip.style.top = Math.max(8, e.clientY - h - 12) + "px";
}
function ocultarTip() { tip.classList.remove("on"); }

function contar(el, hasta, fmt = money) {
  const desde = parseFloat(el.dataset.v || "0");
  el.dataset.v = hasta;
  if (REDUCIDO) { el.textContent = fmt(hasta); return; }
  const t0 = performance.now(), dur = 900;
  const paso = (t) => {
    const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    el.textContent = fmt(desde + (hasta - desde) * e);
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}

function recibirLibro(l) {
  libro = l;
  if (vista === "dash") renderDash(false);
}

function renderDash(animar) {
  if (!libro) return;
  $(".dash").classList.toggle("quieto", !animar);
  const r = libro.resumen, c = libro.conteo, hay = libro.rows.length > 0;

  // 1. ¿Cómo vas esta semana?
  contar($("#heroVal"), r.flujo);
  $("#formula").innerHTML = hay
    ? `<span>Entró ${money(r.ventas + r.cobros)}</span><em>−</em><span>Salió ${money(r.gastos)}</span>`
    : "<span>Todavía no hay nada anotado</span>";
  const debenTxt = libro.fiados.length
    ? libro.fiados.slice(0, 2).map((f) => `${esc(f.cliente || "Cliente")}: ${f.debe == null ? "sin monto" : money(f.debe)}`).join(" · ")
    : "Nadie te debe 🎉";
  const tres = [
    { ic: "💰", lbl: "Entró", v: r.ventas + r.cobros, sub: `${c.venta || 0} venta(s) y ${c.cobro_fiado || 0} cobro(s) de fiado`, dot: C1 },
    { ic: "🧾", lbl: "Salió", v: r.gastos, sub: `${c.gasto || 0} gasto(s)`, dot: C2 },
    { ic: "⏳", lbl: "Te deben", v: libro.por_cobrar, sub: debenTxt, dot: C3 },
  ];
  $("#tres").innerHTML = tres.map((t, i) => `<div class="stat" style="animation-delay:${80 + i * 70}ms"><div class="ic">${t.ic}</div>
    <div><div class="lbl"><span class="dot" style="background:${t.dot}"></span>${t.lbl}</div><div class="val" data-i="${i}">S/ 0.00</div>
    <div class="sub">${t.sub}</div></div></div>`).join("");
  tres.forEach((t, i) => contar($(`#tres .val[data-i="${i}"]`), t.v));
  const conDatos = libro.por_dia.some((d) => d.ventas || d.gastos);
  $("#cardDias").hidden = !conDatos;
  if (conDatos) chartDias($("#chartDias"), libro.por_dia);

  // 2. Cuota
  renderCuota();

  // 3. Movimientos
  $("#alerta").innerHTML = r.pendientes ? `<div class="alerta"><span class="ic">⚠️</span><p><b>${r.pendientes} movimiento(s) sin monto.</b>
    No se cuentan hasta que le digas a Mi Caja cuánto fue.</p><button class="btn" id="completar">Completar en el chat</button></div>` : "";
  $("#completar")?.addEventListener("click", () => { setVista("chat"); entrada.focus(); });
  renderRegistro();
  $("#btnCsv").href = `/api/resultados.csv?equipo=${encodeURIComponent($("#equipo").value || "equipo")}`;
}

function niceMax(v) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}
const compacto = (v) => (v >= 1000 ? +(v / 1000).toFixed(1) + "K" : String(+v.toFixed(1)));
function barraRedonda(x, y, w, h, r = 4) {
  if (h <= 0) return "";
  r = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

function chartDias(el, datos) {
  const hay = datos.some((d) => d.ventas || d.gastos);
  if (!hay) { el.innerHTML = '<div class="vacio">Cuando anotes ventas y gastos, aquí verás cada día de la semana.</div>'; return; }
  const W = Math.max(320, el.clientWidth || 600), H = 250, m = { t: 22, r: 6, b: 28, l: 48 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = niceMax(Math.max(...datos.flatMap((d) => [d.ventas, d.gastos]), 1));
  const banda = iw / datos.length, bw = Math.min(24, (banda * 0.62 - 2) / 2);
  const y = (v) => m.t + ih - (v / max) * ih;
  let s = "";
  for (let k = 0; k <= 4; k++) {
    const v = (max / 4) * k, yy = y(v);
    s += `<line class="${k ? "grid-l" : "base-l"}" x1="${m.l}" x2="${W - m.r}" y1="${yy}" y2="${yy}"/>`;
    s += `<text x="${m.l - 8}" y="${yy + 4}" text-anchor="end">${k ? "S/ " + compacto(v) : "0"}</text>`;
  }
  const iMax = datos.reduce((b, d, i) => (d.ventas > datos[b].ventas ? i : b), 0);
  datos.forEach((d, i) => {
    const x0 = m.l + i * banda + banda / 2 - (bw * 2 + 2) / 2;
    s += `<g class="grupo" data-i="${i}">`;
    s += `<path class="bar" fill="${C1}" style="animation-delay:${i * 70}ms" d="${barraRedonda(x0, y(d.ventas), bw, ih + m.t - y(d.ventas))}"/>`;
    s += `<path class="bar" fill="${C2}" style="animation-delay:${i * 70 + 40}ms" d="${barraRedonda(x0 + bw + 2, y(d.gastos), bw, ih + m.t - y(d.gastos))}"/>`;
    if (i === iMax && d.ventas) s += `<text x="${x0 + bw / 2}" y="${y(d.ventas) - 7}" text-anchor="middle" style="fill:#111b21;font-weight:700">${money(d.ventas).replace(".00", "")}</text>`;
    s += `<text x="${m.l + i * banda + banda / 2}" y="${H - 8}" text-anchor="middle">${CORTO[d.dia] || d.dia}</text>`;
    s += `<rect class="hit" x="${m.l + i * banda}" y="${m.t}" width="${banda}" height="${ih}" fill="transparent"/></g>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="Lo que entró y salió cada día de la semana">${s}</svg>`;
  el.querySelectorAll(".grupo").forEach((g) => {
    const d = datos[+g.dataset.i];
    g.addEventListener("mousemove", (e) => {
      el.querySelectorAll(".grupo").forEach((o) => o.classList.toggle("apagado", o !== g));
      mostrarTip(`<b style="text-transform:capitalize">${d.dia}</b><div class="row"><i style="background:${C1}"></i>Entró <b>${money(d.ventas)}</b></div>
        <div class="row"><i style="background:${C2}"></i>Salió <b>${money(d.gastos)}</b></div>`, e);
    });
    g.addEventListener("mouseleave", () => { el.querySelectorAll(".grupo").forEach((o) => o.classList.remove("apagado")); ocultarTip(); });
  });
}

function renderCuota() {
  const el = $("#cuotaCard"), q = libro.cuota, r = libro.resumen;
  if (!libro.rows.length) {
    el.innerHTML = '<div class="vacio">Cuando anotes lo que vendes y gastas, aquí te digo cuánto podrías pagar al mes.</div>';
    return;
  }
  const pct = Math.round(q.pct * 100);
  const poco = r.dias < 5 ? `<li>Solo hay ${r.dias} día(s) de datos: tómalo con calma <b>⚠️</b></li>` : "";
  el.innerHTML = `<div class="cuota-grid">
    <div>
      <div class="c-lbl">💡 Podrías pagar hasta</div>
      <div class="c-val"><span id="cuotaVal">S/ 0</span> <small>al mes</small></div>
      <div class="meter"><i id="meterFill"></i></div>
      <div class="meter-l"><span>Es el ${pct}% de lo que te queda al mes</span><span>${money(q.mensual)}</span></div>
    </div>
    <ol class="pasos">
      <li style="animation-delay:.1s">Te queda en la semana <b>${money(r.flujo)}</b></li>
      <li style="animation-delay:.2s">En un mes (÷ ${q.dias} días × 30) <b>${money(q.mensual)}</b></li>
      ${poco}
      <li style="animation-delay:.3s">Cuota: el ${pct}%, redondeado hacia abajo <b>${money(q.cuota)}</b></li>
    </ol>
  </div>
  <div class="aviso-legal">Es solo una estimación para ayudarte a organizarte. Mi Caja no aprueba ni promete créditos.</div>`;
  contar($("#cuotaVal"), q.cuota, (v) => money(v).replace(".00", ""));
  requestAnimationFrame(() => requestAnimationFrame(() => { $("#meterFill").style.width = (r.flujo > 0 ? pct : 0) + "%"; }));
}

/* ---------------- registro */
const FILTROS = [
  ["todo", "Todo", () => true],
  ["venta", "Ventas", (x) => x.tipo === "venta"],
  ["gasto", "Gastos", (x) => x.tipo === "gasto"],
  ["fiado", "Fiados", (x) => x.tipo === "fiado" || x.tipo === "cobro_fiado"],
  ["falta", "Sin monto", (x) => x.monto == null],
];
let filtro = "todo";
const BORRAR = '<svg viewBox="0 0 24 24"><path d="M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12ZM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4Z"/></svg>';

function renderRegistro() {
  const rows = libro.rows;
  $(".reg-tools").hidden = !rows.length;
  $("#filtros").innerHTML = FILTROS.map(([k, lbl, f]) => `<button class="chip ${k === filtro ? "on" : ""}" data-f="${k}">${lbl}<span class="n">${rows.filter(f).length}</span></button>`).join("");
  const q = $("#buscar").value.trim().toLowerCase();
  const pasa = FILTROS.find((f) => f[0] === filtro)[2];
  const visibles = rows.slice().reverse().filter(pasa).filter((x) => !q || `${x.producto} ${x.cliente} ${x.dia}`.toLowerCase().includes(q));
  $("#regCount").textContent = rows.length ? `${visibles.length} de ${rows.length} movimiento(s) · lo más reciente primero` : "";
  if (!rows.length) {
    $("#tabla").innerHTML = '<div class="vacio">Todavía no hay movimientos.<br>Cuéntale a Mi Caja lo que vendiste hoy y aparecerá aquí.<br><button class="btn" id="vacioChat">💬 Ir al chat</button></div>';
    $("#vacioChat").addEventListener("click", () => setVista("chat"));
    return;
  }
  const th = '<div class="fila th" role="row"><span>Día</span><span>Tipo</span><span>Detalle</span><span style="text-align:right">Monto</span><span></span></div>';
  $("#tabla").innerHTML = th + (visibles.length ? visibles.map((x, i) => {
    const t = TIPOS[x.tipo] || TIPOS.venta;
    const monto = x.monto == null ? '<span class="monto falta">⚠️ falta el monto</span>' : `<span class="monto ${t.clase}">${t.signo} ${money(x.monto)}</span>`;
    const quien = x.cliente ? `<small>${esc(x.cliente)}</small>` : "";
    return `<div class="fila" role="row" data-uid="${x.uid}" style="animation-delay:${Math.min(i, 12) * 35}ms">
      <span class="dia">${esc(x.dia || "—")}</span><span class="tipo"><i style="background:${t.color}"></i>${t.label}</span>
      <span class="det"><b>${cant(x.cantidad)}</b> ${esc(x.producto)}${quien}</span>${monto}
      <button class="borrar" data-uid="${x.uid}" aria-label="Eliminar ${esc(x.producto)}" title="Eliminar">${BORRAR}</button></div>`;
  }).join("") : '<div class="vacio">No hay movimientos con ese filtro.</div>');
}

$("#filtros").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (!b) return; filtro = b.dataset.f; renderRegistro(); });
$("#buscar").addEventListener("input", () => renderRegistro());
$("#tabla").addEventListener("click", async (e) => {
  const b = e.target.closest(".borrar");
  if (!b || b.disabled) return;
  b.disabled = true;
  const fila = b.closest(".fila");
  fila.classList.add("sale");
  await sleep(380);
  try {
    const r = await api(`/api/registro/${b.dataset.uid}`, undefined, "DELETE");
    libro = r.libro;
    renderDash(false);
    toast(`Eliminado: ${r.borrado.producto}`, "Deshacer", async () => { const x = await api("/api/registro", r.borrado); libro = x.libro; renderDash(false); });
  } catch (err) { fila.classList.remove("sale"); toast("No se pudo eliminar: " + err.message); }
});
$("#irChat").addEventListener("click", () => setVista("chat"));

/* ================================================================ herramientas del equipo */
function abrirTools(abrir) {
  $("#drawer").classList.toggle("abierto", abrir);
  $("#drawer").setAttribute("aria-hidden", !abrir);
  $("#scrim").hidden = !abrir;
}
$("#btnTools").addEventListener("click", () => abrirTools(true));
$("#cerrarTools").addEventListener("click", () => abrirTools(false));
$("#scrim").addEventListener("click", () => abrirTools(false));
addEventListener("keydown", (e) => { if (e.key === "Escape") abrirTools(false); });

(function dias() {
  const hoy = DIAS[(new Date().getDay() + 6) % 7];
  $("#dia").innerHTML = DIAS.map((d) => `<option value="${d}">${d}</option>`).join("");
  $("#dia").value = store.get("micaja.dia", hoy);
  $("#dia").addEventListener("change", () => store.set("micaja.dia", $("#dia").value));
})();

$("#btnEjemplo").addEventListener("click", async () => {
  const r = await api("/api/ejemplo");
  recibirLibro(r.libro);
  toast("Semana de ejemplo cargada ✅", "Ver dashboard", () => { abrirTools(false); setVista("dash"); });
});
$("#btnReset").addEventListener("click", async () => {
  if (!confirm("¿Borrar todos los movimientos y el chat?")) return;
  const r = await api("/api/reset");
  recibirLibro(r.libro);
  msgs = [];
  lista.innerHTML = "";
  guardarChat();
  saludar();
  toast("Listo, empezamos de cero 🧹");
});
$("#archivo").addEventListener("change", () => { $("#archivoNombre").textContent = $("#archivo").files[0]?.name || "Elegir CSV (id_mensaje,dia,mensaje)"; });
$("#btnLote").addEventListener("click", async () => {
  const f = $("#archivo").files[0], fd = new FormData(), btn = $("#btnLote"), res = $("#loteRes");
  if (!f && !$("#usarEj").checked) { res.textContent = "Elige un CSV o marca la opción de ejemplos."; return; }
  if (f) fd.append("archivo", f);
  fd.append("usar_ejemplos", $("#usarEj").checked ? "true" : "false");
  btn.disabled = true;
  btn.textContent = "Procesando… (puede tardar un minuto)";
  res.textContent = "";
  try {
    const r = await api("/api/lote", fd);
    recibirLibro(r.libro);
    const eq = encodeURIComponent($("#equipo").value || "equipo");
    res.innerHTML = `✅ ${r.mensajes} mensajes → ${r.filas} filas. <a href="/api/resultados.csv?equipo=${eq}">Descargar resultados_${esc($("#equipo").value || "equipo")}.csv</a>`;
  } catch (err) { res.textContent = "❌ " + err.message; }
  btn.disabled = false;
  btn.textContent = "Procesar lote";
});
$("#equipo").addEventListener("input", () => { $("#btnCsv").href = `/api/resultados.csv?equipo=${encodeURIComponent($("#equipo").value || "equipo")}`; });

/* ================================================================ toast */
let toastT = null;
function toast(texto, accion, fn) {
  const t = $("#toast");
  t.innerHTML = `<span>${esc(texto)}</span>${accion ? `<button>${esc(accion)}</button>` : ""}`;
  if (accion) t.querySelector("button").addEventListener("click", () => { t.classList.remove("on"); fn?.(); });
  t.classList.add("on");
  clearTimeout(toastT);
  toastT = setTimeout(() => t.classList.remove("on"), accion ? 7000 : 3500);
}

/* ================================================================ inicio */
async function saludar() {
  await sleep(700);
  for (const t of SALUDO) {
    mostrarEscribiendo();
    await sleep(650 + t.length * 8);
    ocultarEscribiendo();
    agregar({ de: "bot", texto: t });
  }
  estadoHeader("en línea");
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setVista(b.dataset.vista)));
addEventListener("resize", () => { moverIndicador(); if (vista === "dash") { clearTimeout(window._rz); window._rz = setTimeout(() => renderDash(false), 150); } });
requestAnimationFrame(moverIndicador);

(async function iniciar() {
  let e = null;
  try { e = await api("/api/estado", undefined, "GET"); } catch { /* servidor apagado */ }
  if (e && store.get("micaja.sesion", null) !== e.sesion) { msgs = []; store.set("micaja.sesion", e.sesion); guardarChat(); }
  if (Array.isArray(msgs) && msgs.some((m) => m.de === "yo")) {
    msgs.forEach((m) => { if (m.st === "enviando") m.st = "leido"; pintar(m, false); });
  } else {
    msgs = [];
    saludar();
  }
  try { libro = await api("/api/libro", undefined, "GET"); } catch { /* el servidor responde luego */ }
  const box = $("#estadoGroq");
  if (e) {
    box.className = "tool estado " + (e.groq ? "ok" : "mal");
    box.textContent = e.groq ? `✅ Groq conectado · ${e.modelo} · voz: ${e.voz}` : "❌ Falta GROQ_API_KEY en el archivo .env";
  } else box.textContent = "No se pudo comprobar la conexión.";
})();

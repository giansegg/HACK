"""Clientes de IA: transcripción de voz y extracción en JSON.

Proveedores gratuitos con respaldo automático: Gemini (principal, entiende audio), Groq y xAI Grok.
Todo va por HTTP simple (requests); si un modelo está saturado o sin cuota, se pasa al siguiente."""
import base64
import json
import re
import time

import requests

from . import config

STT_PROMPT = ("Transcribe fielmente esta nota de voz en español de una bodeguera peruana. "
              "Vocabulario frecuente: vendí, fié, fiado, cobré, pagué, soles, lucas, gaseosa, Inca Kola, leche Gloria, "
              "aceite Primor, pan, huevos, atún, arroz, azúcar, don Pepe. Escribe los montos con cifras (2.50, 12). "
              "Devuelve SOLO la transcripción, sin comentarios.")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1"
XAI_URL = "https://api.x.ai/v1"

REINTENTABLE = {429, 500, 502, 503, 504}
ultimo_proveedor = None  # para mostrar quién respondió


class LLMError(RuntimeError):
    pass


def _post(url, intentos=2, **kw):
    """POST con reintentos cortos ante saturación (429/5xx) o red caída."""
    espera, err = 1.5, None
    for i in range(intentos):
        try:
            r = requests.post(url, timeout=60, **kw)
        except requests.RequestException as e:
            err = LLMError(f"sin conexión: {type(e).__name__}")
        else:
            if r.status_code == 200:
                return r
            err = LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
            if r.status_code not in REINTENTABLE:
                raise err
            try:
                espera = min(float(r.headers.get("retry-after", espera)), 20)
            except ValueError:
                pass
        if i < intentos - 1:
            time.sleep(espera)
            espera *= 2
    raise err


def parse_json(texto):
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"\{.*\}", texto or "", re.S)
        if not m:
            raise ValueError(f"El modelo no devolvió JSON: {texto!r}")
        return json.loads(m.group(0))


# ---------- Gemini ----------

def _gemini(model, parts, json_mode, max_tokens):
    key = config.get_secret("GEMINI_API_KEY")
    gen = {"temperature": 0, "maxOutputTokens": max_tokens}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    r = _post(GEMINI_URL.format(model=model), headers={"x-goog-api-key": key, "Content-Type": "application/json"},
              json={"contents": [{"role": "user", "parts": parts}], "generationConfig": gen})
    cand = (r.json().get("candidates") or [{}])[0]
    texto = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    if not texto.strip():
        raise LLMError(f"respuesta vacía ({cand.get('finishReason')})")
    return texto


# ---------- Groq / xAI (API compatible con OpenAI) ----------

def _openai(base, key, model, system, user, max_tokens, extras=None):
    body = {"model": model, "temperature": 0, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    body.update(extras or {})
    r = _post(base + "/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body)
    return r.json()["choices"][0]["message"]["content"] or ""


def _cadena():
    """[(proveedor, modelo, función(system,user,max_tokens)->texto)] en orden de preferencia."""
    cad = []
    for p in config.proveedores_activos():
        if p == "gemini":
            for m in config.GEMINI_MODELS:
                cad.append((p, m, lambda s, u, mt, m=m: _gemini(m, [{"text": s + "\n\n" + u}], True, mt)))
        elif p == "groq":
            key = config.get_secret("GROQ_API_KEY")
            for m in config.GROQ_MODELS:
                ex = {"reasoning_effort": config.GROQ_REASONING} if "gpt-oss" in m else None
                cad.append((p, m, lambda s, u, mt, m=m, ex=ex: _openai(GROQ_URL, key, m, s, u, mt, ex)))
        elif p == "xai":
            key = config.get_secret("XAI_API_KEY")
            for m in config.XAI_MODELS:
                cad.append((p, m, lambda s, u, mt, m=m: _openai(XAI_URL, key, m, s, u, mt)))
    return cad


def chat_json(system, user, max_tokens=4000):
    """Pide JSON al primer modelo disponible de la cadena."""
    global ultimo_proveedor
    cad = _cadena()
    if not cad:
        raise RuntimeError("Falta una clave de IA (GEMINI_API_KEY, GROQ_API_KEY o XAI_API_KEY) en .env o en los secretos de Streamlit.")
    errores = []
    for prov, model, fn in cad:
        try:
            out = parse_json(fn(system, user, max_tokens))
            ultimo_proveedor = f"{prov}:{model}"
            return out
        except (LLMError, ValueError, KeyError) as e:
            errores.append(f"{prov}/{model}: {e}")
    raise LLMError("Ningún modelo respondió. " + " | ".join(errores))


def _mime(filename):
    return "audio/mpeg" if filename.endswith(".mp3") else "audio/webm" if filename.endswith(".webm") else "audio/wav"


def transcribir(audio_bytes, filename="audio.wav"):
    """Voz -> texto. Gemini entiende audio directo; si falla, Whisper de Groq."""
    errores = []
    if config.get_secret("GEMINI_API_KEY") and "gemini" in config.PROVIDERS:
        parts = [{"text": STT_PROMPT},
                 {"inlineData": {"mimeType": _mime(filename), "data": base64.b64encode(audio_bytes).decode()}}]
        for m in config.GEMINI_STT_MODELS:
            try:
                return _gemini(m, parts, False, 1000).strip()
            except LLMError as e:
                errores.append(f"gemini/{m}: {e}")
    if config.get_secret("GROQ_API_KEY"):
        try:
            r = _post(GROQ_URL + "/audio/transcriptions", headers={"Authorization": f"Bearer {config.get_secret('GROQ_API_KEY')}"},
                      files={"file": (filename, audio_bytes)},
                      data={"model": config.GROQ_STT_MODEL, "language": "es", "temperature": "0", "prompt": STT_PROMPT[:220]})
            return (r.json().get("text") or "").strip()
        except LLMError as e:
            errores.append(f"groq/whisper: {e}")
    raise LLMError("No pude transcribir el audio. " + " | ".join(errores) if errores else "No hay clave para transcribir audio.")

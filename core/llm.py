"""Cliente de Groq: transcripción (Whisper) y extracción en JSON, con reintentos por límite de uso."""
import json
import re
import time

from . import config

STT_PROMPT = ("Notas de voz de una bodeguera peruana: vendí, fié, fiado, cobré, pagué, soles, "
              "gaseosa, Inca Kola, leche Gloria, aceite Primor, pan, huevos, atún, don Pepe.")

_client = None
_client_key = None


def get_client():
    global _client, _client_key
    key = config.get_key()
    if not key:
        raise RuntimeError("Falta GROQ_API_KEY (ponla en el archivo .env o en los secretos de Streamlit).")
    if _client is None or key != _client_key:
        from groq import Groq

        _client, _client_key = Groq(api_key=key), key
    return _client


def _con_reintentos(fn, intentos=3):
    import groq

    espera, ultimo = 2.0, None
    for _ in range(intentos):
        try:
            return fn()
        except groq.RateLimitError as e:
            ultimo = e
            ra = None
            try:
                ra = float(e.response.headers.get("retry-after"))
            except Exception:
                pass
            time.sleep(min(ra if ra is not None else espera, 60) + 0.5)
            espera *= 2
        except (groq.APIConnectionError, groq.InternalServerError) as e:
            ultimo = e
            time.sleep(espera)
            espera *= 2
    raise ultimo


def transcribir(audio_bytes, filename="audio.wav"):
    c = get_client()
    r = _con_reintentos(lambda: c.audio.transcriptions.create(
        file=(filename, audio_bytes), model=config.STT_MODEL, language="es",
        temperature=0.0, response_format="json", prompt=STT_PROMPT))
    return (getattr(r, "text", "") or "").strip()


def _extras(model):
    if "gpt-oss" in model:
        return {"reasoning_effort": config.REASONING}
    if "qwen3" in model:
        return {"reasoning_effort": "none"}
    return None


def parse_json(texto):
    try:
        return json.loads(texto)
    except Exception:
        m = re.search(r"\{.*\}", texto or "", re.S)
        if not m:
            raise ValueError(f"El modelo no devolvió JSON: {texto!r}")
        return json.loads(m.group(0))


def chat_json(system, user, max_tokens=2500):
    """Llama al modelo principal y, si se agota su límite o falla, al de respaldo."""
    import groq

    c = get_client()
    ultimo = None
    for model, intentos in ((config.MODEL, 3), (config.FALLBACK_MODEL, 4)):
        def llamar(extras):
            kw = dict(model=model, temperature=0, max_tokens=max_tokens,
                      response_format={"type": "json_object"},
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            if extras:
                kw["extra_body"] = extras
            return c.chat.completions.create(**kw)

        try:
            try:
                resp = _con_reintentos(lambda: llamar(_extras(model)), intentos)
            except groq.BadRequestError:
                resp = _con_reintentos(lambda: llamar(None), intentos)
            return parse_json(resp.choices[0].message.content)
        except (groq.RateLimitError, groq.APIStatusError, groq.APIConnectionError, ValueError) as e:
            ultimo = e
    raise ultimo

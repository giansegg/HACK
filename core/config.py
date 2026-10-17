import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
load_dotenv(BASE / ".env")

# Modelos por proveedor, del principal al de respaldo. Se prueban en orden.
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-2.5-flash").split(",") if m.strip()]
GEMINI_STT_MODELS = [m.strip() for m in os.getenv("GEMINI_STT_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash").split(",") if m.strip()]
GROQ_MODELS = [m.strip() for m in os.getenv("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
GROQ_REASONING = os.getenv("GROQ_REASONING", "low")
XAI_MODELS = [m.strip() for m in os.getenv("XAI_MODELS", "grok-4-fast-non-reasoning,grok-3-mini").split(",") if m.strip()]
# Orden en que se usan los proveedores (los que no tengan clave se saltan).
PROVIDERS = [p.strip() for p in os.getenv("LLM_PROVIDERS", "gemini,groq,xai").split(",") if p.strip()]

N_SHOTS_SIMILARES = int(os.getenv("N_SHOTS_SIMILARES", "4"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
CUOTA_PCT = float(os.getenv("CUOTA_PCT", "0.30"))


def get_secret(name):
    """Variable de entorno (.env) o secreto de Streamlit Cloud."""
    val = os.getenv(name)
    if val:
        return val
    try:
        import streamlit as st

        return st.secrets.get(name)
    except Exception:
        return None


def get_key():
    """Hay al menos un proveedor con clave."""
    return any(get_secret(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY"))


def proveedores_activos():
    clave = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "xai": "XAI_API_KEY"}
    return [p for p in PROVIDERS if clave.get(p) and get_secret(clave[p])]

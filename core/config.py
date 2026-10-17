import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
load_dotenv(BASE / ".env")

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3")
REASONING = os.getenv("GROQ_REASONING", "low")

N_SHOTS_SIMILARES = int(os.getenv("N_SHOTS_SIMILARES", "4"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
CUOTA_PCT = float(os.getenv("CUOTA_PCT", "0.30"))


def get_key():
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    try:
        import streamlit as st

        return st.secrets.get("GROQ_API_KEY")
    except Exception:
        return None

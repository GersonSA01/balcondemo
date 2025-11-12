# app/services/config.py
"""Configuración central y cliente LLM."""
import os
from pathlib import Path
import os
from langchain_google_genai import ChatGoogleGenerativeAI


def _load_google_api_key() -> str:
    """Carga la API key de Google Gemini desde variables de entorno o .env."""
    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        try:
            from django.conf import settings
            key = getattr(settings, "GOOGLE_API_KEY", None)
        except Exception:
            pass
    if not key:
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parents[2] / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                key = os.getenv("GOOGLE_API_KEY")
        except Exception:
            pass
    if not key:
        raise RuntimeError(
            "GOOGLE_API_KEY no está configurada. Define la variable de entorno GOOGLE_API_KEY"
        )
    return key


# API Key
GOOGLE_API_KEY = _load_google_api_key()

# Cliente LLM Gemini
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # Modelo experimental más rápido
    temperature=0,
    api_key=GOOGLE_API_KEY,
    max_retries=0,  # dejamos los reintentos al guard
)

# Umbrales de confianza para answerability (V2 optimizados)
TAU_NORMA = 0.72    # Si >= ⇒ respondemos con alta confianza (aumentado para early-exit)
TAU_MIN = 0.50      # Si >= 0.50 ⇒ responde aunque sea con baja confianza, SOLO deriva si < 0.50 (aumentado para menos handoffs)
TAU_SKIP_CONFIRM = 0.90  # Si >= 0.90 ⇒ saltar confirmación y ir directo a retrieval

# Feature Flags para capas de Query Understanding
FEATURE_FLAGS = {
    "query_planner": True,          # Planner con subconsultas
    "rrf_fusion": True,             # Reciprocal Rank Fusion (híbrido)
    "fuzzy_safety_net": False,      # RapidFuzz safety net (OFF para velocidad)
    "entity_router": True,          # Router por entidades (EPUNEMI, SGA, etc.)
    "neutral_response": False,      # Respuesta sin "Según..." (desactivado por ahora)
    "cross_encoder_rerank": False,  # Cross-encoder reranking (OFF: agrega 3-5 segundos)
}

# Directorios
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# PrivateGPT API Configuration
PRIVATEGPT_API_URL = os.getenv("PRIVATEGPT_API_URL", "http://localhost:8001")

# Rate-limit guard para evitar 429 (respeta 'retry in N seconds' si está presente)
import re
import asyncio
from google.api_core.exceptions import ResourceExhausted


# Feature flags / modo free tier
LLM_FREE_TIER = os.getenv("LLM_FREE_TIER", "1") == "1"
ALLOW_RELATED_LLM = not LLM_FREE_TIER
ALLOW_HANDOFF_LLM = True

# Token bucket simple (9 RPM) + semáforo global (1 a la vez)
from threading import Lock
import time
_bucket_lock = Lock()
_bucket_last_reset = time.monotonic()
_bucket_tokens = 9  # por debajo de 10 RPM para margen


def _maybe_refill_bucket():
    global _bucket_last_reset, _bucket_tokens
    now = time.monotonic()
    if now - _bucket_last_reset >= 60:
        _bucket_tokens = 9
        _bucket_last_reset = now


async def _take_token_async():
    global _bucket_tokens
    while True:
        with _bucket_lock:
            _maybe_refill_bucket()
            if _bucket_tokens > 0:
                _bucket_tokens -= 1
                return
            # calcular espera restante
            wait_s = max(0.0, 60 - (time.monotonic() - _bucket_last_reset))
        await asyncio.sleep(wait_s + 0.01)


def _take_token_sync():
    global _bucket_tokens
    while True:
        with _bucket_lock:
            _maybe_refill_bucket()
            if _bucket_tokens > 0:
                _bucket_tokens -= 1
                return
            wait_s = max(0.0, 60 - (time.monotonic() - _bucket_last_reset))
        import time as _t
        _t.sleep(wait_s + 0.01)


def llm_budget_remaining() -> int:
    with _bucket_lock:
        _maybe_refill_bucket()
        return _bucket_tokens

def guarded_invoke(llm_client, msgs):
    try:
        _take_token_sync()
        return llm_client.invoke(msgs)
    except ResourceExhausted as e:
        m = re.search(r"retry in (\d+)", str(e).lower())
        wait_s = int(m.group(1)) + 1 if m else 60
        import time
        time.sleep(wait_s)
        return llm_client.invoke(msgs)

async def guarded_ainvoke(llm_client, msgs):
    try:
        await _take_token_async()
        return await llm_client.ainvoke(msgs)
    except ResourceExhausted as e:
        m = re.search(r"retry in (\d+)", str(e).lower())
        wait_s = int(m.group(1)) + 1 if m else 60
        await asyncio.sleep(wait_s)
        return await llm_client.ainvoke(msgs)


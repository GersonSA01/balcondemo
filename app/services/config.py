# app/services/config.py
"""Configuración central y cliente LLM."""
import os
from pathlib import Path
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
    max_retries=2,
)

# Umbrales de confianza para answerability (V2 optimizados)
TAU_NORMA = 0.72    # Si >= ⇒ respondemos con alta confianza (aumentado para early-exit)
TAU_EXPAND = 0.30   # Si entre 0.30 y 0.70 ⇒ intentamos expansión
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


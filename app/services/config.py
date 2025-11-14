# app/services/config.py
"""Configuración central y cliente LLM."""
import os
from pathlib import Path
from typing import Dict, Any
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
PRIVATEGPT_API_URL = os.getenv("PRIVATEGPT_API_URL", "http://localhost:8001")  # Volver a 8001 hasta que PrivateGPT se reinicie en 8002

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
    first_wait = True
    while True:
        with _bucket_lock:
            _maybe_refill_bucket()
            if _bucket_tokens > 0:
                tokens_before = _bucket_tokens
                _bucket_tokens -= 1
                if not first_wait:
                    print(f"✅ [Rate Limit] Token obtenido. Tokens restantes: {_bucket_tokens}")
                return
            wait_s = max(0.0, 60 - (time.monotonic() - _bucket_last_reset))
        
        if first_wait:
            print(f"⚠️ [Rate Limit] Límite de 9 RPM alcanzado. Tokens disponibles: 0")
            print(f"   Esperando {wait_s:.1f} segundos antes de la próxima llamada al LLM...")
            first_wait = False
        
        import time as _t
        _t.sleep(min(wait_s + 0.01, 1.0))  # Dormir máximo 1 segundo a la vez para mostrar progreso


def llm_budget_remaining() -> int:
    """Retorna la cantidad de tokens disponibles en el bucket."""
    with _bucket_lock:
        _maybe_refill_bucket()
        return _bucket_tokens

def get_rate_limit_status() -> Dict[str, Any]:
    """Retorna información detallada del estado del rate limiting."""
    with _bucket_lock:
        _maybe_refill_bucket()
        now = time.monotonic()
        elapsed = now - _bucket_last_reset
        remaining_in_bucket = max(0.0, 60 - elapsed)
        return {
            "tokens_available": _bucket_tokens,
            "tokens_max": 9,
            "elapsed_seconds": elapsed,
            "reset_in_seconds": remaining_in_bucket,
            "percentage_used": ((60 - remaining_in_bucket) / 60) * 100 if remaining_in_bucket > 0 else 0
        }

def guarded_invoke(llm_client, msgs, max_retries: int = 2):
    """
    Invoca el LLM con protección de rate limiting.
    
    Args:
        llm_client: Cliente del LLM
        msgs: Mensaje o prompt a enviar
        max_retries: Número máximo de reintentos después de error 429
    
    Returns:
        Respuesta del LLM
    """
    retry_count = 0
    
    while retry_count <= max_retries:
        # Mostrar tokens disponibles antes de tomar
        tokens_available = llm_budget_remaining()
        if tokens_available == 0:
            print(f"⚠️ [Rate Limit Guard] Sin tokens disponibles. Esperando...")
        else:
            if retry_count == 0:
                print(f"🔑 [Rate Limit Guard] Tokens disponibles: {tokens_available}/9")
            else:
                print(f"🔑 [Rate Limit Guard] Reintento {retry_count}/{max_retries}. Tokens disponibles: {tokens_available}/9")
        
        try:
            # Solo tomar token en el primer intento o si ya pasó tiempo suficiente
            if retry_count == 0:
                _take_token_sync()
            else:
                # En reintentos, verificar si tenemos tokens sin tomarlos todavía
                # porque ya los usamos en el primer intento
                tokens_available = llm_budget_remaining()
                if tokens_available == 0:
                    print(f"⚠️ [Rate Limit Guard] Sin tokens para reintento. Esperando...")
                    _take_token_sync()
                else:
                    # Usar un token del bucket para el reintento
                    _take_token_sync()
            
            print(f"⏳ [Rate Limit Guard] Llamando al LLM... (intento {retry_count + 1})")
            result = llm_client.invoke(msgs)
            tokens_remaining = llm_budget_remaining()
            print(f"✅ [Rate Limit Guard] LLM respondió exitosamente. Tokens restantes: {tokens_remaining}/9")
            return result
            
        except ResourceExhausted as e:
            retry_count += 1
            error_msg = str(e)
            print(f"❌ [Rate Limit Guard] ResourceExhausted (intento {retry_count}):")
            print(f"   Error: {error_msg[:200]}...")
            
            # Extraer tiempo de espera del error
            m = re.search(r"retry in (\d+(?:\.\d+)?)", error_msg.lower())
            wait_s = float(m.group(1)) + 1 if m else 60
            
            # Extraer información del límite si está disponible
            quota_match = re.search(r"limit:\s*(\d+)", error_msg.lower())
            limit = quota_match.group(1) if quota_match else "desconocido"
            
            if retry_count > max_retries:
                print(f"❌ [Rate Limit Guard] Se alcanzó el máximo de reintentos ({max_retries})")
                print(f"   Límite de la API: {limit} requests por minuto")
                print(f"   Por favor, espera unos momentos antes de intentar nuevamente.")
                raise RuntimeError(
                    f"Límite de cuota excedido (máximo {limit} requests/minuto). "
                    f"Por favor, espera unos momentos antes de intentar nuevamente."
                )
            
            print(f"⏳ [Rate Limit Guard] Esperando {wait_s:.1f} segundos según el error de la API...")
            print(f"   Límite de la API: {limit} requests por minuto")
            print(f"   Reintento {retry_count}/{max_retries} en {wait_s:.1f}s...")
            
            import time
            # Esperar en bloques para mostrar progreso
            waited = 0
            while waited < wait_s:
                sleep_time = min(1.0, wait_s - waited)
                time.sleep(sleep_time)
                waited += sleep_time
                if waited < wait_s:
                    remaining = wait_s - waited
                    print(f"   ⏳ Esperando... {remaining:.1f}s restantes")
            
            print(f"🔄 [Rate Limit Guard] Reintentando llamada al LLM...")
            
        except Exception as e:
            # Otros errores no relacionados con rate limiting
            print(f"❌ [Rate Limit Guard] Error inesperado: {type(e).__name__}: {str(e)}")
            raise
    
    # No debería llegar aquí, pero por si acaso
    raise RuntimeError("Error al invocar LLM después de múltiples intentos")

async def guarded_ainvoke(llm_client, msgs):
    try:
        await _take_token_async()
        return await llm_client.ainvoke(msgs)
    except ResourceExhausted as e:
        m = re.search(r"retry in (\d+)", str(e).lower())
        wait_s = int(m.group(1)) + 1 if m else 60
        await asyncio.sleep(wait_s)
        return await llm_client.ainvoke(msgs)


# Funciones de encriptación simple para IDs (simulación)
import base64

def encrypt(value):
    """Encripta un valor (ID) para simulación."""
    if value is None:
        return None
    try:
        # Convertir a string y codificar en base64
        encoded = base64.b64encode(str(value).encode()).decode()
        return encoded
    except Exception:
        return str(value)

def decrypt(encrypted_value):
    """Desencripta un valor encriptado."""
    if encrypted_value is None:
        return None
    try:
        # Decodificar desde base64
        decoded = base64.b64decode(encrypted_value.encode()).decode()
        # Intentar convertir a int si es posible
        try:
            return int(decoded)
        except ValueError:
            return decoded
    except Exception:
        # Si falla, intentar usar directamente como int
        try:
            return int(encrypted_value)
        except (ValueError, TypeError):
            return encrypted_value


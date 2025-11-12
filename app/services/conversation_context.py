# app/services/conversation_context.py
"""
Manejo de contexto conversacional para preguntas de seguimiento.
Solución industrial: usar LLM para enriquecer query con contexto.
"""
import json
from typing import List, Dict, Any, Optional
from .config import llm
from .config import guarded_invoke
import re


def build_conversation_summary(history: List[Dict[str, Any]], max_turns: int = 4) -> str:
    """
    Construye un resumen de los últimos turnos de conversación.
    Incluye más contexto para análisis semántico.
    
    Args:
        history: Historial completo de conversación
        max_turns: Número máximo de turnos a incluir (default: 4, aumentado para mejor contexto)
    
    Returns:
        Resumen de conversación en formato legible (con más contexto semántico)
    """
    if not history:
        return "No hay conversación previa."
    
    # Tomar últimos N turnos (pares usuario-bot) - más turnos para mejor análisis semántico
    recent = history[-max_turns*2:] if len(history) > max_turns*2 else history
    
    lines = []
    for msg in recent:
        role = msg.get("role") or msg.get("who")
        text = msg.get("content") or msg.get("text", "")
        
        if role in ("user", "student", "estudiante"):
            # Incluir preguntas completas (hasta 250 chars para mantener contexto semántico)
            lines.append(f"Usuario: {text[:250]}")
        elif role in ("bot", "assistant"):
            # Incluir más contexto de las respuestas del bot (hasta 350 chars)
            # El LLM necesita ver temas y detalles para análisis semántico
            text_short = text[:350] + "..." if len(text) > 350 else text
            lines.append(f"Bot: {text_short}")
    
    return "\n".join(lines)


PRONOUN_HINTS = re.compile(r"\b(eso|ese|esa|esto|así|alli|allí|ahí|en ese caso|también|lo mismo|aquello)\b", re.I)
FOLLOW_UP_HINTS = re.compile(r"\b(y|para|en|de|sobre|cuando|donde|como|que|cuál|cuáles)\s+(la|el|los|las|un|una|ese|esa|eso|este|esta|esto)\b", re.I)
LOCATION_HINTS = re.compile(r"\b(para|en|de)\s+(quito|machala|santo domingo|azogues|portoviejo|santa elena|sede|ciudad)\b", re.I)

def _heuristic_needs_context(user_text: str, history: List[Dict[str, Any]]):
    if not history or len(history) < 2:
        return False, "No hay conversación previa"
    t = (user_text or "").strip().lower()
    
    # Detectar pronombres/referencias
    if PRONOUN_HINTS.search(t):
        return True, "Pronombres/referencias detectadas"
    
    # Detectar preguntas de seguimiento que empiezan con "y", "para", etc.
    if FOLLOW_UP_HINTS.search(t):
        return True, "Pregunta de seguimiento detectada"
    
    # Detectar preguntas sobre ubicaciones/lugares específicos (ej: "para quito")
    if LOCATION_HINTS.search(t):
        return True, "Pregunta sobre ubicación específica"
    
    # Detectar preguntas cortas que pueden ser de seguimiento
    if len(t) <= 3:  # “sí”, “no”, “ok”
        return True, "Respuesta corta dependiente"
    
    # Detectar preguntas que empiezan con "y" (muy común en seguimientos)
    if t.startswith("y ") and len(t) > 3:
        return True, "Pregunta de seguimiento con 'y'"
    
    return False, "Pregunta auto-contenida"


def needs_context(user_text: str, conversation_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Usa LLM para detectar si la pregunta necesita contexto conversacional previo.
    Solución industrial sin keywords.
    
    Args:
        user_text: Texto del usuario
        conversation_history: Historial de conversación (opcional)
    
    Returns:
        {
            "needs_context": bool,
            "confidence": "high" | "medium" | "low",
            "reason": str
        }
    """
    # Si no hay historial, no puede necesitar contexto
    if not conversation_history or len(conversation_history) < 2:
        return {
            "needs_context": False,
            "confidence": "high",
            "reason": "No hay conversación previa"
        }
    
    # Heurística previa: solo filtrar casos OBVIOS donde NO hay contexto
    # (ej: "sí", "no", "ok" sin contexto previo, o primera pregunta de la conversación)
    # Para todo lo demás, dejar que el LLM haga análisis semántico
    flag, reason = _heuristic_needs_context(user_text, conversation_history or [])
    # Solo usar heurística para casos MUY obvios (respuestas de 1-2 palabras sin contexto claro)
    # Para el resto, SIEMPRE invocar LLM para análisis semántico
    if not flag and len(user_text.strip()) <= 2:
        # Solo filtrar respuestas muy cortas que claramente NO tienen contexto
        return {
            "needs_context": False,
            "confidence": "high",
            "reason": reason
        }
    # Para todo lo demás (preguntas normales), SIEMPRE analizar con LLM

    # Construir resumen breve de conversación
    context_summary = build_conversation_summary(conversation_history, max_turns=2)
    
    prompt = f"""Analiza SEMÁNTICAMENTE si esta pregunta necesita contexto de la conversación previa para ser entendida.

IMPORTANTE: Haz análisis SEMÁNTICO, NO solo búsqueda de keywords. Analiza el SIGNIFICADO y la RELACIÓN entre la pregunta y el contexto.

CONVERSACIÓN PREVIA:
{context_summary}

PREGUNTA ACTUAL:
"{user_text}"

ANÁLISIS SEMÁNTICO:
- INDEPENDIENTE: La pregunta tiene sentido completo por sí sola, sin referencias semánticas al contexto previo.
- DEPENDIENTE: La pregunta tiene una RELACIÓN SEMÁNTICA con el contexto, aunque no use palabras clave obvias.

Ejemplos de relaciones SEMÁNTICAS que requieren contexto:
- Contexto: "Exámenes finales: 24-29 noviembre"
  Pregunta: "y para quito?" → DEPENDIENTE (se refiere semánticamente a fechas de exámenes para Quito)
- Contexto: "Cambio de paralelo requiere documentos..."
  Pregunta: "qué documentos necesito?" → DEPENDIENTE (se refiere semánticamente a documentos para cambio de paralelo)
- Contexto: "Matriculación inicia en marzo"
  Pregunta: "cuándo es?" → DEPENDIENTE (se refiere semánticamente a fechas de matriculación)
- Contexto: "Asistencia mínima es 70%"
  Pregunta: "y si falto más?" → DEPENDIENTE (se refiere semánticamente a consecuencias de faltar más)

Ejemplos de preguntas INDEPENDIENTES (sin relación semántica con contexto):
- "¿Cuál es la asistencia mínima?" (pregunta completa y auto-contenida)
- "¿Cómo cambio mi contraseña?" (pregunta completa sobre tema diferente)
- "Necesito información sobre becas" (solicitud completa sobre tema nuevo)

REGLAS:
1. Analiza el TEMA PRINCIPAL del contexto y si la pregunta se refiere a ese tema
2. No dependas solo de keywords como "y", "para", "también"
3. Detecta relaciones semánticas aunque no haya palabras clave obvias
4. Si la pregunta amplía, especifica o continúa el tema del contexto → DEPENDIENTE
5. Si la pregunta es sobre un tema completamente diferente → INDEPENDIENTE

Responde ESTRICTAMENTE en formato JSON:
{{
  "needs_context": true/false,
  "confidence": "high/medium/low",
  "reason": "explicación breve de la relación semántica detectada (o su ausencia)"
}}

JSON:"""

    try:
        response = guarded_invoke(llm, prompt).content.strip()
        
        # Limpiar markdown si existe
        if response.startswith("```json"):
            response = response.replace("```json", "").replace("```", "").strip()
        elif response.startswith("```"):
            response = response.replace("```", "").strip()
        
        result = json.loads(response)
        
        # Validar campos
        if "needs_context" not in result:
            result["needs_context"] = False
        if "confidence" not in result:
            result["confidence"] = "medium"
        if "reason" not in result:
            result["reason"] = "Evaluación automática"
        
        print(f"🧠 [Context Detection] needs={result['needs_context']}, confidence={result['confidence']}")
        print(f"   Reason: {result['reason']}")
        
        return result
        
    except Exception as e:
        print(f"⚠️ [Context Detection Error] {e}, asumiendo independiente")
        return {
            "needs_context": False,
            "confidence": "low",
            "reason": "Error en evaluación"
        }


def enrich_query_with_context(
    user_text: str,
    conversation_history: List[Dict[str, Any]]
) -> str:
    """
    Enriquece la query del usuario con contexto de la conversación previa.
    Usa LLM para resolver referencias y crear una query auto-contenida.
    
    Args:
        user_text: Query actual del usuario
        conversation_history: Historial de conversación
    
    Returns:
        Query enriquecida con contexto (auto-contenida)
    """
    # Evaluar si necesita contexto usando LLM (solo si heurística lo sugiere)
    context_check = needs_context(user_text, conversation_history)
    
    # Si no necesita contexto, retornar query original
    if not context_check["needs_context"]:
        print(f"🔵 [Context] Query independiente, no necesita enriquecimiento")
        print(f"   Reason: {context_check['reason']}")
        return user_text
    
    # Construir resumen de conversación
    context_summary = build_conversation_summary(conversation_history, max_turns=3)
    
    # Prompt para enriquecer query con contexto
    prompt = f"""Eres un asistente que reformula preguntas para hacerlas auto-contenidas.

CONVERSACIÓN PREVIA:
{context_summary}

PREGUNTA ACTUAL DEL USUARIO:
"{user_text}"

TAREA:
La pregunta actual puede tener referencias al contexto previo (pronombres, referencias, etc.).
Reformula la pregunta para que sea COMPLETA y AUTO-CONTENIDA, sin necesitar el contexto.

REGLAS:
1. Reemplaza pronombres ("eso", "esto") con lo que realmente significan del contexto
2. Reemplaza referencias ("lo anterior", "tu respuesta") con el tema específico
3. Si es una pregunta de seguimiento, incluye el tema de conversación
4. Mantén el mismo sentido e intención de la pregunta original
5. Si la pregunta ya es clara y auto-contenida, devuélvela sin cambios
6. Responde SOLO con la pregunta reformulada, sin explicaciones

PREGUNTA REFORMULADA:"""

    try:
        enriched_query = guarded_invoke(llm, prompt).content.strip()
        
        # Limpiar comillas si las agregó el LLM
        enriched_query = enriched_query.strip('"').strip("'").strip()
        
        print(f"🔄 [Context Enrichment]")
        print(f"   Original: {user_text}")
        print(f"   Enriquecida: {enriched_query}")
        
        return enriched_query
        
    except Exception as e:
        print(f"⚠️ [Context Error] {e}, usando query original")
        return user_text







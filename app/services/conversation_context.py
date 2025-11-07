# app/services/conversation_context.py
"""
Manejo de contexto conversacional para preguntas de seguimiento.
Solución industrial: usar LLM para enriquecer query con contexto.
"""
import json
from typing import List, Dict, Any, Optional
from .config import llm


def build_conversation_summary(history: List[Dict[str, Any]], max_turns: int = 3) -> str:
    """
    Construye un resumen de los últimos turnos de conversación.
    
    Args:
        history: Historial completo de conversación
        max_turns: Número máximo de turnos a incluir (default: 3)
    
    Returns:
        Resumen de conversación en formato legible
    """
    if not history:
        return "No hay conversación previa."
    
    # Tomar últimos N turnos (pares usuario-bot)
    recent = history[-max_turns*2:] if len(history) > max_turns*2 else history
    
    lines = []
    for msg in recent:
        role = msg.get("role") or msg.get("who")
        text = msg.get("content") or msg.get("text", "")
        
        if role in ("user", "student", "estudiante"):
            lines.append(f"Usuario: {text}")
        elif role in ("bot", "assistant"):
            # Limitar longitud de respuestas del bot en el resumen
            text_short = text[:200] + "..." if len(text) > 200 else text
            lines.append(f"Bot: {text_short}")
    
    return "\n".join(lines)


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
    
    # Construir resumen breve de conversación
    context_summary = build_conversation_summary(conversation_history, max_turns=2)
    
    prompt = f"""Analiza si esta pregunta necesita contexto de la conversación previa para ser entendida.

CONVERSACIÓN PREVIA:
{context_summary}

PREGUNTA ACTUAL:
"{user_text}"

Evalúa si la pregunta es:
- INDEPENDIENTE: Se entiende completamente por sí sola, sin necesitar contexto previo
- DEPENDIENTE: Tiene referencias, pronombres o conexiones que requieren el contexto previo para entenderse

Ejemplos de preguntas DEPENDIENTES:
- "¿Y si falto más?" (se refiere a algo mencionado antes)
- "¿Eso aplica también para...?" (usa pronombre "eso")
- "¿Pero en ese caso qué pasa?" (referencia a caso anterior)
- "¿También puedo...?" (continúa tema anterior)

Ejemplos de preguntas INDEPENDIENTES:
- "¿Cuál es la asistencia mínima?" (pregunta completa)
- "¿Cómo cambio mi contraseña?" (pregunta completa)
- "Necesito información sobre matrículas" (solicitud completa)

Responde ESTRICTAMENTE en formato JSON:
{{
  "needs_context": true/false,
  "confidence": "high/medium/low",
  "reason": "explicación breve de 1 línea"
}}

JSON:"""

    try:
        response = llm.invoke(prompt).content.strip()
        
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
    # Evaluar si necesita contexto usando LLM
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
        enriched_query = llm.invoke(prompt).content.strip()
        
        # Limpiar comillas si las agregó el LLM
        enriched_query = enriched_query.strip('"').strip("'").strip()
        
        print(f"🔄 [Context Enrichment]")
        print(f"   Original: {user_text}")
        print(f"   Enriquecida: {enriched_query}")
        
        return enriched_query
        
    except Exception as e:
        print(f"⚠️ [Context Error] {e}, usando query original")
        return user_text


def detect_follow_up_type(context_check: Dict[str, Any]) -> str:
    """
    Detecta el tipo de pregunta basándose en la evaluación de contexto.
    
    Args:
        context_check: Resultado de needs_context()
    
    Returns:
        "follow_up" | "independent"
    """
    if context_check["needs_context"]:
        return "follow_up"
    return "independent"


def should_use_conversational_mode(
    user_text: str,
    conversation_history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Determina si se debe activar el modo conversacional usando evaluación LLM.
    
    Args:
        user_text: Query del usuario
        conversation_history: Historial de conversación
    
    Returns:
        Resultado de needs_context() con evaluación completa
    """
    # Usar evaluación LLM para determinar si necesita contexto
    return needs_context(user_text, conversation_history)


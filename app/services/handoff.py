
from typing import Dict, List, Any, Optional
from .config import TAU_NORMA, TAU_MIN, llm
import json

# Intenciones críticas que requieren intervención humana
CRITICAL_INTENTS = {
    "cambio_de_paralelo",
    "cambio_de_curso",
    "anulacion_matricula",
    "cambio_de_carrera",
    "homologacion",
    "convalidacion",
    "sede_de_examen",
    "tramite_con_plazo",
    "problema_con_pagos",
    "rectificacion_calificacion",
    "apelacion",
    "queja_formal",
    "solicitud_de_baja",
    "retiro_semestre",
}

# Documentos requeridos por intención
REQUIRED_DOCS = {
    "justificar_inasistencia_medica": ["certificado_medico"],
    "cambio_de_paralelo": ["motivo", "paralelo_destino"],
    "anulacion_matricula": ["formulario", "identificacion"],
    "homologacion": ["certificado_notas", "programa_academico"],
    "convalidacion": ["certificado_notas", "programa_academico"],
    "rectificacion_calificacion": ["evidencia_error"],
}

# Categorías sensibles que requieren mayor certeza
SENSITIVE_CATEGORIES = {
    "Calificaciones",
    "Asistencia", 
    "Pagos",
    "Matriculación",
    "Financiero",
    "Becas",
}

SENSITIVE_SUBCATEGORIES = {
    "Cambio de paralelo",
    "Cambio de curso",
    "Anulación de matrícula",
    "Rectificación de actividades",
    "Recalificación de actividad",
    "Valores a cancelar",
    "Notas de crédito",
}


def count_followups(history: List[Dict[str, Any]]) -> int:
    """
    Cuenta repreguntas del usuario desde el último turno del bot con respuesta completa.
    
    Args:
        history: Historial de conversación
    
    Returns:
        Número de mensajes consecutivos del usuario sin respuesta satisfactoria del bot
    """
    followups = 0
    for msg in reversed(history or []):
        role = msg.get("role") or msg.get("who")
        
        if role in ("bot", "assistant"):
            # Si el bot respondió, detenemos el conteo
            break
        
        if role in ("user", "student", "estudiante"):
            followups += 1
    
    return followups


def missing_required_docs(intent_short: str, slots: Dict[str, Any]) -> List[str]:
    """
    Verifica si faltan documentos/datos obligatorios para una intención.
    
    Args:
        intent_short: Intención corta del usuario
        slots: Slots extraídos de la intención
    
    Returns:
        Lista de documentos/datos faltantes
    """
    required = REQUIRED_DOCS.get(intent_short, [])
    missing = []
    
    for req in required:
        # Quitar "?" opcional
        is_optional = req.endswith("?")
        key = req.rstrip("?")
        
        if not is_optional and not slots.get(key):
            missing.append(key)
    
    return missing


def classify_with_llm(
    user_text: str,
    intent_short: str,
    category: Optional[str],
    subcategory: Optional[str],
    slots: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Usa LLM para clasificar inteligentemente la solicitud y determinar el canal correcto.
    
    Args:
        user_text: Texto original del usuario
        intent_short: Intención corta extraída
        category: Categoría detectada
        subcategory: Subcategoría detectada
        slots: Slots de la intención
    
    Returns:
        {
            "answer_type": "informativo" | "procedimental" | "operativo",
            "department": "académico" | "financiero" | "bienestar" | "administrativo" | "general",
            "channel": "Mesa de Ayuda...",
            "reasoning": "explicación breve"
        }
    """
    
    prompt = f"""Analiza esta solicitud de un estudiante universitario y clasifícala:

SOLICITUD DEL USUARIO: "{user_text}"
INTENCIÓN DETECTADA: "{intent_short}"
CATEGORÍA: "{category or 'No detectada'}"
SUBCATEGORÍA: "{subcategory or 'No detectada'}"

Clasifica la solicitud en JSON:
{{
  "answer_type": "informativo | procedimental | operativo",
  "department": "académico | financiero | bienestar | administrativo | tic | biblioteca | general",
  "channel": "nombre del departamento específico",
  "reasoning": "explicación breve (max 20 palabras)"
}}

CRITERIOS:
- **informativo**: Consulta de datos, definiciones, horarios, requisitos, contactos, porcentajes
- **procedimental**: Pasos para hacer algo, instrucciones, guías, "cómo hacer X"
- **operativo**: Cambio de estado, modificar algo, anular, homologar, pagar, tramitar

DEPARTAMENTOS:
- **académico**: matriculación, cambios de paralelo/curso/carrera, notas, asistencia, titulación, homologaciones
- **financiero**: pagos, valores a cancelar, notas de crédito, aranceles, becas financieras
- **bienestar**: servicios médicos, psicológicos, odontológicos, deportivos, becas sociales
- **administrativo**: certificados, carnets, permisos, documentación general
- **tic**: problemas técnicos, acceso a sistemas (SGA, correo, wifi), contraseñas, EPUNEMI
- **biblioteca**: préstamos, reservas, consultas bibliográficas
- **general**: consultas muy generales o ambiguas

CANALES (según department):
- académico → "Mesa de Ayuda Académica"
- financiero → "Departamento Financiero"
- bienestar → "Bienestar Estudiantil"
- administrativo → "Secretaría General"
- tic → "Soporte TIC"
- biblioteca → "Biblioteca Central"
- general → "Mesa de Ayuda SGA"

Responde SOLO con el JSON, sin markdown ni explicaciones adicionales."""

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        
        # Limpiar markdown si existe
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
        
        result = json.loads(content)
        
        # Validar campos
        if "answer_type" not in result:
            result["answer_type"] = "informativo"
        if "department" not in result:
            result["department"] = "general"
        if "channel" not in result:
            result["channel"] = "Mesa de Ayuda SGA"
        
        print(f"🤖 [LLM Classification]")
        print(f"   Type: {result['answer_type']}")
        print(f"   Department: {result['department']}")
        print(f"   Channel: {result['channel']}")
        print(f"   Reasoning: {result.get('reasoning', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"⚠️ Error en clasificación LLM: {e}")
        # Fallback a clasificación por keywords (método anterior)
        return {
            "answer_type": _classify_answer_type_fallback(intent_short, slots),
            "department": "general",
            "channel": "Mesa de Ayuda SGA",
            "reasoning": "Clasificación por fallback"
        }


def _classify_answer_type_fallback(
    intent_short: str,
    slots: Dict[str, Any]
) -> str:
    """Clasificación fallback por keywords si el LLM falla."""
    INFORMATIVO_KEYWORDS = {
        "consultar", "conocer", "saber", "cuanto", "cuando", "donde",
        "que es", "como es", "porcentaje", "horario", "requisitos",
        "correo", "contacto", "telefono", "validar", "verificar"
    }
    
    OPERATIVO_KEYWORDS = {
        "cambio", "anular", "modificar", "homologar", "convalidar",
        "rectificar", "apelar", "solicitar", "presentar", "retirar",
        "matricular", "pagar"
    }
    
    intent_lower = intent_short.lower() if intent_short else ""
    accion = slots.get("accion", "").lower() if slots else ""
    
    for kw in OPERATIVO_KEYWORDS:
        if kw in intent_lower or kw in accion:
            return "operativo"
    
    for kw in INFORMATIVO_KEYWORDS:
        if kw in intent_lower or kw in accion:
            return "informativo"
    
    if intent_short in CRITICAL_INTENTS:
        return "operativo"
    
    return "informativo"


def should_handoff(
    confidence: float,
    intent_short: str,
    category: Optional[str],
    subcategory: Optional[str],
    slots: Dict[str, Any],
    history: List[Dict[str, Any]],
    user_text: str = "",
    answer_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Decide si se debe ofrecer escalamiento a agente humano.
    Usa LLM para clasificar inteligentemente la solicitud y determinar el canal correcto.
    
    Args:
        confidence: Score de confianza (0.0-1.0)
        intent_short: Intención corta del usuario
        category: Categoría detectada
        subcategory: Subcategoría detectada
        slots: Slots extraídos de la intención
        history: Historial de conversación
        user_text: Texto original del usuario (para clasificación LLM)
        answer_type: Tipo de respuesta (opcional, se calcula si no se provee)
    
    Returns:
        {
            "handoff": bool,
            "handoff_reason": str | None,
            "handoff_channel": str | None,
            "answer_type": str,
            "department": str
        }
    """
    reasons = []
    
    # Clasificar con LLM si no hay answer_type
    llm_classification = None
    if user_text and not answer_type:
        llm_classification = classify_with_llm(user_text, intent_short, category, subcategory, slots)
        answer_type = llm_classification["answer_type"]
        channel_llm = llm_classification["channel"]
        department = llm_classification["department"]
    else:
        # Fallback si no hay texto de usuario
        answer_type = answer_type or _classify_answer_type_fallback(intent_short, slots)
        channel_llm = None
        department = "general"
    
    # Contar repreguntas
    followups = count_followups(history)
    
    # ===== REGLA A: BAJA CONFIANZA =====
    if confidence < TAU_MIN:
        reasons.append(f"baja_confianza<{TAU_MIN}")
    
    # ===== REGLA B: CONFIANZA MEDIA + INTENCIÓN CRÍTICA =====
    if TAU_MIN <= confidence < TAU_NORMA and intent_short in CRITICAL_INTENTS:
        reasons.append("confianza_media+intencion_critica")
    
    # ===== REGLA C1: FALTAN DOCUMENTOS OBLIGATORIOS =====
    missing_docs = missing_required_docs(intent_short, slots or {})
    if missing_docs:
        reasons.append(f"faltan_documentos:{','.join(missing_docs)}")
    
    # ===== REGLA C2: MÚLTIPLES REPREGUNTAS =====
    if followups >= 2 and confidence < TAU_NORMA:
        reasons.append(f"multiples_repreguntas:{followups}")
    
    # ===== REGLA D: TEMAS SENSIBLES =====
    is_sensitive_cat = category in SENSITIVE_CATEGORIES
    is_sensitive_sub = subcategory in SENSITIVE_SUBCATEGORIES
    
    if (is_sensitive_cat or is_sensitive_sub) and confidence < TAU_NORMA:
        reasons.append("tema_sensible+baja_confianza")
    
    # ===== REGLA E: TIPO OPERATIVO =====
    # Solo ofrecer agente si es operativo Y (baja confianza O intención crítica)
    if answer_type == "operativo":
        if confidence < TAU_NORMA or intent_short in CRITICAL_INTENTS:
            if "operativo_requiere_validacion" not in reasons:
                reasons.append("operativo_requiere_validacion")
    
    # Decisión final
    handoff = len(reasons) > 0
    
    # Determinar canal de escalamiento (prioridad: LLM > manual)
    channel = None
    if handoff:
        if channel_llm:
            # Usar canal determinado por LLM
            channel = channel_llm
        else:
            # Fallback a mapeo manual
            if category in {"Académico", "Matriculación"}:
                channel = "Mesa de Ayuda Académica"
            elif category == "Financiero":
                channel = "Departamento Financiero"
            elif category == "Bienestar estudiantil":
                channel = "Bienestar Estudiantil"
            else:
                channel = "Mesa de Ayuda SGA"
    
    return {
        "handoff": handoff,
        "handoff_reason": "; ".join(reasons) if handoff else None,
        "handoff_channel": channel,
        "answer_type": answer_type,
        "department": department,
        "confidence": confidence,
        "followups": followups,
        "llm_reasoning": llm_classification.get("reasoning") if llm_classification else None
    }


def format_handoff_message(
    handoff_data: Dict[str, Any],
    include_reason: bool = False
) -> str:
    """
    Formatea un mensaje amigable para mostrar al usuario.
    
    Args:
        handoff_data: Resultado de should_handoff()
        include_reason: Si incluir el motivo técnico
    
    Returns:
        Mensaje formateado
    """
    if not handoff_data.get("handoff"):
        return ""
    
    channel = handoff_data.get("handoff_channel", "Mesa de Ayuda")
    

    if include_reason:
        reason = handoff_data.get("handoff_reason", "")
        if reason:
            # Traducir razones técnicas a lenguaje amigable
            friendly_reasons = {
                "baja_confianza": "No estoy seguro de poder ayudarte con precisión",
                "confianza_media+intencion_critica": "Este trámite requiere validación humana",
                "faltan_documentos": "Necesitas proporcionar documentación adicional",
                "multiples_repreguntas": "Parece que necesitas asistencia más detallada",
                "tema_sensible": "Este tema requiere atención especializada",
                "operativo_requiere_validacion": "Este trámite debe ser procesado por personal autorizado"
            }
            
            reason_parts = reason.split("; ")
            friendly = []
            for r in reason_parts:
                for key, val in friendly_reasons.items():
                    if key in r:
                        friendly.append(val)
                        break
            
            if friendly:
                msg += f"_Motivo: {', '.join(friendly)}_\n\n"
    
    return msg


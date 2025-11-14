
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from .config import TAU_NORMA, TAU_MIN, llm
from .config import ALLOW_HANDOFF_LLM, llm_budget_remaining

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

# Cargar configuración de handoff desde archivo JSON
def _load_handoff_config() -> Dict[str, Any]:
    """Carga configuración de handoff desde archivo JSON."""
    config_path = Path(__file__).resolve().parent.parent / "data" / "handoff_config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ [Handoff] Error cargando configuración: {e}. Usando valores por defecto.")
        return {
            "departamentos": [],
            "mapeo_categoria_subcategoria": {},
            "mapeo_por_intencion": {}
        }

def get_handoff_config() -> Dict[str, Any]:
    """
    Obtiene la configuración de handoff cargada.
    Usa la variable global _handoff_config que se carga al inicio del módulo.
    """
    return _handoff_config

def get_mapeo_categoria_subcategoria() -> Dict[str, Any]:
    """
    Obtiene el mapeo de categorías y subcategorías desde handoff_config.
    """
    return _handoff_config.get("mapeo_categoria_subcategoria", {})

def get_department_from_categoria_json(categoria: str) -> str:
    """
    Determina el department genérico desde una categoría del JSON.
    Analiza el JSON para mapear categoría → department.
    
    Args:
        categoria: Nombre de la categoría del JSON (ej: "Academico", "Bienestar estudiantil")
    
    Returns:
        Department genérico: "académico", "financiero", "bienestar", "vinculación", o "general"
    """
    mapeo_cat_sub = get_mapeo_categoria_subcategoria()
    
    # Mapeo de categorías del JSON a departments genéricos
    categoria_lower = categoria.lower().strip()
    
    # Buscar la categoría en el JSON (case-insensitive)
    categoria_encontrada = None
    for cat_key in mapeo_cat_sub.keys():
        if cat_key.lower() == categoria_lower:
            categoria_encontrada = cat_key
            break
    
    if not categoria_encontrada:
        return "general"
    
    # Determinar department según la categoría encontrada
    # Analizar el channel al que mapea para determinar el department
    subcategorias = mapeo_cat_sub.get(categoria_encontrada, {})
    if subcategorias:
        # Tomar el primer channel como referencia
        primer_channel = list(subcategorias.values())[0] if subcategorias else ""
        channel_upper = primer_channel.upper()
        
        # Mapear channel → department
        if "BIENESTAR" in channel_upper:
            return "bienestar"
        elif "FINANCIERA" in channel_upper:
            return "financiero"
        elif "VINCULACIÓN" in channel_upper:
            return "vinculación"
        elif "BIBLIOTECA" in channel_upper or "RECURSOS PARA EL APRENDIZAJE" in channel_upper:
            return "biblioteca"
        elif "TECNOLOGÍA" in channel_upper or "TIC" in channel_upper:
            return "tic"
        elif "ACADÉMICOS" in channel_upper or "VICERRECTORADO" in channel_upper:
            return "académico"
    
    # Mapeo directo por nombre de categoría
    mapeo_directo = {
        "academico": "académico",
        "financiero": "financiero",
        "bienestar estudiantil": "bienestar",
        "vinculación": "vinculación",
        "consultas varias": "general",
        "idiomas/ofimatica": "académico",  # Mapea a DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS
    }
    
    return mapeo_directo.get(categoria_lower, "general")

_handoff_config = _load_handoff_config()
DEPARTAMENTOS_REALES = _handoff_config.get("departamentos", [])
MAPEO_DEPARTAMENTOS = {}
MAPEO_POR_INTENCION = _handoff_config.get("mapeo_por_intencion", {})

# Convertir mapeo_categoria_subcategoria a formato de tuplas
mapeo_cat_sub = _handoff_config.get("mapeo_categoria_subcategoria", {})
for categoria, subcategorias in mapeo_cat_sub.items():
    for subcategoria, departamento in subcategorias.items():
        MAPEO_DEPARTAMENTOS[(categoria, subcategoria)] = departamento


def get_department_from_channel(channel: str) -> str:
    """
    Determina el department genérico desde un channel (departamento real).
    
    Args:
        channel: Nombre del departamento real de UNEMI
    
    Returns:
        Department genérico: "académico", "financiero", "bienestar", "tic", "biblioteca", "vinculación", o "general"
    """
    channel_upper = channel.upper()
    
    # Mapeo inverso: departamento real → department genérico
    dept_mapping = {
        "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS": "académico",
        "DIRECCIÓN FINANCIERA": "financiero",
        "DIRECCIÓN DE BIENESTAR UNIVERSITARIO": "bienestar",
        "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES": "tic",
        "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN": "biblioteca",
        "FACULTAD DE VINCULACIÓN": "vinculación",
        "VICERRECTORADO ACADÉMICO DE FORMACIÓN DE GRADO": "académico",
        "VICERRECTORADO DE INVESTIGACIÓN Y POSGRADO": "académico",
    }
    
    # Buscar department desde channel
    for dept_real, dept_gen in dept_mapping.items():
        if dept_real in channel_upper:
            return dept_gen
    
    return "general"


def get_department_from_categoria_subcategoria(categoria: Optional[str], subcategoria: Optional[str]) -> str:
    """
    Determina el department genérico desde categoria/subcategoria usando el mapeo.
    Primero obtiene el channel, luego el department desde el channel.
    
    Args:
        categoria: Categoría de la taxonomía
        subcategoria: Subcategoría de la taxonomía
    
    Returns:
        Department genérico: "académico", "financiero", "bienestar", "tic", "biblioteca", "vinculación", o "general"
    """
    if categoria and subcategoria:
        # Obtener channel desde categoria/subcategoria
        channel = get_departamento_real(categoria, subcategoria, None, "")
        # Obtener department desde channel
        return get_department_from_channel(channel)
    
    return "general"


def get_departamento_real(categoria: Optional[str], subcategoria: Optional[str], department: str = None, user_text: str = "") -> str:
    """
    Mapea categoria/subcategoria a un departamento real de UNEMI.
    Prioridad: mapeo exacto > mapeo por department > mapeo por keywords > default.
    
    Args:
        categoria: Categoría de la taxonomía
        subcategoria: Subcategoría de la taxonomía
        department: Departamento genérico (académico, financiero, etc.)
        user_text: Texto del usuario para extraer keywords
    
    Returns:
        Nombre del departamento real de UNEMI
    """
    # Mapeo exacto por categoria/subcategoria
    if categoria and subcategoria:
        key = (categoria, subcategoria)
        if key in MAPEO_DEPARTAMENTOS:
            return MAPEO_DEPARTAMENTOS[key]
    
    # Mapeo por categoria sola (búsqueda parcial)
    if categoria:
        # Buscar si hay algún mapeo para esta categoría (ignorando subcategoria)
        for (cat, sub), dept in MAPEO_DEPARTAMENTOS.items():
            if cat == categoria:
                return dept
    
    # Mapeo por department genérico
    if department:
        dept_mapping = {
            "académico": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
            "financiero": "DIRECCIÓN FINANCIERA",
            "bienestar": "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
            "tic": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
            "biblioteca": "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
            "vinculación": "FACULTAD DE VINCULACIÓN",
            "administrativo": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
        }
        if department.lower() in dept_mapping:
            return dept_mapping[department.lower()]
    
    # Mapeo por keywords en el texto del usuario
    if user_text:
        text_lower = user_text.lower()
        for keyword, dept in MAPEO_POR_INTENCION.items():
            if keyword in text_lower:
                return dept
    
    # Default: Dirección de Gestión y Servicios Académicos
    return "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"


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
            "answer_type": "informativo" | "operativo",
            "department": "académico" | "financiero" | "bienestar" | "tic" | "biblioteca" | "vinculación" | "general" (determinado automáticamente desde el JSON),
            "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS" | "DIRECCIÓN FINANCIERA" | ... (determinado automáticamente del JSON),
            "reasoning": "explicación breve"
        }
    """
    # El LLM debe determinar department y channel analizando el JSON de departamentos y la consulta del usuario
    # Construir sección con JSON de mapeo de departamentos
    mapeo_cat_sub = get_mapeo_categoria_subcategoria()
    mapeo_departamentos_json = json.dumps(mapeo_cat_sub, ensure_ascii=False, indent=2)
    
    # Construir campos del JSON - siempre pedimos department y channel al LLM
    json_fields = """
  "answer_type": "informativo" o "operativo" (SOLO uno de estos dos valores),
  "department": "académico | financiero | bienestar | administrativo | tic | biblioteca | vinculación | general",
  "channel": "nombre del departamento específico",
  "reasoning": "explicación breve (max 20 palabras)"""
    
    department_section = f"""
MAPEO DE DEPARTAMENTOS (estructura JSON desde handoff_config.json):
{mapeo_departamentos_json}

CANALES DISPONIBLES (departamentos reales de UNEMI):
{chr(10).join([f"- {dept}" for dept in DEPARTAMENTOS_REALES])}

REGLAS PARA DETERMINAR department y channel:
1. Analiza la solicitud del usuario y el JSON de mapeo de departamentos arriba
2. Identifica qué categoría/subcategoría mejor corresponde a la solicitud del usuario
3. El campo "department" DEBE extraerse EXCLUSIVAMENTE del análisis del JSON arriba:
   - Analiza el JSON para ver qué categoría corresponde a la solicitud
   - Luego analiza a qué departamento real mapea esa categoría/subcategoría en el JSON
   - Determina el department genérico según el departamento real:
     * Si el departamento real contiene "BIENESTAR" → department="bienestar"
     * Si el departamento real contiene "FINANCIERA" → department="financiero"
     * Si el departamento real contiene "VINCULACIÓN" → department="vinculación"
     * Si el departamento real contiene "BIBLIOTECA" o "RECURSOS PARA EL APRENDIZAJE" → department="biblioteca"
     * Si el departamento real contiene "TECNOLOGÍA" o "TIC" → department="tic"
     * Si el departamento real contiene "ACADÉMICOS" o "VICERRECTORADO" → department="académico"
     * Si NO encuentras una categoría que corresponda en el JSON → department="general"
4. El campo "channel" debe ser EXACTAMENTE el valor del departamento real que aparece en el JSON para esa categoría/subcategoría (ej: "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS", "DIRECCIÓN FINANCIERA", etc.)
5. Si la solicitud no encaja en ninguna categoría/subcategoría del JSON, usa department="general" y channel="DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
6. El campo "channel" debe ser EXACTAMENTE uno de los departamentos listados arriba (respetar mayúsculas y acentos)

IMPORTANTE: 
- El campo "department" DEBE extraerse EXCLUSIVAMENTE del análisis del JSON de mapeo arriba
- NO uses listas predefinidas, analiza el JSON para determinar el department según el departamento real al que mapea
- Si no encuentras correspondencia en el JSON → department="general" y channel="DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
- Responde SOLO con JSON válido, sin texto adicional, sin markdown, sin explicaciones"""
    
    prompt = f"""Analiza esta solicitud de un estudiante universitario y clasifícala:

SOLICITUD DEL USUARIO: "{user_text}"
INTENCIÓN DETECTADA: "{intent_short}"
CATEGORÍA: "{category or 'No detectada'}"
SUBCATEGORÍA: "{subcategory or 'No detectada'}"

RESPONDE ÚNICAMENTE CON UN JSON VÁLIDO (sin markdown, sin texto adicional, sin explicaciones):

{{{json_fields}
}}

REGLAS OBLIGATORIAS:
1. El campo "answer_type" DEBE ser EXACTAMENTE uno de estos dos valores: "informativo" o "operativo"
   - "informativo": Consulta de datos, definiciones, horarios, requisitos, contactos, porcentajes, pasos para hacer algo, instrucciones, guías, "cómo hacer X", cualquier pregunta que se pueda responder con información de documentos
   - "operativo": Cambio de estado, modificar algo, anular, homologar, pagar, tramitar, cualquier solicitud que requiera acción humana para cambiar o procesar algo

2. El campo "department" DEBE extraerse EXCLUSIVAMENTE del análisis del JSON de mapeo de departamentos proporcionado arriba:
   - Analiza el JSON para identificar qué categoría/subcategoría corresponde a la solicitud
   - Luego determina el department genérico según el departamento real al que mapea en el JSON
   - Si NO encuentras correspondencia en el JSON → department="general"

3. El campo "channel" DEBE ser EXACTAMENTE el nombre del departamento real que aparece en el JSON para esa categoría/subcategoría
   - Si no encuentras correspondencia → channel="DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"

{department_section}

FORMATO DE RESPUESTA:
- Responde SOLO con el JSON válido
- NO incluyas markdown (```json o ```)
- NO incluyas texto explicativo antes o después del JSON
- El JSON debe ser válido y parseable directamente"""

    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        
        # Limpiar markdown si existe
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
        
        # Intentar parsear JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"⚠️ [Handoff] Error parseando JSON del LLM: {e}")
            print(f"   Contenido recibido: {content[:200]}")
            # Intentar extraer JSON si está dentro de texto
            import re
            json_match = re.search(r'\{[^{}]*"answer_type"[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                except:
                    result = {"answer_type": "informativo", "department": "general", "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"}
            else:
                result = {"answer_type": "informativo", "department": "general", "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"}
        
        # Validar campos
        if "answer_type" not in result:
            result["answer_type"] = "informativo"
        
        # Validar campos del LLM
        # El LLM determina department y channel analizando el JSON de departamentos
        if "department" not in result:
            result["department"] = "general"
        if "channel" not in result:
            # Si el LLM no retornó channel, usar mapeo como fallback
            result["channel"] = get_departamento_real(category or "", subcategory or "", result.get("department"), user_text)
        else:
            # Validar que el channel del LLM es uno de los departamentos reales
            channel = result["channel"]
            channel_normalized = channel.upper().strip()
            dept_found = None
            for dept in DEPARTAMENTOS_REALES:
                if dept.upper().strip() == channel_normalized:
                    dept_found = dept
                    break
            
            if dept_found:
                result["channel"] = dept_found
            else:
                # Si no coincide exactamente, usar función de mapeo como fallback
                result["channel"] = get_departamento_real(category or "", subcategory or "", result.get("department"), user_text)
                print(f"⚠️ Canal '{channel}' no coincide con departamentos reales, usando mapeo: '{result['channel']}'")
        
        print(f"🤖 [LLM Classification]")
        print(f"   Type: {result['answer_type']}")
        print(f"   Department: {result['department']}")
        print(f"   Channel: {result['channel']}")
        print(f"   Reasoning: {result.get('reasoning', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"⚠️ Error en clasificación LLM: {e}")
        # Fallback a clasificación por keywords (método anterior)
        fallback_dept = "general"
        fallback_cat = "Consultas varias"
        fallback_sub = "Consultas varias"
        
        fallback_result = {
            "answer_type": _classify_answer_type_fallback(intent_short, slots, user_text),
            "department": fallback_dept,
            "channel": get_departamento_real(fallback_cat, fallback_sub, fallback_dept, user_text),
            "reasoning": "Clasificación por fallback"
        }
        return fallback_result


def _classify_answer_type_fallback(
    intent_short: str,
    slots: Dict[str, Any],
    user_text: str = ""
) -> str:
    """
    Clasificación del tipo de respuesta usando LLM.
    Si el LLM falla, usa heurísticas simples basadas en estructura (sin keywords).
    """
    # Intentar usar LLM primero si está disponible
    try:
        from .config import ALLOW_HANDOFF_LLM, llm_budget_remaining
        if ALLOW_HANDOFF_LLM and llm_budget_remaining() > 0:
            llm_result = classify_with_llm(
                user_text=user_text or intent_short,
                intent_short=intent_short,
                category=None,
                subcategory=None,
                slots=slots
            )
            answer_type = llm_result.get("answer_type", "")
            # Normalizar: mapear "procedimental" a "informativo" (ya no se usa "procedimental")
            if answer_type == "procedimental":
                answer_type = "informativo"
            if answer_type in ("informativo", "operativo"):
                return answer_type
    except Exception as e:
        print(f"⚠️ [Handoff] Error usando LLM para clasificar answer_type: {e}")
    
    # Fallback sin keywords: usar heurísticas estructurales
    # Si la intención está en CRITICAL_INTENTS, es operativo
    if intent_short in CRITICAL_INTENTS:
        return "operativo"
    
    # Heurística simple: si la acción implica un cambio de estado o acción concreta
    # basado en la estructura del texto, no en keywords específicas
    accion = slots.get("accion", "").lower() if slots else ""
    objeto = slots.get("objeto", "").lower() if slots else ""
    
    # Si hay acción y objeto, probablemente es operativo
    # Si solo hay consulta sin acción específica, probablemente es informativo
    if accion and objeto:
        # Verificar si la acción sugiere una operación (basado en longitud y estructura)
        # Acciones operativas suelen ser verbos transitivos con objeto
        if len(accion) > 3 and len(objeto) > 2:
            return "operativo"
    
    # Por defecto, asumir informativo si no hay suficiente información
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
    
    # Inicializar clasificación y usar fallback barato por defecto.
    llm_classification = None
    channel_llm = None
    department = "general"  # Default inicial, el LLM lo determinará según la consulta
    # Fallback inicial para poder evaluar reglas sin invocar LLM
    answer_type = answer_type or _classify_answer_type_fallback(intent_short, slots, user_text)
    
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
    
    # Antes de decidir, ver si es necesario invocar LLM según señales duras
    if user_text:
        should_call_llm = False
        if confidence < TAU_MIN:
            should_call_llm = True
        if TAU_MIN <= confidence < TAU_NORMA and intent_short in CRITICAL_INTENTS:
            should_call_llm = True
        if missing_docs:
            should_call_llm = True
        if followups >= 2 and confidence < TAU_NORMA:
            should_call_llm = True
        # Aplicar gating global: bandera y presupuesto de tokens
        if should_call_llm and ALLOW_HANDOFF_LLM and llm_budget_remaining() >= 1:
            llm_classification = classify_with_llm(
                user_text, intent_short, category, subcategory, slots
            )
            answer_type = llm_classification.get("answer_type", answer_type)
            # Normalizar: mapear "procedimental" a "informativo" (ya no se usa "procedimental")
            if answer_type == "procedimental":
                answer_type = "informativo"
            channel_llm = llm_classification.get("channel")
            # El LLM determina department analizando el JSON de departamentos y la consulta del usuario
            department = llm_classification.get("department", "general")

    # Decisión final
    handoff = len(reasons) > 0
    
    # Determinar canal de escalamiento (prioridad: channel del LLM > categoria/subcategoria > mapeo por keywords > default)
    channel = None
    if handoff:
        if channel_llm:
            # Prioridad 1: Usar canal determinado por LLM (ya analizó el JSON de departamentos)
            channel = channel_llm
        else:
            # Prioridad 2: Fallback a mapeo por categoría si el LLM no retornó channel
            categoria_fallback = category or "Consultas varias"
            subcategoria_fallback = subcategory or "Consultas varias"
            channel = get_departamento_real(categoria_fallback, subcategoria_fallback, department, user_text)
    
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



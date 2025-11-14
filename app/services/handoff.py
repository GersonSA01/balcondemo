
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from .config import TAU_NORMA, TAU_MIN

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


def classify_with_heuristics(intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clasificación determinista usando heurísticas.
    Usa intent_code, accion, objeto y texto libre para mapear a department/channel.
    
    Args:
        intent: Dict con slots de intención (resultado de interpretar_intencion_principal)
    
    Returns:
        {
            "answer_type": "informativo" | "operativo",
            "department": "académico" | "financiero" | "bienestar" | "tic" | "biblioteca" | "vinculación" | "general",
            "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS" | ...,
            "reasoning": "Clasificado por reglas heurísticas"
        }
    """
    intent_code = intent.get("intent_code", "") or "otro"
    accion = (intent.get("accion") or "").lower()
    objeto = (intent.get("objeto") or "").lower()
    texto = (intent.get("detalle_libre") or intent.get("original_user_message") or "").lower()
    
    # 1) Determinar answer_type (ya viene del LLM en V3, pero validamos)
    answer_type = intent.get("answer_type", "informativo")
    if answer_type not in ("informativo", "operativo"):
        # Heurística basada en acción
        if accion in {"cambiar", "modificar", "anular", "inscribir", "homologar", "rectificar", "pagar", "solicitar", "recalificar", "convalidar"}:
            answer_type = "operativo"
        else:
            answer_type = "informativo"
    
    # 2) Determinar department/channel desde handoff_config.json
    department = "general"
    channel = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
    
    # Mapeo por palabras clave comunes en el texto
    texto_completo = f"{texto} {objeto} {accion}".lower()
    
    # Mapeo directo por keywords del mapeo_por_intencion
    mapeo_intencion = get_handoff_config().get("mapeo_por_intencion", {})
    for keyword, dept_real in mapeo_intencion.items():
        if keyword.lower() in texto_completo:
            channel = dept_real
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": f"Clasificado por keyword '{keyword}'"
            }
    
    # Mapeo por objeto/acción específicos usando el JSON de categorías
    mapeo_cat_sub = get_mapeo_categoria_subcategoria()
    
    # Casos comunes: cambio de paralelo
    if "paralelo" in texto_completo:
        categoria = "Academico"
        subcategoria = "Cambio de paralelo"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por cambio de paralelo"
            }
    
    # Casos comunes: beca estudiantil
    if "beca" in texto_completo:
        categoria = "Bienestar estudiantil"
        subcategoria = "Beca estudiantil"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por beca estudiantil"
            }
    
    # Casos comunes: pago/financiero
    if any(kw in texto_completo for kw in ["pago", "pagos", "arancel", "financiero", "valores a cancelar"]):
        categoria = "Financiero"
        subcategoria = "Valores a cancelar"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por tema financiero"
            }
    
    # Casos comunes: biblioteca/libro/préstamo
    if any(kw in texto_completo for kw in ["biblioteca", "libro", "préstamo", "prestamo"]):
        categoria = "Idiomas/ofimatica"
        subcategoria = "Servicio de biblioteca física y digital"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por biblioteca"
            }
    
    # Casos comunes: prácticas/vinculación
    if any(kw in texto_completo for kw in ["practica", "práctica", "vinculación", "vinculacion", "preprofesional"]):
        categoria = "Vinculación"
        subcategoria = "Practicas preprofesionales"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por vinculación"
            }
    
    # Casos comunes: matriculación
    if any(kw in texto_completo for kw in ["matricula", "matriculación", "matricular"]):
        categoria = "Academico"
        subcategoria = "Matriculación"
        if categoria in mapeo_cat_sub and subcategoria in mapeo_cat_sub[categoria]:
            channel = mapeo_cat_sub[categoria][subcategoria]
            department = get_department_from_channel(channel)
            return {
                "answer_type": answer_type,
                "department": department,
                "channel": channel,
                "reasoning": "Clasificado por matriculación"
            }
    
    # Casos comunes: SGA/plataforma/TIC
    if any(kw in texto_completo for kw in ["sga", "plataforma", "correo", "contraseña", "clave", "acceso", "tic"]):
        channel = "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES"
        department = get_department_from_channel(channel)
        return {
            "answer_type": answer_type,
            "department": department,
            "channel": channel,
            "reasoning": "Clasificado por tema TIC"
        }
    
    # Default: académico
    return {
        "answer_type": answer_type,
        "department": department,
        "channel": channel,
        "reasoning": "Clasificado por defecto (general)"
    }


def _classify_answer_type_fallback(
    intent_short: str,
    slots: Dict[str, Any],
    user_text: str = ""
) -> str:
    """
    Clasificación del tipo de respuesta usando heurísticas simples basadas en estructura.
    """
    # Si la intención está en CRITICAL_INTENTS, es operativo
    if intent_short in CRITICAL_INTENTS:
        return "operativo"
    
    # Heurística simple: si la acción implica un cambio de estado o acción concreta
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
    Usa heurísticas para clasificar la solicitud y determinar el canal correcto.
    
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
    
    # Usar classify_with_heuristics para determinar department y channel (sin LLM)
    if user_text and slots:
        try:
            heuristic_classification = classify_with_heuristics(slots)
            answer_type = heuristic_classification.get("answer_type", answer_type)
            channel_llm = heuristic_classification.get("channel")
            department = heuristic_classification.get("department", "general")
        except Exception as e:
            print(f"⚠️ [Handoff] Error en clasificación heurística: {e}")

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



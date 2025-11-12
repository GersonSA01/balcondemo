
from typing import Dict, List, Any, Optional
from .config import TAU_NORMA, TAU_MIN, llm
from .config import ALLOW_HANDOFF_LLM, llm_budget_remaining
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

# Departamentos reales de UNEMI (extraídos del sistema)
DEPARTAMENTOS_REALES = [
    "ARQUITECTURA SOSTENIBLE EN MODALIDAD PRESENCIAL",
    "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    "COMUNICACIÓN EN MODALIDAD PRESENCIAL",
    "CONTABILIDAD Y AUDITORIA EN MODALIDAD PRESENCIAL",
    "DERECHO EN MODALIDAD EN LÍNEA",
    "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "DIRECCIÓN DE OPERACIONES TECNOLÓGICAS Y DE LABORATORIOS",
    "DIRECCIÓN DE RELACIONES INTERINSTITUCIONALES",
    "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "DIRECCIÓN FINANCIERA",
    "ECONOMIA EN MODALIDAD PRESENCIAL",
    "FACULTAD DE EDUCACIÓN",
    "FACULTAD DE CIENCIAS E INGENIERIA",
    "FACULTAD DE SALUD Y SERVICIOS SOCIALES",
    "FACULTAD DE VINCULACIÓN",
    "FISIOTERAPIA EN MODALIDAD PRESENCIAL",
    "INDUSTRIAL EN MODALIDAD PRESENCIAL",
    "LICENCIATURA EN PSICOLOGIA 2019 EN MODALIDAD PRESENCIAL",
    "NUTRICIÓN Y DIETÉTICA EN MODALIDAD PRESENCIAL",
    "PEDAGOGÍA DE LOS IDIOMAS NACIONALES Y EXTRANJEROS EN LÍNEA EN MODALIDAD EN LÍNEA",
    "SOFTWARE 2019",
    "TECNOLOGÍAS DE LA INFORMACIÓN EN MODALIDAD EN LÍNEA",
    "TRABAJO SOCIAL EN MODALIDAD EN LÍNEA",
    "TURISMO EN MODALIDAD EN LÍNEA",
    "VICERRECTORADO ACADÉMICO DE FORMACIÓN DE GRADO",
    "VICERRECTORADO DE INVESTIGACIÓN Y POSGRADO",
]

# Mapeo categoría/subcategoría → Departamento real
MAPEO_DEPARTAMENTOS = {
    # Académico
    ("Academico", "Matriculación"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Cambio de paralelo"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Cambio de carrera"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Cambio de ies"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Titulación"): "VICERRECTORADO ACADÉMICO DE FORMACIÓN DE GRADO",
    ("Academico", "Rectificación de actividades"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Recalificación de actividad"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Reubicación de salón"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Academico", "Cupos por asignatura"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    
    # Bienestar estudiantil
    ("Bienestar estudiantil", "Beca estudiantil"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Servicio médico"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Servicio odontológico"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Servicio psicológico"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Servicio de nutrición"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Servicio de trabajo social"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Cobertura seguro estudiantil"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Gestión de inclusión y equidad académica"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    ("Bienestar estudiantil", "Reportar acoso, discriminación o violencia"): "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    
    # Financiero
    ("Financiero", "Valores a cancelar"): "DIRECCIÓN FINANCIERA",
    ("Financiero", "Notas de crédito"): "DIRECCIÓN FINANCIERA",
    
    # Idiomas/ofimática
    ("Idiomas/ofimatica", "Homologacion módulos ingles"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Idiomas/ofimatica", "Homologacion módulos de computacion"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Idiomas/ofimatica", "Inscripción a prueba de suficiencia"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Idiomas/ofimatica", "Inscripción a módulos"): "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    ("Idiomas/ofimatica", "Servicio de biblioteca física y digital"): "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    
    # Vinculación
    ("Vinculación", "Practicas preprofesionales"): "FACULTAD DE VINCULACIÓN",
    ("Vinculación", "Proyectos de servicios comunitarios"): "FACULTAD DE VINCULACIÓN",
    ("Vinculación", "Actividades extracurriculares"): "FACULTAD DE VINCULACIÓN",
    
    # Consultas varias (default para problemas técnicos)
    ("Consultas varias", "Consultas varias"): "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
}

# Mapeo por palabras clave/intenciones → Departamento
MAPEO_POR_INTENCION = {
    "sga": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "correo": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "plataforma": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "contraseña": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "clave": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "acceso": "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES",
    "biblioteca": "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    "libro": "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    "préstamo": "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    "beca": "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    "becas": "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    "pago": "DIRECCIÓN FINANCIERA",
    "pagos": "DIRECCIÓN FINANCIERA",
    "arancel": "DIRECCIÓN FINANCIERA",
    "matricula": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "matriculación": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "titulación": "VICERRECTORADO ACADÉMICO DE FORMACIÓN DE GRADO",
    "practicas": "FACULTAD DE VINCULACIÓN",
    "vinculación": "FACULTAD DE VINCULACIÓN",
}


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
    slots: Dict[str, Any],
    include_taxonomy: bool = True
) -> Dict[str, Any]:
    """
    Usa LLM para clasificar inteligentemente la solicitud y determinar el canal correcto.
    FUSIONADO: Ahora también clasifica taxonomía (categoria/subcategoria) en la misma llamada LLM.
    
    Args:
        user_text: Texto original del usuario
        intent_short: Intención corta extraída
        category: Categoría detectada
        subcategory: Subcategoría detectada
        slots: Slots de la intención
        include_taxonomy: Si True, también clasifica categoria/subcategoria (default: True)
    
    Returns:
        {
            "answer_type": "informativo" | "procedimental" | "operativo",
            "department": "académico" | "financiero" | "bienestar" | "administrativo" | "tic" | "biblioteca" | "general",
            "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS" | "DIRECCIÓN FINANCIERA" | ... (ver lista completa arriba),
            "reasoning": "explicación breve",
            "categoria": "Académico" | ... (si include_taxonomy=True),
            "subcategoria": "Cambios" | ... (si include_taxonomy=True)
        }
    """
    from pathlib import Path
    from .config import DATA_DIR
    
    # Cargar taxonomía si se requiere (una sola vez para prompt y validación)
    taxonomy_json_str = ""
    taxonomy_for_validation = {}
    if include_taxonomy:
        try:
            taxonomy_path = DATA_DIR / "taxonomia.json"
            if taxonomy_path.exists():
                with open(taxonomy_path, "r", encoding="utf-8") as f:
                    taxonomy = json.load(f)
                # Guardar para validación después
                taxonomy_for_validation = taxonomy
                # Pasar el JSON completo como contexto (más eficiente que lista plana)
                taxonomy_json_str = json.dumps(taxonomy, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    # Construir prompt con taxonomía si aplica
    taxonomy_section = ""
    taxonomy_json_fields = ""
    taxonomy_rules = ""
    
    if include_taxonomy and taxonomy_json_str:
        taxonomy_section = f"""
TAXONOMÍA DEL SISTEMA (estructura JSON):
{taxonomy_json_str}

IMPORTANTE: 
- Debes elegir EXACTAMENTE UNA categoría y UNA subcategoría de la estructura JSON arriba.
- La 'categoria' debe ser EXACTAMENTE el nombre de la clave del JSON (ej: "Academico", "Financiero").
- La 'subcategoria' debe ser EXACTAMENTE uno de los elementos del array de esa categoría (ej: "Cambio de paralelo", "Matriculación").
- Si la categoría tiene un solo elemento o es "Consultas varias", usa ese mismo valor para subcategoria también.
"""
        taxonomy_json_fields = """,
  "categoria": "nombre exacto de la categoría (debe coincidir con una clave del JSON de taxonomía)",
  "subcategoria": "nombre exacto de la subcategoría (debe coincidir con un elemento del array de esa categoría)"
"""
        taxonomy_rules = """
REGLAS PARA TAXONOMÍA:
- Analiza la estructura JSON de taxonomía proporcionada arriba
- Identifica la categoría que mejor corresponde a la solicitud
- Identifica la subcategoría específica dentro de esa categoría
- Los nombres deben ser EXACTAMENTE como aparecen en el JSON (respeta mayúsculas, acentos, espacios)
- Ejemplo: Si el JSON tiene "Academico": ["Cambio de paralelo"], entonces categoria="Academico" y subcategoria="Cambio de paralelo"
"""
    
    prompt = f"""Analiza esta solicitud de un estudiante universitario y clasifícala:

SOLICITUD DEL USUARIO: "{user_text}"
INTENCIÓN DETECTADA: "{intent_short}"
CATEGORÍA: "{category or 'No detectada'}"
SUBCATEGORÍA: "{subcategory or 'No detectada'}"
{taxonomy_section}
Clasifica la solicitud en JSON:
{{
  "answer_type": "informativo | procedimental | operativo",
  "department": "académico | financiero | bienestar | administrativo | tic | biblioteca | general",
  "channel": "nombre del departamento específico",
  "reasoning": "explicación breve (max 20 palabras){taxonomy_json_fields}
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

CANALES DISPONIBLES (departamentos reales de UNEMI):
{chr(10).join([f"- {dept}" for dept in DEPARTAMENTOS_REALES])}

REGLAS DE MAPEO:
- académico → "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS" (default)
- financiero → "DIRECCIÓN FINANCIERA"
- bienestar → "DIRECCIÓN DE BIENESTAR UNIVERSITARIO"
- tic → "DIRECCIÓN DE TECNOLOGÍA DE LA INFORMACIÓN Y COMUNICACIONES"
- biblioteca → "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN"
- vinculación → "FACULTAD DE VINCULACIÓN"
- general → "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS" (default)

IMPORTANTE: El campo "channel" debe ser EXACTAMENTE uno de los departamentos listados arriba (respetar mayúsculas y acentos).
{taxonomy_rules}
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
            # Usar función de mapeo para obtener departamento real
            categoria = result.get("categoria", "")
            subcategoria = result.get("subcategoria", "")
            result["channel"] = get_departamento_real(categoria, subcategoria, result.get("department"), user_text)
        else:
            # Validar que el channel es uno de los departamentos reales
            channel = result["channel"]
            # Normalizar comparación (case-insensitive)
            channel_normalized = channel.upper().strip()
            dept_found = None
            for dept in DEPARTAMENTOS_REALES:
                if dept.upper().strip() == channel_normalized:
                    dept_found = dept
                    break
            
            if not dept_found:
                # Si no coincide exactamente, usar función de mapeo
                categoria = result.get("categoria", "")
                subcategoria = result.get("subcategoria", "")
                result["channel"] = get_departamento_real(categoria, subcategoria, result.get("department"), user_text)
                print(f"⚠️ Canal '{channel}' no coincide con departamentos reales, usando mapeo: '{result['channel']}'")
            else:
                # Usar el nombre exacto del departamento real
                result["channel"] = dept_found
        
        # Validar y parsear taxonomía si aplica (usar la ya cargada)
        if include_taxonomy:
            categoria = result.get("categoria", "").strip()
            subcategoria = result.get("subcategoria", "").strip()
            
            # Validar que la categoría existe en el JSON
            if categoria and taxonomy_for_validation:
                # Buscar categoría (case-insensitive pero mantener el original del JSON)
                categoria_valida = None
                for cat_key in taxonomy_for_validation.keys():
                    if cat_key.lower() == categoria.lower():
                        categoria_valida = cat_key
                        break
                
                if categoria_valida:
                    result["categoria"] = categoria_valida
                    # Validar que la subcategoría existe en esa categoría
                    subcategorias_validas = taxonomy_for_validation[categoria_valida]
                    if isinstance(subcategorias_validas, list) and subcategorias_validas:
                        # Buscar subcategoría (case-insensitive pero mantener el original)
                        subcategoria_valida = None
                        for sub in subcategorias_validas:
                            if sub.lower() == subcategoria.lower():
                                subcategoria_valida = sub
                                break
                        
                        if subcategoria_valida:
                            result["subcategoria"] = subcategoria_valida
                        else:
                            # Si no coincide exactamente, usar la primera de la categoría
                            print(f"⚠️ Subcategoría '{subcategoria}' no encontrada en '{categoria_valida}', usando '{subcategorias_validas[0]}'")
                            result["subcategoria"] = subcategorias_validas[0]
                    else:
                        # Si no hay subcategorías, usar la misma categoría
                        result["subcategoria"] = categoria_valida
                else:
                    # Categoría no válida, usar fallback
                    print(f"⚠️ Categoría '{categoria}' no encontrada en taxonomía, usando fallback")
                    result["categoria"] = "Consultas varias"
                    result["subcategoria"] = "Consultas varias"
            elif not categoria or not subcategoria:
                # Si faltan valores, usar fallback
                result["categoria"] = "Consultas varias"
                result["subcategoria"] = "Consultas varias"
        
        print(f"🤖 [LLM Classification]")
        print(f"   Type: {result['answer_type']}")
        print(f"   Department: {result['department']}")
        print(f"   Channel: {result['channel']}")
        if include_taxonomy:
            print(f"   Categoria: {result.get('categoria', 'N/A')}")
            print(f"   Subcategoria: {result.get('subcategoria', 'N/A')}")
        print(f"   Reasoning: {result.get('reasoning', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"⚠️ Error en clasificación LLM: {e}")
        # Fallback a clasificación por keywords (método anterior)
        fallback_dept = "general"
        fallback_cat = "Consultas varias"
        fallback_sub = "Consultas varias"
        
        fallback_result = {
            "answer_type": _classify_answer_type_fallback(intent_short, slots),
            "department": fallback_dept,
            "channel": get_departamento_real(fallback_cat, fallback_sub, fallback_dept, user_text),
            "reasoning": "Clasificación por fallback"
        }
        if include_taxonomy:
            fallback_result["categoria"] = fallback_cat
            fallback_result["subcategoria"] = fallback_sub
        return fallback_result


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
    
    # Inicializar clasificación y usar fallback barato por defecto.
    llm_classification = None
    channel_llm = None
    department = "general"
    # Fallback inicial para poder evaluar reglas sin invocar LLM
    answer_type = answer_type or _classify_answer_type_fallback(intent_short, slots)
    
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
                user_text, intent_short, category, subcategory, slots, include_taxonomy=True
            )
            answer_type = llm_classification.get("answer_type", answer_type)
            channel_llm = llm_classification.get("channel")
            department = llm_classification.get("department", department)

    # Decisión final
    handoff = len(reasons) > 0
    
    # Determinar canal de escalamiento (prioridad: LLM > mapeo por categoría > default)
    channel = None
    if handoff:
        if channel_llm:
            # Usar canal determinado por LLM (ya validado)
            channel = channel_llm
        else:
            # Fallback a mapeo por categoría usando función helper
            categoria_fallback = category or "Consultas varias"
            subcategoria_fallback = subcategory or "Consultas varias"
            channel = get_departamento_real(categoria_fallback, subcategoria_fallback, department, user_text)
    
    # Extraer categoria/subcategoria de la clasificación LLM si está disponible
    categoria = llm_classification.get("categoria") if llm_classification else None
    subcategoria = llm_classification.get("subcategoria") if llm_classification else None
    
    return {
        "handoff": handoff,
        "handoff_reason": "; ".join(reasons) if handoff else None,
        "handoff_channel": channel,
        "answer_type": answer_type,
        "department": department,
        "confidence": confidence,
        "followups": followups,
        "llm_reasoning": llm_classification.get("reasoning") if llm_classification else None,
        "categoria": categoria,  # De la clasificación LLM fusionada
        "subcategoria": subcategoria  # De la clasificación LLM fusionada
    }



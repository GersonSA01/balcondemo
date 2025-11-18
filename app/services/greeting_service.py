# app/services/greeting_service.py
"""
Servicio para generar saludos estructurados desde el backend.
Todos los saludos se generan aquí y se envían al frontend como mensajes estructurados.
"""
from typing import Dict, Optional, List, Any


def build_greeting_message(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    student_data: Optional[Dict] = None,
    is_initial: bool = False
) -> Dict[str, Any]:
    """
    Construye un saludo estructurado como mensaje para el frontend.
    
    Args:
        category: Categoría de la consulta
        subcategory: Subcategoría de la consulta
        student_data: Datos del estudiante (para personalización)
        is_initial: Si es el saludo inicial del chat
    
    Returns:
        Dict con estructura de mensaje para el frontend
    """
    # Extraer nombre del estudiante si está disponible
    nombre_estudiante = None
    if student_data:
        nombre_estudiante = student_data.get("nombre") or student_data.get("primer_nombre")
        if nombre_estudiante:
            # Obtener solo el primer nombre
            nombre_estudiante = nombre_estudiante.split()[0] if " " in nombre_estudiante else nombre_estudiante
    
    saludo_base = nombre_estudiante if nombre_estudiante else None
    saludo_texto = f"¡Hola {saludo_base}! 👋" if saludo_base else "¡Hola! 👋"
    
    # Si no hay categoría ni subcategoría, retornar saludo genérico
    if not category and not subcategory:
        mensaje = f"{saludo_texto} Soy tu asistente virtual del Balcón de Servicios UNEMI. Estoy aquí para ayudarte con tus consultas y solicitudes. ¿En qué puedo asistirte hoy?"
        return {
            "who": "bot",
            "text": mensaje,
            "type": "greeting",
            "is_initial": is_initial
        }
    
    # ✅ Saludos personalizados por categoría y subcategoría (quemados pero personalizables)
    # Nota: Se soportan múltiples variantes de nombres de categorías para compatibilidad
    greetings_by_category = {
        # Variantes: "MATRICULACIÓN", "Academico", "ACADEMICO"
        "MATRICULACIÓN": {
            "Matriculación": f"{saludo_texto} Veo que necesitas ayuda con tu Matriculación. Estoy aquí para guiarte en todo el proceso. ¿Qué necesitas saber?",
            "Cambio de paralelo": f"{saludo_texto} Te ayudaré con tu solicitud de Cambio de paralelo. ¿En qué asignatura necesitas el cambio?",
            "Cupos por asignatura": f"{saludo_texto} Entiendo que necesitas información sobre Cupos por asignatura. ¿De qué materia necesitas conocer la disponibilidad?",
        },
        "ACADEMICO": {
            "Matriculación": f"{saludo_texto} Veo que necesitas ayuda con tu Matriculación. Estoy aquí para guiarte en todo el proceso. ¿Qué necesitas saber?",
            "Cambio de paralelo": f"{saludo_texto} Te ayudaré con tu solicitud de Cambio de paralelo. ¿En qué asignatura necesitas el cambio?",
            "Cupos por asignatura": f"{saludo_texto} Entiendo que necesitas información sobre Cupos por asignatura. ¿De qué materia necesitas conocer la disponibilidad?",
        },
        "Academico": {
            "Matriculación": f"{saludo_texto} Veo que necesitas ayuda con tu Matriculación. Estoy aquí para guiarte en todo el proceso. ¿Qué necesitas saber?",
            "Cambio de paralelo": f"{saludo_texto} Te ayudaré con tu solicitud de Cambio de paralelo. ¿En qué asignatura necesitas el cambio?",
            "Cupos por asignatura": f"{saludo_texto} Entiendo que necesitas información sobre Cupos por asignatura. ¿De qué materia necesitas conocer la disponibilidad?",
        },
        # Variantes: "TITULACIÓN", "Academico"
        "TITULACIÓN": {
            "Titulación": f"{saludo_texto} ¡Qué emocionante! Estás en el proceso de Titulación. ¿En qué puedo asistirte?",
            "Rectificación de actividades": f"{saludo_texto} Te ayudaré con la Rectificación de actividades. Cuéntame qué necesitas rectificar.",
            "Recalificación de actividad": f"{saludo_texto} Veo que necesitas una Recalificación de actividad. ¿De qué asignatura y actividad se trata?",
        },
        # Variantes: "CAMBIO DE CARRERA", "Academico"
        "CAMBIO DE CARRERA": {
            "Cambio de carrera": f"{saludo_texto} Te guiaré en tu proceso de Cambio de carrera. ¿A qué carrera deseas cambiarte?",
            "Reubicación de salón": f"{saludo_texto} Te ayudaré con la Reubicación de salón. ¿Qué situación se te presenta?",
            "Cambio de ies": f"{saludo_texto} Entiendo que estás considerando un Cambio de IES. ¿En qué puedo ayudarte?",
        },
        # Variantes: "BIENESTAR UNIVERSITARIO", "BIENESTAR ESTUDIANTIL", "Bienestar estudiantil"
        "BIENESTAR UNIVERSITARIO": {
            "Servicio médico": f"{saludo_texto} Te guiaré con el Servicio médico. ¿Qué consulta necesitas realizar?",
            "Servicio psicológico": f"{saludo_texto} Bienvenido/a al Servicio psicológico. Estoy aquí para orientarte. ¿Cómo puedo ayudarte?",
            "Servicio de nutrición": f"{saludo_texto} Te ayudaré con el Servicio de nutrición. ¿Qué información necesitas?",
            "Servicio de trabajo social": f"{saludo_texto} Estoy aquí para guiarte con el Servicio de trabajo social. ¿En qué puedo asistirte?",
            "Beca estudiantil": f"{saludo_texto} Te ayudaré con tu solicitud de Beca estudiantil. ¿Qué necesitas saber sobre las becas disponibles?",
            "Cobertura seguro estudiantil": f"{saludo_texto} Te orientaré sobre la Cobertura del seguro estudiantil. ¿Qué consulta tienes?",
            "Gestión de inclusión y equidad académica": f"{saludo_texto} Estoy aquí para ayudarte con Gestión de inclusión y equidad académica. ¿Cómo puedo apoyarte?",
            "Reportar acoso, discriminación o violencia": f"{saludo_texto} Tu bienestar es importante. Estoy aquí para guiarte en cómo Reportar acoso, discriminación o violencia. ¿Qué necesitas?",
        },
        "BIENESTAR ESTUDIANTIL": {
            "Servicio médico": f"{saludo_texto} Te guiaré con el Servicio médico. ¿Qué consulta necesitas realizar?",
            "Servicio psicológico": f"{saludo_texto} Bienvenido/a al Servicio psicológico. Estoy aquí para orientarte. ¿Cómo puedo ayudarte?",
            "Servicio de nutrición": f"{saludo_texto} Te ayudaré con el Servicio de nutrición. ¿Qué información necesitas?",
            "Servicio de trabajo social": f"{saludo_texto} Estoy aquí para guiarte con el Servicio de trabajo social. ¿En qué puedo asistirte?",
            "Beca estudiantil": f"{saludo_texto} Te ayudaré con tu solicitud de Beca estudiantil. ¿Qué necesitas saber sobre las becas disponibles?",
            "Cobertura seguro estudiantil": f"{saludo_texto} Te orientaré sobre la Cobertura del seguro estudiantil. ¿Qué consulta tienes?",
            "Gestión de inclusión y equidad académica": f"{saludo_texto} Estoy aquí para ayudarte con Gestión de inclusión y equidad académica. ¿Cómo puedo apoyarte?",
            "Reportar acoso, discriminación o violencia": f"{saludo_texto} Tu bienestar es importante. Estoy aquí para guiarte en cómo Reportar acoso, discriminación o violencia. ¿Qué necesitas?",
        },
        "Bienestar estudiantil": {
            "Servicio médico": f"{saludo_texto} Te guiaré con el Servicio médico. ¿Qué consulta necesitas realizar?",
            "Servicio psicológico": f"{saludo_texto} Bienvenido/a al Servicio psicológico. Estoy aquí para orientarte. ¿Cómo puedo ayudarte?",
            "Servicio de nutrición": f"{saludo_texto} Te ayudaré con el Servicio de nutrición. ¿Qué información necesitas?",
            "Servicio de trabajo social": f"{saludo_texto} Estoy aquí para guiarte con el Servicio de trabajo social. ¿En qué puedo asistirte?",
            "Beca estudiantil": f"{saludo_texto} Te ayudaré con tu solicitud de Beca estudiantil. ¿Qué necesitas saber sobre las becas disponibles?",
            "Cobertura seguro estudiantil": f"{saludo_texto} Te orientaré sobre la Cobertura del seguro estudiantil. ¿Qué consulta tienes?",
            "Gestión de inclusión y equidad académica": f"{saludo_texto} Estoy aquí para ayudarte con Gestión de inclusión y equidad académica. ¿Cómo puedo apoyarte?",
            "Reportar acoso, discriminación o violencia": f"{saludo_texto} Tu bienestar es importante. Estoy aquí para guiarte en cómo Reportar acoso, discriminación o violencia. ¿Qué necesitas?",
        },
        # Variantes: "OTROS", "Consultas varias"
        "OTROS": {
            "Consultas varias": f"{saludo_texto} Estoy aquí para ayudarte con tus Consultas varias. ¿Qué información necesitas?",
        },
        "Consultas varias": {
            "Consultas varias": f"{saludo_texto} Estoy aquí para ayudarte con tus Consultas varias. ¿Qué información necesitas?",
        },
        # Variantes: "GESTIÓN FINANCIERA", "Financiero"
        "GESTIÓN FINANCIERA": {
            "Valores a cancelar": f"{saludo_texto} Te ayudaré con información sobre los Valores a cancelar. ¿Qué necesitas saber?",
            "Notas de crédito": f"{saludo_texto} Te guiaré con el proceso de Notas de crédito. ¿Qué consulta tienes?",
        },
        "Financiero": {
            "Valores a cancelar": f"{saludo_texto} Te ayudaré con información sobre los Valores a cancelar. ¿Qué necesitas saber?",
            "Notas de crédito": f"{saludo_texto} Te guiaré con el proceso de Notas de crédito. ¿Qué consulta tienes?",
        },
        # Variantes: "GESTIÓN ACADÉMICA", "Idiomas/ofimatica"
        "GESTIÓN ACADÉMICA": {
            "Homologacion módulos ingles": f"{saludo_texto} Te ayudaré con la Homologación de módulos de inglés. ¿Qué información necesitas?",
            "Homologacion módulos de computacion": f"{saludo_texto} Te guiaré en la Homologación de módulos de computación. ¿Qué necesitas saber?",
            "Inscripción a prueba de suficiencia": f"{saludo_texto} Te orientaré sobre la Inscripción a prueba de suficiencia. ¿Cómo puedo ayudarte?",
            "Inscripción a módulos": f"{saludo_texto} Te ayudaré con la Inscripción a módulos. ¿Qué módulo te interesa?",
            "Servicio de biblioteca física y digital": f"{saludo_texto} Te guiaré sobre el Servicio de biblioteca física y digital. ¿Qué necesitas?",
        },
        "Idiomas/ofimatica": {
            "Homologacion módulos ingles": f"{saludo_texto} Te ayudaré con la Homologación de módulos de inglés. ¿Qué información necesitas?",
            "Homologacion módulos de computacion": f"{saludo_texto} Te guiaré en la Homologación de módulos de computación. ¿Qué necesitas saber?",
            "Inscripción a prueba de suficiencia": f"{saludo_texto} Te orientaré sobre la Inscripción a prueba de suficiencia. ¿Cómo puedo ayudarte?",
            "Inscripción a módulos": f"{saludo_texto} Te ayudaré con la Inscripción a módulos. ¿Qué módulo te interesa?",
            "Servicio de biblioteca física y digital": f"{saludo_texto} Te guiaré sobre el Servicio de biblioteca física y digital. ¿Qué necesitas?",
        },
        # Variantes: "PRÁCTICAS PROFESIONALES", "Vinculación"
        "PRÁCTICAS PROFESIONALES": {
            "Practicas preprofesionales": f"{saludo_texto} Te ayudaré con tus Prácticas preprofesionales. ¿Qué información necesitas?",
            "Proyectos de servicios comunitarios": f"{saludo_texto} Te guiaré en los Proyectos de servicios comunitarios. ¿Cómo puedo asistirte?",
            "Actividades extracurriculares": f"{saludo_texto} Te orientaré sobre las Actividades extracurriculares. ¿Qué te interesa saber?",
        },
        "Vinculación": {
            "Practicas preprofesionales": f"{saludo_texto} Te ayudaré con tus Prácticas preprofesionales. ¿Qué información necesitas?",
            "Proyectos de servicios comunitarios": f"{saludo_texto} Te guiaré en los Proyectos de servicios comunitarios. ¿Cómo puedo asistirte?",
            "Actividades extracurriculares": f"{saludo_texto} Te orientaré sobre las Actividades extracurriculares. ¿Qué te interesa saber?",
        },
    }
    
    # ✅ Buscar saludo específico - intentar múltiples variantes de categoría
    category_variants = []
    if category:
        category_variants = [
            category.upper(),
            category,  # Nombre original
            category.title(),  # Title case
        ]
        # Variantes adicionales
        if category.upper() == "ACADEMICO":
            category_variants.extend(["MATRICULACIÓN", "TITULACIÓN", "CAMBIO DE CARRERA"])
        elif "bienestar" in category.lower():
            category_variants.extend(["BIENESTAR UNIVERSITARIO", "BIENESTAR ESTUDIANTIL"])
        elif "financier" in category.lower():
            category_variants.extend(["GESTIÓN FINANCIERA"])
        elif "idiomas" in category.lower() or "ofimatica" in category.lower():
            category_variants.extend(["GESTIÓN ACADÉMICA"])
        elif "vinculación" in category.lower() or "vinculacion" in category.lower():
            category_variants.extend(["PRÁCTICAS PROFESIONALES"])
        elif "otro" in category.lower() or "varias" in category.lower():
            category_variants.extend(["OTROS", "Consultas varias"])
    
    # Buscar en todas las variantes
    for cat_variant in category_variants:
        if cat_variant in greetings_by_category:
            if subcategory and subcategory in greetings_by_category[cat_variant]:
                mensaje = greetings_by_category[cat_variant][subcategory]
                return {
                    "who": "bot",
                    "text": mensaje,
                    "type": "greeting",
                    "category": category,
                    "subcategory": subcategory,
                    "is_initial": is_initial
                }
    
    # Si no se encontró con subcategoría, intentar solo con categoría (sin subcategoría específica)
    for cat_variant in category_variants:
        if cat_variant in greetings_by_category:
            # Buscar cualquier subcategoría en esa categoría como fallback genérico
            subcategories = list(greetings_by_category[cat_variant].keys())
            if subcategories:
                # Usar el primer saludo de la categoría como genérico
                mensaje = greetings_by_category[cat_variant][subcategories[0]]
                # Reemplazar la subcategoría específica con la subcategoría actual si existe
                if subcategory:
                    mensaje = f"{saludo_texto} Veo que necesitas ayuda con {subcategory} en {category}. Estoy aquí para guiarte. ¿Qué necesitas saber?"
                return {
                    "who": "bot",
                    "text": mensaje,
                    "type": "greeting",
                    "category": category,
                    "subcategory": subcategory,
                    "is_initial": is_initial
                }
    
    # Saludo genérico con categoría y subcategoría
    if category and subcategory:
        mensaje = f"{saludo_texto} Veo que necesitas ayuda con {subcategory} en {category}. Estoy aquí para guiarte. ¿Qué necesitas saber?"
    elif category:
        mensaje = f"{saludo_texto} Veo que necesitas ayuda con {category}. Estoy aquí para guiarte. ¿Qué necesitas saber?"
    else:
        mensaje = f"{saludo_texto} Estoy aquí para ayudarte. ¿En qué puedo asistirte?"
    
    return {
        "who": "bot",
        "text": mensaje,
        "type": "greeting",
        "category": category,
        "subcategory": subcategory,
        "is_initial": is_initial
    }


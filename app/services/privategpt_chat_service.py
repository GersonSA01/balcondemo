# app/services/privategpt_chat_service.py
"""
Servicio de chat usando PrivateGPT API.
Flujo: Saludo → Interpretar Intención → Confirmar → Solicitudes Relacionadas → PrivateGPT API (con mensaje confirmado)
"""
from typing import Dict, List, Any, Optional
from enum import Enum
import json
import re
import unicodedata
from datetime import datetime
from .privategpt_client import get_privategpt_client, PrivateGPTClient
from .handoff import get_departamento_real, _classify_answer_type_fallback, classify_with_heuristics
from .intent_parser import (
    es_greeting,
    interpretar_intencion_principal,
    _confirm_text_from_slots,
    es_confirmacion_positiva,
    es_confirmacion_negativa,
    obtener_primer_nombre
)
from .related_request_matcher import find_related_requests, load_student_requests
from .privategpt_response_parser import PrivateGPTResponseParser
from .solicitud_service import crear_solicitud, obtener_solicitudes_usuario
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus
from pathlib import Path


# ConversationStage ahora viene de conversation_types.py

# Intenciones que se pueden responder SOLO con student_data (sin LLM ni PrivateGPT)
DATA_INTENTS = {
    "consultar_solicitudes_balcon",
    "consultar_carrera_actual",
    "consultar_roles_usuario",
    "consultar_datos_personales",
}

# Campos seguros que se pueden mostrar del JSON (whitelist)
SAFE_PERSON_FIELDS = {
    "nombres", "apellido1", "apellido2", "emailinst", "email"
}


def _agrupar_fuentes_por_archivo(fuentes: List[Dict]) -> List[Dict]:
    """
    Agrupa las fuentes por archivo y consolida las páginas.
    
    Args:
        fuentes: Lista de fuentes con formato [{"archivo": str, "pagina": str}, ...]
    
    Returns:
        Lista de fuentes agrupadas: [{"archivo": str, "paginas": [str, ...]}, ...]
    """
    if not fuentes:
        return []
    
    # Agrupar por archivo
    archivos_dict = {}
    for fuente in fuentes:
        archivo = fuente.get("archivo", "").strip()
        pagina = fuente.get("pagina", "").strip()
        
        if not archivo:
            continue
        
        if archivo not in archivos_dict:
            archivos_dict[archivo] = []
        
        # Agregar página si no está duplicada
        if pagina and pagina not in archivos_dict[archivo]:
            archivos_dict[archivo].append(pagina)
    
    # Convertir a lista y ordenar páginas numéricamente cuando sea posible
    fuentes_agrupadas = []
    for archivo, paginas in archivos_dict.items():
        # Intentar ordenar numéricamente, si falla ordenar alfabéticamente
        try:
            paginas_ordenadas = sorted(paginas, key=lambda x: int(x) if x.isdigit() else float('inf'))
        except (ValueError, TypeError):
            paginas_ordenadas = sorted(paginas)
        
        fuentes_agrupadas.append({
            "archivo": archivo,
            "paginas": paginas_ordenadas
        })
    
    return fuentes_agrupadas


def _formatear_fuentes_para_respuesta(fuentes_agrupadas: List[Dict]) -> str:
    """
    Formatea las fuentes agrupadas en un texto legible para incluir en la respuesta.
    
    Args:
        fuentes_agrupadas: Lista de fuentes agrupadas [{"archivo": str, "paginas": [str, ...]}, ...]
    
    Returns:
        String formateado con las fuentes
    """
    if not fuentes_agrupadas:
        return ""
    
    partes = []
    for fuente in fuentes_agrupadas:
        archivo = fuente.get("archivo", "")
        paginas = fuente.get("paginas", [])
        
        if not archivo:
            continue
        
        if paginas:
            if len(paginas) == 1:
                partes.append(f"{archivo} (página {paginas[0]})")
            else:
                paginas_str = ", ".join(paginas)
                partes.append(f"{archivo} (páginas {paginas_str})")
        else:
            partes.append(archivo)
    
    
    return ""


def _normalize_text_for_llm(text: str) -> str:
    """
    Normaliza el texto quitando tildes y caracteres especiales para enviarlo al LLM.
    
    Args:
        text: Texto a normalizar
    
    Returns:
        Texto normalizado sin tildes ni caracteres especiales
    """
    if not text:
        return ""
    
    # Normalizar a NFD (descomponer caracteres con tildes)
    text_normalized = unicodedata.normalize('NFD', text)
    
    # Filtrar solo caracteres ASCII básicos (quitar diacríticos)
    text_ascii = ''.join(
        char for char in text_normalized 
        if unicodedata.category(char) != 'Mn'  # Mn = Mark, Nonspacing (tildes, diacríticos)
    )
    
    # Reemplazar caracteres especiales comunes por equivalentes ASCII
    replacements = {
        'ñ': 'n',
        'Ñ': 'N',
        '¿': '?',
        '¡': '!',
        '«': '"',
        '»': '"',
        '…': '...',
        '–': '-',
        '—': '-',
    }
    
    for old_char, new_char in replacements.items():
        text_ascii = text_ascii.replace(old_char, new_char)
    
    # Limpiar espacios múltiples y espacios al inicio/final
    text_ascii = re.sub(r'\s+', ' ', text_ascii).strip()
    
    return text_ascii


def _call_privategpt_api(
    user_text: str,  # SOLO el mensaje confirmado del usuario (no "sí" o "correcto")
    conversation_history: List[Dict],
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None,
    perfil_id: str = None
) -> Dict[str, Any]:
    """
    Llama a la API de PrivateGPT con el mensaje confirmado del usuario.
    Incluye contexto de rol para filtrar información relevante.
    
    Args:
        user_text: Mensaje del usuario
        conversation_history: Historial de conversación
        category: Categoría seleccionada
        subcategory: Subcategoría seleccionada
        student_data: Datos completos del usuario desde data_unemi.json
        perfil_id: ID del perfil seleccionado (opcional)
    
    Returns:
        {
            "has_information": bool,
            "response": str,
            "fuentes": [{"archivo": str, "pagina": str}, ...],
            "error": str or None
        }
    """
    client = get_privategpt_client()
    
    try:
        is_available = client.is_available()
    except Exception as e:
        print(f"⚠️ [PrivateGPT] Health check falló: {e}")
        is_available = False
    
    if not is_available:
        print(f"⚠️ [PrivateGPT] Health check falló, pero intentando petición de chat...")
    
    # Extraer rol del usuario desde student_data usando perfil_id si está disponible
    rol = _extract_user_role(student_data, perfil_id)
    print(f"👤 [Rol] Rol detectado: {rol} (perfil_id: {perfil_id})")
    
    # Normalizar texto del usuario antes de enviarlo al LLM
    user_text_normalized = _normalize_text_for_llm(user_text)
    print(f"📝 [Normalización] Texto original: '{user_text[:100]}'")
    print(f"📝 [Normalización] Texto normalizado: '{user_text_normalized[:100]}'")
    
    # Construir mensajes con contexto de rol usando texto normalizado
    messages = _build_role_context_message(user_text_normalized, rol)
    
    # Construir session_context con información del rol (si PrivateGPT lo soporta)
    session_context = None
    if student_data:
        perfil_principal = _get_current_student_profile(student_data)
        if not perfil_principal:
            perfiles_activos = [p for p in student_data.get("perfiles", []) if p.get("status", False)]
            if perfiles_activos:
                perfil_principal = perfiles_activos[0]
        
        if perfil_principal:
            session_context = {
                "user_role": rol,
                "profile_type": perfil_principal.get("tipo", ""),
                "carrera": perfil_principal.get("carrera_nombre", ""),
                "facultad": perfil_principal.get("facultad_nombre", "")
            }
    
    try:
        response = client.chat_completion(
            messages=messages,
            use_context=True,
            include_sources=True,
            stream=False,
            session_context=session_context
        )
        
        if response.get("error"):
            error_msg = response.get("error", "Error desconocido")
            print(f"❌ [PrivateGPT] Error: {error_msg}")
            return {
                "has_information": False,
                "response": f"Lo siento, ocurrió un error al procesar tu solicitud: {error_msg}",
                "fuentes": [],
                "error": error_msg
            }
        
        # Usar parser para normalizar respuesta
        parsed = PrivateGPTResponseParser.parse(response)
        has_information = parsed.get("has_information", False)
        response_text = parsed.get("response", "")
        fuentes = parsed.get("fuentes", [])
        
        if not response_text:
            response_text = "No pude procesar tu solicitud."
        
        fuentes_agrupadas = _agrupar_fuentes_por_archivo(fuentes)
        
        # Formatear fuentes para incluir en la respuesta (opcional, para mostrar en el texto)
        # Pero mantener las fuentes originales y agrupadas en el dict para el frontend
        fuentes_texto = _formatear_fuentes_para_respuesta(fuentes_agrupadas)
        
        # Si hay fuentes, agregarlas al final de la respuesta
        response_final = response_text
        if fuentes_agrupadas and has_information:
            # Solo agregar si no están ya en la respuesta
            if "Fuentes:" not in response_text and "fuentes:" not in response_text.lower():
                response_final = response_text + fuentes_texto
        
        
        return {
            "has_information": has_information,
            "response": response_final,
            "fuentes": fuentes_agrupadas,  # Devolver fuentes agrupadas en lugar de las originales
            "error": None
        }
        
    except Exception as e:
        import traceback
        print(f"❌ [PrivateGPT] Excepción: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        return {
            "has_information": False,
            "response": f"Lo siento, ocurrió un error al procesar tu solicitud: {str(e)}. Por favor, intenta nuevamente o contacta al administrador.",
            "fuentes": [],
            "error": str(e)
        }


def _aplicar_excepciones_informativas(
    answer_type: str,
    intent_short: str,
    intent_slots: Dict,
    user_text: str
) -> str:
    """
    Aplica reglas de excepciones para convertir ciertas solicitudes operativas en informativas.
    
    Algunas solicitudes que parecen operativas en realidad deben tratarse como información
    porque están prohibidas o requieren consulta en el reglamento.
    
    Args:
        answer_type: Tipo de respuesta actual ("operativo" o "informativo")
        intent_short: Intención corta extraída
        intent_slots: Slots de la intención
        user_text: Texto original del usuario
    
    Returns:
        Tipo de respuesta corregido ("operativo" o "informativo")
    """
    # Si ya es informativo, no hay nada que hacer
    if answer_type == "informativo":
        return answer_type
    
    # Lista de excepciones: intenciones que deben tratarse como información aunque sean operativas
    EXCEPCIONES_INFORMATIVAS = {
        # Justificación de faltas/inasistencias - está prohibido, debe consultarse en reglamento
        "justificar falta",
        "justificar inasistencia",
        "justificar ausencia",
        "justificación de falta",
        "justificación de inasistencia",
        "justificación de ausencia",
        "excusa por falta",
        "excusa por inasistencia",
        "permiso por falta",
        "permiso por inasistencia",
        "como justificar falta",
        "como justificar inasistencia",
        "procedimiento justificar falta",
        "procedimiento justificar inasistencia",
    }
    
    # Normalizar texto para comparación
    intent_lower = (intent_short or "").lower()
    user_text_lower = (user_text or "").lower()
    accion = (intent_slots.get("accion", "") or "").lower()
    objeto = (intent_slots.get("objeto", "") or "").lower()
    
    # Combinar acción y objeto para detectar patrones
    accion_objeto = f"{accion} {objeto}".strip()
    
    # Verificar si coincide con alguna excepción
    for excepcion in EXCEPCIONES_INFORMATIVAS:
        if (excepcion in intent_lower or 
            excepcion in user_text_lower or 
            excepcion in accion_objeto):
            return "informativo"
    
    # Verificar patrones específicos en el texto del usuario usando regex
    patrones_prohibidos = [
        r"justificar\s+(una\s+)?falta",
        r"justificar\s+(una\s+)?inasistencia",
        r"justificar\s+(una\s+)?ausencia",
        r"excusa\s+por\s+(falta|inasistencia|ausencia)",
        r"permiso\s+por\s+(falta|inasistencia|ausencia)",
        r"como\s+justificar",
        r"procedimiento\s+para\s+justificar",
    ]
    
    for patron in patrones_prohibidos:
        if re.search(patron, user_text_lower):
            return "informativo"
    
    return answer_type


def _extract_user_role(student_data: Optional[Dict], perfil_id: Optional[str] = None) -> str:
    """
    Extrae el rol del usuario desde el perfil seleccionado en student_data.
    Ahora funciona con datos completos desde data_unemi.json.
    
    Args:
        student_data: Datos completos del usuario desde data_unemi.json
        perfil_id: ID del perfil seleccionado (opcional, si no se proporciona usa el principal)
    
    Returns:
        String con el rol: "estudiante", "profesor", "administrativo", "externo", etc.
        Por defecto retorna "usuario" si no se puede determinar.
    """
    if not student_data:
        return "usuario"
    
    # Buscar perfiles en student_data (estructura desde data_unemi.json)
    perfiles = student_data.get("perfiles", [])
    if not perfiles:
        return "usuario"
    
    # Filtrar perfiles activos
    perfiles_activos = [p for p in perfiles if p.get("status", False)]
    if not perfiles_activos:
        return "usuario"
    
    # Si se proporciona perfil_id, buscar ese perfil específico
    perfil_seleccionado = None
    if perfil_id:
        for p in perfiles_activos:
            if str(p.get("id")) == str(perfil_id):
                perfil_seleccionado = p
                break
    
    # Si no se encontró el perfil específico o no se proporcionó perfil_id,
    # buscar perfil principal
    if not perfil_seleccionado:
        for p in perfiles_activos:
            if p.get("inscripcionprincipal", False):
                perfil_seleccionado = p
                break
    
    # Si aún no hay perfil, usar el primero activo
    if not perfil_seleccionado:
        perfil_seleccionado = perfiles_activos[0]
    
    # Determinar rol según flags del perfil
    if perfil_seleccionado.get("es_estudiante", False):
        return "estudiante"
    elif perfil_seleccionado.get("es_profesor", False):
        return "profesor"
    elif perfil_seleccionado.get("es_administrativo", False):
        return "administrativo"
    elif perfil_seleccionado.get("es_externo", False):
        return "externo"
    elif perfil_seleccionado.get("es_postulante", False):
        return "postulante"
    elif perfil_seleccionado.get("es_postulanteempleo", False):
        return "postulante_empleo"
    
    # Fallback: usar el tipo del perfil
    tipo = perfil_seleccionado.get("tipo", "").upper()
    if "ESTUDIANTE" in tipo or "INGENIER" in tipo or "SOFTWARE" in tipo or "ADMISI" in tipo:
        return "estudiante"
    elif "PROFESOR" in tipo:
        return "profesor"
    elif "ADMINISTRATIVO" in tipo:
        return "administrativo"
    elif "EXTERNO" in tipo:
        return "externo"
    
    return "usuario"


def _build_role_context_message(user_text: str, rol: str) -> List[Dict[str, str]]:
    """
    Construye los mensajes con contexto de rol para PrivateGPT.
    
    NOTA: PrivateGPT ahora combina automáticamente nuestro system message con
    default_query_system_prompt de settings-docker.yaml, así que solo necesitamos
    enviar las instrucciones específicas de filtrado por rol.
    
    Args:
        user_text: Mensaje original del usuario
        rol: Rol del usuario (estudiante, profesor, etc.)
    
    Returns:
        Lista de mensajes con contexto de rol
    """
    # Instrucciones específicas de filtrado según el rol
    filtrado_por_rol = {
        "estudiante": (
            "ROL DEL USUARIO: ESTUDIANTE\n\n"
            "FILTRADO CRITICO:\n"
            "- SOLO usa documentos para ESTUDIANTES (reglamentos estudiantiles, procesos académicos estudiantiles, servicios estudiantiles, becas estudiantiles)\n"
            "- IGNORA documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente)\n"
            "- IGNORA documentos para PERSONAL ADMINISTRATIVO\n"
            "- Si el contexto contiene SOLO información para profesores/administrativos, establece has_information=false"
        ),
        "profesor": (
            "ROL DEL USUARIO: PROFESOR\n\n"
            "FILTRADO CRITICO:\n"
            "- SOLO usa documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente, procesos académicos para profesores)\n"
            "- IGNORA documentos para ESTUDIANTES (procesos de matrícula estudiantil, servicios estudiantiles)\n"
            "- IGNORA documentos para PERSONAL ADMINISTRATIVO\n"
            "- Si el contexto contiene SOLO información para estudiantes/administrativos, establece has_information=false"
        ),
        "administrativo": (
            "ROL DEL USUARIO: ADMINISTRATIVO\n\n"
            "FILTRADO CRITICO:\n"
            "- SOLO usa documentos para PERSONAL ADMINISTRATIVO (normativas administrativas, procedimientos administrativos, gestión universitaria)\n"
            "- IGNORA documentos para ESTUDIANTES\n"
            "- IGNORA documentos para PROFESORES\n"
            "- Si el contexto contiene SOLO información para estudiantes/profesores, establece has_information=false"
        ),
        "externo": (
            "ROL DEL USUARIO: EXTERNO\n\n"
            "FILTRADO:\n"
            "- Prioriza información general de la universidad\n"
            "- Evita información muy específica de procesos internos\n"
            "- Si el contexto contiene información muy específica de procesos internos, establece has_information=false"
        ),
        "postulante": (
            "ROL DEL USUARIO: POSTULANTE\n\n"
            "FILTRADO CRITICO:\n"
            "- SOLO usa documentos sobre ADMISIÓN y POSTULACIÓN\n"
            "- IGNORA documentos sobre procesos internos de estudiantes ya matriculados\n"
            "- Si el contexto contiene SOLO información para estudiantes matriculados, establece has_information=false"
        ),
    }
    
    contexto_rol = filtrado_por_rol.get(rol, "ROL DEL USUARIO: GENERAL")
    
    # Construir mensajes: sistema con rol + usuario
    # PrivateGPT combinará automáticamente este system message con default_query_system_prompt
    # de settings-docker.yaml, así que solo enviamos las instrucciones específicas de filtrado
    messages = [
        {"role": "system", "content": contexto_rol},
        {"role": "user", "content": user_text}
    ]
    
    return messages


def _capitalize_name(name: str) -> str:
    """
    Capitaliza un nombre correctamente: solo la primera letra de cada palabra en mayúscula.
    
    Args:
        name: Nombre a capitalizar
    
    Returns:
        Nombre capitalizado correctamente
    """
    if not name:
        return ""
    
    # Dividir por espacios y capitalizar cada palabra
    palabras = name.strip().split()
    palabras_capitalizadas = []
    
    for palabra in palabras:
        if palabra:
            # Capitalizar: primera letra mayúscula, resto minúsculas
            palabra_capitalizada = palabra[0].upper() + palabra[1:].lower() if len(palabra) > 1 else palabra.upper()
            palabras_capitalizadas.append(palabra_capitalizada)
    
    return " ".join(palabras_capitalizadas)


def _get_student_name(student_data: Optional[Dict]) -> str:
    """
    Obtiene el nombre completo del estudiante desde student_data.
    Busca en múltiples ubicaciones posibles y lo capitaliza correctamente.
    
    Args:
        student_data: Datos completos del usuario desde data_unemi.json
    
    Returns:
        Nombre completo del estudiante capitalizado correctamente o cadena vacía si no se encuentra
    """
    if not student_data:
        return ""
    
    nombre_sin_capitalizar = ""
    
    # Prioridad 1: contexto.credenciales.nombre_completo
    contexto = student_data.get("contexto", {})
    if contexto:
        credenciales = contexto.get("credenciales", {})
        if credenciales:
            nombre = credenciales.get("nombre_completo", "").strip()
            if nombre:
                nombre_sin_capitalizar = nombre
    
    # Prioridad 2: persona.nombres + apellidos
    if not nombre_sin_capitalizar:
        persona = student_data.get("persona", {})
        if persona:
            nombres = persona.get("nombres", "").strip()
            apellido1 = persona.get("apellido1", "").strip()
            apellido2 = persona.get("apellido2", "").strip()
            if nombres:
                nombre_completo = f"{nombres} {apellido1} {apellido2}".strip()
                if nombre_completo:
                    nombre_sin_capitalizar = nombre_completo
    
    # Prioridad 3: datos_personales.nombres + apellidos
    if not nombre_sin_capitalizar:
        datos_personales = contexto.get("datos_personales", {}) if contexto else {}
        if datos_personales:
            nombres = datos_personales.get("nombres", "").strip()
            apellido_paterno = datos_personales.get("apellido_paterno", "").strip()
            apellido_materno = datos_personales.get("apellido_materno", "").strip()
            if nombres:
                nombre_completo = f"{nombres} {apellido_paterno} {apellido_materno}".strip()
                if nombre_completo:
                    nombre_sin_capitalizar = nombre_completo
    
    # Prioridad 4: credenciales directo (sin contexto)
    if not nombre_sin_capitalizar:
        credenciales_directo = student_data.get("credenciales", {})
        if credenciales_directo:
            nombre = credenciales_directo.get("nombre_completo", "").strip()
            if nombre:
                nombre_sin_capitalizar = nombre
    
    # Capitalizar el nombre antes de retornarlo
    return _capitalize_name(nombre_sin_capitalizar)


def _get_current_student_profile(student_data: Dict) -> Optional[Dict]:
    """
    Obtiene el perfil de estudiante activo principal del student_data.
    
    Prioriza perfiles con inscripcionprincipal=True, luego el más reciente.
    """
    if not student_data:
        return None
    
    perfiles = student_data.get("perfiles", [])
    if not perfiles:
        # Intentar desde contexto si viene en formato diferente
        contexto = student_data.get("contexto", {})
        if contexto:
            # Si viene del formato del API, no tiene perfiles directamente
            return None
    
    # Buscar perfiles activos de estudiante
    candidatos = [
        p for p in perfiles
        if p.get("status") and p.get("es_estudiante") and p.get("inscripcionprincipal")
    ]
    
    # Si no hay principal, buscar cualquier estudiante activo
    if not candidatos:
        candidatos = [
            p for p in perfiles
            if p.get("status") and p.get("es_estudiante")
        ]
    
    if not candidatos:
        return None
    
    # Retornar el más reciente (por fecha_creacion)
    return sorted(candidatos, key=lambda p: p.get("fecha_creacion") or "")[-1]


def _answer_solicitudes_balcon(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre las solicitudes del balcón consultando el servicio de solicitudes.
    Usa el servicio de solicitudes para obtener datos actualizados.
    """
    # Obtener ID del solicitante desde student_data
    solicitante_id = None
    if student_data:
        persona = student_data.get("persona", {})
        solicitante_id = persona.get("id")
    
    # Si no hay ID, generar uno basado en cédula
    if not solicitante_id:
        cedula = (
            student_data.get("datos_personales", {}).get("cedula") or
            student_data.get("cedula") or
            "0000000000"
        )
        try:
            solicitante_id = int(cedula[-6:]) if len(cedula) >= 6 else hash(cedula) % 1000000
        except:
            solicitante_id = hash(str(cedula)) % 1000000
    
    # Consultar solicitudes desde el servicio
    try:
        solicitudes = obtener_solicitudes_usuario(solicitante_id)
    except Exception as e:
        print(f"⚠️ [AnswerSolicitudes] Error obteniendo solicitudes: {e}")
        solicitudes = []
    
    # Si no hay solicitudes desde el servicio, intentar desde student_data como fallback
    if not solicitudes:
        solicitudes_data = (
            student_data.get("solicitudes_balcon") or 
            student_data.get("solicitudes") or
            student_data.get("contexto", {}).get("solicitudes") or
            student_data.get("contexto", {}).get("solicitudes_balcon") or
            []
        )
        
        # Convertir formato de student_data al formato esperado
        for s in solicitudes_data:
            solicitudes.append({
                "codigo": s.get("codigo_generado") or s.get("codigo") or "SIN CÓDIGO",
                "estado_display": s.get("estado_display") or s.get("estado") or "Sin estado",
                "nombre_servicio_minus": s.get("tipo") or s.get("descripcion", "")[:50] or "Sin servicio",
                "fecha_creacion": s.get("fecha_creacion") or s.get("fecha") or "",
                "fecha_creacion_v2": s.get("fecha_creacion_v2") or ""
            })
    
    if not solicitudes:
        return {
            "summary": "No tienes solicitudes registradas en el Balcón de Servicios.",
            "has_information": True,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    # Formatear respuesta
    lineas = []
    for s in solicitudes:
        codigo = s.get("codigo", "SIN CÓDIGO")
        estado = s.get("estado_display", "Sin estado")
        servicio = s.get("nombre_servicio_minus", "Solicitud General")
        
        # Formatear fecha
        fecha_display = s.get("fecha_creacion_v2", "")
        if not fecha_display:
            fecha_str = s.get("fecha_creacion", "")
            if fecha_str:
                try:
                    if "T" in fecha_str:
                        fecha_obj = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
                        fecha_display = fecha_obj.strftime("%d/%m/%Y")
                    else:
                        fecha_display = fecha_str[:10]
                except:
                    fecha_display = fecha_str[:10] if len(fecha_str) >= 10 else fecha_str
        
        linea = f"- **{codigo}** · {servicio} · {estado}"
        if fecha_display:
            linea += f" · {fecha_display}"
        lineas.append(linea)
    
    texto = (
        "Aquí tienes tus solicitudes en el Balcón de Servicios:\n\n" +
        "\n".join(lineas) +
        "\n\nPuedes preguntar por el estado de una solicitud específica o ver más detalles."
    )
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def _extract_carrera_data(student_data: Dict) -> Optional[Dict[str, str]]:
    """
    Extrae datos de carrera desde cualquier ubicación posible en student_data.
    
    Returns:
        Dict con keys: carrera, facultad, modalidad, o None si no se encuentra
    """
    # Prioridad 1: informacion_academica directa
    info_academica = student_data.get("informacion_academica", {})
    if info_academica.get("carrera"):
        return {
            "carrera": info_academica.get("carrera", ""),
            "facultad": info_academica.get("facultad", ""),
            "modalidad": info_academica.get("modalidad", "")
        }
    
    # Prioridad 2: contexto.informacion_academica
    contexto = student_data.get("contexto", {})
    if contexto:
        info_academica = contexto.get("informacion_academica", {})
        if info_academica.get("carrera"):
            return {
                "carrera": info_academica.get("carrera", ""),
                "facultad": info_academica.get("facultad", ""),
                "modalidad": info_academica.get("modalidad", "")
            }
    
    # Prioridad 3: perfiles
    perfil = _get_current_student_profile(student_data)
    if perfil:
        return {
            "carrera": perfil.get("carrera_nombre", ""),
            "facultad": perfil.get("facultad_nombre", ""),
            "modalidad": perfil.get("modalidad_nombre", "")
        }
    
    return None


def _build_carrera_response(carrera_data: Dict[str, str], intent_slots: Dict) -> Dict[str, Any]:
    """Construye la respuesta sobre carrera desde datos extraídos."""
    carrera = carrera_data.get("carrera", "").strip()
    facultad = carrera_data.get("facultad", "").strip()
    modalidad = carrera_data.get("modalidad", "").strip()
    
    if not carrera:
        return {
            "summary": "No encuentro información de tu carrera en el sistema. Por favor, verifica que hayas seleccionado el perfil correcto.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    texto = f"Estás estudiando la carrera de **{carrera}**"
    if facultad:
        texto += f" en la **{facultad}**"
    if modalidad:
        texto += f", en modalidad **{modalidad}**"
    texto += "."
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def _answer_carrera_actual(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre la carrera actual usando solo student_data.
    No usa LLM ni PrivateGPT.
    """
    carrera_data = _extract_carrera_data(student_data)
    if not carrera_data:
        return {
            "summary": "No encuentro información de tu carrera en el sistema. Por favor, verifica que hayas seleccionado el perfil correcto.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    return _build_carrera_response(carrera_data, intent_slots)


def _answer_roles_usuario(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre los roles/perfiles del usuario usando solo student_data.
    No usa LLM ni PrivateGPT.
    """
    perfiles = student_data.get("perfiles", [])
    if not perfiles:
        # Intentar desde contexto
        contexto = student_data.get("contexto", {})
        if contexto:
            return {
                "summary": "No encuentro información de perfiles para este usuario.",
                "has_information": False,
                "from_student_data": True,
                "source_pdfs": [],
                "fuentes": [],
                "category": None,
                "subcategory": None,
                "confidence": 1.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": True,
                "intent_slots": intent_slots,
            }
    
    # Filtrar solo perfiles activos
    perfiles_activos = [p for p in perfiles if p.get("status")]
    
    if not perfiles_activos:
        return {
            "summary": "No tienes perfiles activos registrados.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    roles = []
    for p in perfiles_activos:
        tipo = p.get("tipo") or "Sin tipo"
        rol_parts = []
        
        if p.get("es_estudiante"):
            rol_parts.append("Estudiante")
        if p.get("es_profesor"):
            rol_parts.append("Profesor")
        if p.get("es_administrativo"):
            rol_parts.append("Administrativo")
        if p.get("es_externo"):
            rol_parts.append("Externo")
        
        rol_str = " · ".join(rol_parts) if rol_parts else "Sin rol específico"
        roles.append(f"- **{tipo}**: {rol_str}")
    
    texto = (
        f"Tienes {len(perfiles_activos)} perfil(es) activo(s):\n\n" +
        "\n".join(roles)
    )
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def _answer_datos_personales(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre datos personales básicos usando solo student_data.
    Solo muestra campos seguros (whitelist).
    No usa LLM ni PrivateGPT.
    """
    # Obtener datos desde diferentes ubicaciones
    persona = student_data.get("persona", {})
    contexto = student_data.get("contexto", {})
    credenciales = contexto.get("credenciales", {}) if contexto else {}
    datos_personales = contexto.get("datos_personales", {}) if contexto else {}
    
    # Construir respuesta solo con campos seguros
    partes = []
    
    # Nombre
    nombre_completo = (
        credenciales.get("nombre_completo") or
        datos_personales.get("nombres") or
        persona.get("nombres", "")
    )
    if nombre_completo:
        apellido1 = datos_personales.get("apellido_paterno") or persona.get("apellido1", "")
        apellido2 = datos_personales.get("apellido_materno") or persona.get("apellido2", "")
        if apellido1 or apellido2:
            nombre_completo = f"{nombre_completo} {apellido1} {apellido2}".strip()
        partes.append(f"**Nombre completo**: {nombre_completo}")
    
    # Email institucional
    email_inst = (
        datos_personales.get("email") or
        persona.get("emailinst") or
        persona.get("email", "")
    )
    if email_inst:
        partes.append(f"**Email institucional**: {email_inst}")
    
    if not partes:
        return {
            "summary": "No encuentro datos personales disponibles para mostrar.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    texto = "Aquí tienes tus datos personales:\n\n" + "\n".join(partes)
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def _maybe_answer_with_student_data(intent_slots: Dict, student_data: Dict) -> Optional[Dict[str, Any]]:
    """
    Intenta responder usando solo student_data si el intent_code está en DATA_INTENTS.
    
    Retorna None si no se puede responder con datos, o un dict con la respuesta si sí.
    """
    if not student_data:
        return None
    
    intent_code = intent_slots.get("intent_code", "").strip()
    
    if not intent_code or intent_code not in DATA_INTENTS:
        return None
    
    print(f"📊 [Data Intent] Detectado intent_code: '{intent_code}' - Respondiendo con student_data")
    
    try:
        if intent_code == "consultar_solicitudes_balcon":
            return _answer_solicitudes_balcon(student_data, intent_slots)
        
        elif intent_code == "consultar_carrera_actual":
            return _answer_carrera_actual(student_data, intent_slots)
        
        elif intent_code == "consultar_roles_usuario":
            return _answer_roles_usuario(student_data, intent_slots)
        
        elif intent_code == "consultar_datos_personales":
            return _answer_datos_personales(student_data, intent_slots)
        
    except Exception as e:
        import traceback
        print(f"⚠️ [Data Intent] Error al responder con student_data: {e}")
        traceback.print_exc()
        return None
    
    return None


def _detect_stage_from_history(conversation_history: List[Dict]) -> tuple:
    """
    Detecta el stage actual y extrae información del historial.
    
    Returns:
        Tuple (stage, pending_slots, handoff_channel)
    """
    stage = ConversationStage.AWAIT_INTENT.value
    pending_slots = None
    handoff_channel = None
    
    for i, msg in enumerate(reversed(conversation_history)):
        role = msg.get("role") or msg.get("who")
        if role not in ("bot", "assistant"):
            continue
        
        needs_confirm = msg.get("needs_confirmation", False)
        confirmed_status = msg.get("confirmed")
        slot_payload = msg.get("intent_slots")
        needs_related_selection = msg.get("needs_related_request_selection", False)
        needs_handoff_details = msg.get("needs_handoff_details", False)
        
        meta = msg.get("meta") or {}
        if isinstance(meta, dict):
            if not needs_confirm:
                needs_confirm = meta.get("needs_confirmation", False)
            if confirmed_status is None:
                confirmed_status = meta.get("confirmed")
            if not slot_payload:
                slot_payload = meta.get("intent_slots")
            if not needs_related_selection:
                needs_related_selection = meta.get("needs_related_request_selection", False)
            if not needs_handoff_details:
                needs_handoff_details = meta.get("needs_handoff_details", False)
            if not handoff_channel:
                handoff_channel = meta.get("handoff_channel")
        
        handoff_sent_flag = msg.get("handoff_sent")
        if not handoff_sent_flag and isinstance(meta, dict):
            handoff_sent_flag = meta.get("handoff_sent")
        
        if handoff_sent_flag:
            stage = ConversationStage.AWAIT_INTENT.value
            pending_slots = None
            handoff_channel = None
            break
        
        if needs_handoff_details:
            stage = ConversationStage.AWAIT_HANDOFF_DETAILS.value
            if slot_payload:
                pending_slots = slot_payload
            if not handoff_channel:
                handoff_channel = msg.get("handoff_channel")
            break
        
        if confirmed_status is False:
            stage = ConversationStage.AWAIT_INTENT.value
            pending_slots = None
            break
        
        if needs_related_selection:
            stage = ConversationStage.AWAIT_RELATED_REQUEST.value
            if slot_payload:
                pending_slots = slot_payload
            break
        
        if slot_payload:
            pending_slots = slot_payload
            if needs_confirm:
                stage = ConversationStage.AWAIT_CONFIRM.value
            break
        
        if needs_confirm:
            stage = ConversationStage.AWAIT_CONFIRM.value
            history_list = list(conversation_history)
            bot_index = len(history_list) - i - 1
            if bot_index > 0:
                prev_msg = history_list[bot_index - 1]
                prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                if prev_text:
                    slots_prev = interpretar_intencion_principal(prev_text)
                    pending_slots = slots_prev
            break
    
    return stage, pending_slots, handoff_channel


def _recover_intent_slots(conversation_history: List[Dict], pending_slots: Optional[Dict]) -> Optional[Dict]:
    """Recupera intent_slots desde el historial si no están en pending_slots."""
    if pending_slots:
        return pending_slots
    
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role not in ("bot", "assistant"):
            continue
        payload = msg.get("intent_slots")
        if not payload:
            meta = msg.get("meta") or {}
            if isinstance(meta, dict):
                payload = meta.get("intent_slots")
        if payload:
            return payload
    
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("user", "student", "estudiante"):
            prev_text = msg.get("content") or msg.get("text", "")
            if prev_text:
                return interpretar_intencion_principal(prev_text)
    
    return None


def _recover_original_user_request(intent_slots: Optional[Dict], conversation_history: List[Dict], user_text: str) -> str:
    """Recupera el mensaje original del usuario desde diferentes fuentes."""
    if intent_slots:
        original = intent_slots.get("original_user_message", "")
        if original:
            return original
    
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("user", "student", "estudiante"):
            msg_text = msg.get("content") or msg.get("text", "")
            if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text):
                return msg_text
    
    return user_text


def _build_frontend_response(
    *,
    stage: ConversationStage,
    mode: ConversationMode,
    status: ConversationStatus,
    message: str,
    response: str | None = None,
    has_information: bool | None = None,
    fuentes: list | None = None,
    source_pdfs: list | None = None,
    intent_slots: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Construye la respuesta estándar hacia el frontend.
    
    Centraliza la construcción de respuestas con el nuevo contrato:
    - stage: estado de la conversación
    - mode: modo de operación (informativo/operativo/handoff)
    - status: estado de la respuesta (answer/need_details/handoff/error)
    
    Mantiene campos legacy para compatibilidad con el frontend actual.
    """
    base = {
        "stage": stage.value,
        "mode": mode.value,
        "status": status.value,
        "message": message,
        "response": response or message,
        "has_information": has_information,
        "fuentes": fuentes or [],
        "source_pdfs": source_pdfs or [],
        "intent_slots": intent_slots or {},
    }
    
    # Campos legacy para no romper frontend actual
    base.setdefault("needs_confirmation", False)
    base.setdefault("confirmed", True)
    base.setdefault("handoff", False)
    base.setdefault("needs_handoff_details", False)
    base.setdefault("needs_related_request_selection", False)
    base.setdefault("category", None)
    base.setdefault("subcategory", None)
    base.setdefault("confidence", 0.9)
    base.setdefault("campos_requeridos", [])
    
    if extra:
        base.update(extra)
    
    return base


def _build_informative_answer_response(
    resumen: str,
    fuentes: list,
    intent_slots: dict,
    category: str | None = None,
    subcategory: str | None = None
) -> dict:
    """Construye respuesta para consulta informativa con información encontrada."""
    source_pdfs = sorted({f.get("archivo", "") for f in fuentes if f.get("archivo")})
    return _build_frontend_response(
        stage=ConversationStage.ANSWER_READY,
        mode=ConversationMode.INFORMATIVE,
        status=ConversationStatus.ANSWER,
        message=resumen,
        response=resumen,
        has_information=True,
        fuentes=fuentes,
        source_pdfs=source_pdfs,
        intent_slots=intent_slots,
        extra={
            "needs_confirmation": False,
            "confirmed": True,
            "handoff": False,
            "category": category,
            "subcategory": subcategory,
            "confidence": 0.9,
        },
    )


def _build_need_confirm_response(
    confirm_text: str,
    intent_slots: dict,
    category: str | None = None,
    subcategory: str | None = None
) -> dict:
    """Construye respuesta cuando se necesita confirmación del usuario."""
    answer_type = intent_slots.get("answer_type", "informativo")
    mode = ConversationMode.INFORMATIVE if answer_type == "informativo" else ConversationMode.OPERATIVE
    
    return _build_frontend_response(
        stage=ConversationStage.AWAIT_CONFIRM,
        mode=mode,
        status=ConversationStatus.NEED_DETAILS,
        message=confirm_text,
        response=confirm_text,
        has_information=None,
        intent_slots=intent_slots,
        extra={
            "needs_confirmation": True,
            "confirmed": False,
            "category": category,
            "subcategory": subcategory,
            "confidence": 0.85,
        },
    )


def _build_handoff_response_new(
    resumen: str,
    depto_real: str,
    intent_slots: dict | None = None,
    needs_handoff_details: bool = True,
    category: str | None = None,
    subcategory: str | None = None,
    student_data: Optional[Dict] = None
) -> dict:
    """Construye respuesta para handoff (derivación a humano) usando el nuevo contrato."""
    stage = ConversationStage.AWAIT_HANDOFF_DETAILS if needs_handoff_details else ConversationStage.ANSWER_READY
    
    return _build_frontend_response(
        stage=stage,
        mode=ConversationMode.HANDOFF,
        status=ConversationStatus.HANDOFF,
        message=resumen,
        response=resumen,
        has_information=False,
        intent_slots=intent_slots or {},
        extra={
            "handoff": True,
            "handoff_channel": depto_real,
            "handoff_reason": "No se encontró información suficiente",
            "needs_handoff_details": needs_handoff_details,
            "needs_handoff_file": needs_handoff_details,
            "handoff_file_max_size_mb": 4,
            "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],
            "category": category,
            "subcategory": subcategory,
            "confidence": 0.0,
            "department": depto_real,
        },
    )


def _build_error_response(msg: str) -> dict:
    """Construye respuesta de error técnico."""
    return _build_frontend_response(
        stage=ConversationStage.AWAIT_INTENT,
        mode=ConversationMode.INFORMATIVE,
        status=ConversationStatus.ERROR,
        message=msg,
        response=msg,
        has_information=False,
        extra={
            "confidence": 0.0,
        }
    )


def _build_handoff_response(
    depto: str,
    student_data: Optional[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    intent_slots: Optional[Dict],
    reason: str = "Solicitud operativa que requiere intervención humana"
) -> Dict[str, Any]:
    """Construye respuesta de handoff."""
    student_name = _get_student_name(student_data)
    saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
    ask_msg = (
        f"{saludo_nombre}Entiendo que necesitas realizar una solicitud. Para procesarla correctamente, te voy a conectar con mis compañeros humanos del departamento **{depto}**. 💁\n\n"
        f"Para enviar tu solicitud, necesito que:\n"
        f"1. Describes nuevamente tu solicitud con todos los detalles\n"
        f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
    )
    
    return {
        "summary": ask_msg,
        "category": category,
        "subcategory": subcategory,
        "confidence": 0.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "needs_handoff_details": True,
        "needs_handoff_file": True,
        "handoff_channel": depto,
        "confirmed": True,
        "intent_slots": intent_slots or {},
        "handoff": True,
        "handoff_reason": reason
    }


def _handle_confirmation_stage(
    user_text: str,
    pending_slots: Optional[Dict],
    conversation_history: List[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    student_data: Optional[Dict],
    perfil_id: Optional[str] = None
) -> Dict[str, Any]:
    """Maneja la etapa de confirmación cuando el usuario confirma."""
    intent_slots = _recover_intent_slots(conversation_history, pending_slots)
    
    if not intent_slots:
        return {
            "category": None,
            "subcategory": None,
            "confidence": 0.0,
            "summary": "No pude recuperar la intención confirmada. Dime de nuevo tu requerimiento, por favor.",
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": None
        }
    
    original_user_request = _recover_original_user_request(intent_slots, conversation_history, user_text)
    
    # Usar answer_type del LLM si está disponible (V3), sino usar fallback
    answer_type = intent_slots.get("answer_type")
    if not answer_type or answer_type not in ("informativo", "operativo"):
        intent_short = intent_slots.get("intent_short", "")
        answer_type = _classify_answer_type_fallback(intent_short, intent_slots, original_user_request)
        answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)
        
        # Normalizar: mapear "procedimental" a "informativo" (ya no se usa "procedimental")
        if answer_type == "procedimental":
            answer_type = "informativo"
    
    # Guardar answer_type en intent_slots para que esté disponible en todo el flujo
    intent_slots["answer_type"] = answer_type
    if category:
        intent_slots["category"] = category
    if subcategory:
        intent_slots["subcategory"] = subcategory
    
    intent_short = intent_slots.get("intent_short", "")
    print(f"🔍 [Análisis] Intención confirmada: '{intent_short[:80]}'")
    print(f"   Tipo de respuesta: {answer_type} (guardado en intent_slots)")
    
    if answer_type == "operativo":
        # Usar classify_with_heuristics (sin LLM)
        # Esto determina department y channel desde el JSON
        if not category or not subcategory:
            try:
                heuristic_classification = classify_with_heuristics(intent_slots)
                # Nota: classify_with_heuristics no retorna category/subcategory,
                # pero sí department y channel que es lo que necesitamos para handoff
                print(f"📋 [Handoff] Clasificación heurística:")
                print(f"   Department: {heuristic_classification.get('department')}")
                print(f"   Channel: {heuristic_classification.get('channel')}")
            except Exception as e:
                print(f"⚠️ [Handoff] Error en clasificación heurística: {e}")
        
        # Buscar solicitudes relacionadas antes de hacer handoff
        if student_data:
            print(f"🔍 [Handoff] Buscando solicitudes relacionadas...")
            try:
                related_requests_result = find_related_requests(
                    user_request=original_user_request,
                    intent_slots=intent_slots,
                    student_data=student_data,
                    max_results=3
                )
                
                related_requests = related_requests_result.get("related_requests", [])
                no_related = related_requests_result.get("no_related", False)
                
                print(f"📋 [Handoff] Solicitudes relacionadas encontradas: {len(related_requests)}")
                
                # Si hay solicitudes relacionadas, ofrecer relacionar
                if related_requests and not no_related:
                    primer_nombre = obtener_primer_nombre(student_data)
                    mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                    # Solo enviar mensaje introductorio, el frontend renderizará las solicitudes
                    user_message = (
                        f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:"
                    )
                    
                    return {
                        "summary": user_message,
                        "category": category,
                        "subcategory": subcategory,
                        "confidence": 0.9,
                        "campos_requeridos": [],
                        "needs_confirmation": False,
                        "needs_related_request_selection": True,
                        "related_requests": related_requests,
                        "no_related_request_option": True,
                        "confirmed": True,
                        "intent_slots": intent_slots,
                        "source_pdfs": [],
                        "fuentes": [],
                        "has_information": False
                    }
            except Exception as e:
                print(f"⚠️ [Handoff] Error al buscar solicitudes relacionadas: {e}")
                import traceback
                traceback.print_exc()
        
        depto = _determinar_departamento_handoff(
            user_text=original_user_request,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            student_data=student_data
        )
        return _build_handoff_response(depto, student_data, category, subcategory, intent_slots)
    
    if student_data:
        data_answer = _maybe_answer_with_student_data(intent_slots, student_data)
        if data_answer is not None:
            return data_answer
    
    # Si es informativo, buscar solicitudes relacionadas y luego llamar a PrivateGPT
    if answer_type == "informativo":
        related_requests_result = find_related_requests(
            user_request=original_user_request,
            intent_slots=intent_slots,
            student_data=student_data,
            max_results=3
        )
        
        solicitudes_previas = load_student_requests(student_data)
        hay_solicitudes_previas = len(solicitudes_previas) > 0
        
        related_requests = related_requests_result.get("related_requests", [])
        no_related = related_requests_result.get("no_related", False)
        
        if related_requests and not no_related:
            user_message = related_requests_result.get("user_message", "")
            if not user_message:
                primer_nombre = obtener_primer_nombre(student_data)
                mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                user_message = f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:\n\n"
                for i, req in enumerate(related_requests, 1):
                    user_message += f"{i}. {req.get('display', req.get('id', 'Solicitud'))}\n"
                user_message += "\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar."
            
            return {
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.85,
                "summary": user_message,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_related_request_selection": True,
                "related_requests": related_requests,
                "no_related_request_option": True,
                "confirmed": True,
                "intent_slots": intent_slots,
                "reasoning": related_requests_result.get("reasoning", "")
            }
        elif hay_solicitudes_previas and no_related:
            user_message = related_requests_result.get("user_message", "")
            if not user_message:
                primer_nombre = obtener_primer_nombre(student_data)
                mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                user_message = f"{mensaje_inicio}No he encontrado solicitudes relacionadas con tu requerimiento.\n\n¿Deseas continuar sin relacionar tu solicitud con ninguna solicitud previa?"
            
            return {
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.85,
                "summary": user_message,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_related_request_selection": True,
                "related_requests": [],
                "no_related_request_option": True,
                "confirmed": True,
                "intent_slots": intent_slots,
                "reasoning": related_requests_result.get("reasoning", "No hay solicitudes relacionadas")
            }
        
        # Si no hay solicitudes relacionadas o el usuario las rechazó, llamar a PrivateGPT
        try:
            privategpt_result = _call_privategpt_api(
                user_text=original_user_request,
                conversation_history=conversation_history,
                category=None,
                subcategory=None,
                student_data=student_data,
                perfil_id=perfil_id  # Usar perfil_id pasado como parámetro
            )
        except Exception as e:
            print(f"❌ [PrivateGPT] Error: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
        
        has_information = privategpt_result.get("has_information", False)
        response_text = privategpt_result.get("response", "")
        fuentes = privategpt_result.get("fuentes", [])
        
        if has_information:
            return _build_informative_answer_response(
                resumen=response_text,
                fuentes=fuentes,
                intent_slots=intent_slots,
                category=category,
                subcategory=subcategory
            )
        else:
            # No hay información, hacer handoff
            depto = _determinar_departamento_handoff(
                user_text=original_user_request,
                category=category,
                subcategory=subcategory,
                intent_slots=intent_slots,
                student_data=student_data
            )
            
            student_name = _get_student_name(student_data)
            saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
            ask_msg = (
                f"{saludo_nombre}Este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
                f"Para enviar tu solicitud, por favor:\n"
                f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
                f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
                f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
            )
            
            return _build_handoff_response_new(
                resumen=ask_msg,
                depto_real=depto,
                intent_slots=intent_slots,
                needs_handoff_details=True,
                category=category,
                subcategory=subcategory,
                student_data=student_data
            )


def _determinar_departamento_handoff(
    user_text: str,
    category: str = None,
    subcategory: str = None,
    intent_slots: Dict = None,
    student_data: Dict = None
) -> str:
    """
    Determina el departamento al que se debe derivar la solicitud.
    
    Returns:
        Nombre del departamento
    """
    # Intentar obtener departamento desde categoría/subcategoría
    if category and subcategory:
        depto = get_departamento_real(category, subcategory)
        if depto:
            print(f"🏢 [Handoff] Departamento desde categoría: {depto}")
            return depto
    
    # Si hay intent_slots, usar classify_with_heuristics (sin LLM)
    if intent_slots:
        try:
            heuristic_classification = classify_with_heuristics(intent_slots)
            depto_heur = heuristic_classification.get("channel")
            if depto_heur:
                print(f"🏢 [Handoff] Departamento desde heurísticas: {depto_heur}")
                return depto_heur
        except Exception as e:
            print(f"⚠️ [Handoff] Error al usar heurísticas para determinar departamento: {e}")
    
    # Departamento por defecto
    default_depto = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
    print(f"🏢 [Handoff] Usando departamento por defecto: {default_depto}")
    return default_depto


def classify_with_privategpt(
    user_text: str,
    conversation_history: List[Dict] = None,
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None,
    uploaded_file: Any = None,
    perfil_id: str = None
) -> Dict[str, Any]:
    """
    Clasificador principal con flujo restaurado.
    
    Flujo:
    1. Saludo → respuesta de bienvenida
    2. Interpretar intención → pedir confirmación
    3. Usuario confirma → buscar solicitudes relacionadas
    4. Si hay solicitudes relacionadas → mostrar para selección
    5. Si no hay o después de seleccionar → ENVIAR MENSAJE CONFIRMADO a PrivateGPT API
    6. Si has_information=True → devolver respuesta con fuentes
    7. Si has_information=False → determinar departamento y hacer handoff
    
    Args:
        user_text: Mensaje del usuario
        conversation_history: Historial de conversación
        category: Categoría seleccionada (opcional)
        subcategory: Subcategoría seleccionada (opcional)
        student_data: Datos del estudiante (opcional)
        uploaded_file: Archivo subido (opcional)
    
    Returns:
        Dict con la respuesta del chat y metadatos
    """
    print(f"🎯 [classify_with_privategpt] ===== INICIO =====")
    print(f"   Mensaje del usuario: '{user_text[:100]}'")
    print(f"   Categoría: {category}")
    print(f"   Subcategoría: {subcategory}")
    print(f"   Historial: {len(conversation_history or [])} mensajes")
    print(f"   Student data: {'Sí' if student_data else 'No'}")
    
    conversation_history = conversation_history or []
    
    # 1. Procesar archivo subido si existe
    if uploaded_file:
        try:
            client = get_privategpt_client()
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                for chunk in uploaded_file.chunks():
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name
            
            result = client.ingest_file(tmp_path)
            os.unlink(tmp_path)
            
            if result.get("success", False) or "data" in result:
                print(f"[PrivateGPT] ✅ Archivo ingestionado: {uploaded_file.name}")
            else:
                print(f"[PrivateGPT] ⚠️ Error al ingestionar archivo: {result.get('error', 'Unknown')}")
        except Exception as e:
            print(f"[PrivateGPT] ⚠️ Error al procesar archivo: {e}")
    
    # 2. Verificar primero si el mensaje es una confirmación (antes de detectar stage)
    # Esto es importante porque "si" puede ser malinterpretado como nueva intención
    is_confirmation_positive = es_confirmacion_positiva(user_text)
    is_confirmation_negative = es_confirmacion_negativa(user_text)
    
    # Si es una confirmación, buscar en el historial si hay un mensaje del bot con needs_confirmation
    if is_confirmation_positive or is_confirmation_negative:
        history_list = list(conversation_history)
        for i in range(len(history_list) - 1, -1, -1):
            msg = history_list[i]
            role = msg.get("role") or msg.get("who")
            if role in ("bot", "assistant"):
                needs_confirm = msg.get("needs_confirmation", False)
                meta = msg.get("meta") or {}
                if isinstance(meta, dict):
                    needs_confirm = needs_confirm or meta.get("needs_confirmation", False)
                
                if needs_confirm:
                    # Encontramos un mensaje que necesita confirmación, usar esos slots
                    pending_slots = msg.get("intent_slots") or meta.get("intent_slots")
                    if not pending_slots:
                        # Intentar recuperar desde el mensaje anterior del usuario en el historial
                        if i > 0:
                            prev_msg = history_list[i - 1]
                            prev_role = prev_msg.get("role") or prev_msg.get("who")
                            if prev_role in ("user", "student", "estudiante"):
                                prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                                if prev_text and not es_confirmacion_positiva(prev_text) and not es_confirmacion_negativa(prev_text):
                                    pending_slots = interpretar_intencion_principal(prev_text)
                    
                    if is_confirmation_positive:
                        print(f"✅ [Confirmation] Confirmación positiva detectada, usando slots pendientes")
                        return _handle_confirmation_stage(
                            user_text, pending_slots, conversation_history,
                            category, subcategory, student_data, perfil_id
                        )
                    elif is_confirmation_negative:
                        print(f"❌ [Confirmation] Confirmación negativa detectada")
                        return _build_frontend_response(
                            stage=ConversationStage.AWAIT_INTENT,
                            mode=ConversationMode.INFORMATIVE,
                            status=ConversationStatus.ANSWER,
                            message="Gracias por aclarar. Cuéntame nuevamente tu requerimiento en una frase y lo vuelvo a interpretar.",
                            has_information=False,
                            extra={
                                "confidence": 0.0,
                                "confirmed": False
                            }
                        )
                    break
    
    # 3. Detectar estado del flujo desde el historial
    print(f"🔍 [Stage Detection] Analizando historial de {len(conversation_history)} mensajes")
    stage, pending_slots, handoff_channel = _detect_stage_from_history(conversation_history)
    
    print(f"📊 [Stage Detection] Stage final detectado: {stage}")
    if stage == ConversationStage.AWAIT_HANDOFF_DETAILS.value:
        print(f"   handoff_channel: {handoff_channel}")
        print(f"   pending_slots: {pending_slots is not None}")
    
    # 4. Si es saludo, respuesta natural
    if es_greeting(user_text):
        nombre = obtener_primer_nombre(student_data)
        saludo = f"Hola{' ' + nombre if nombre else ''}! 👋 Soy tu asistente virtual del Balcón de Servicios UNEMI. Estoy aquí para ayudarte con tus consultas y solicitudes. ¿En qué puedo asistirte hoy?"
        
        return _build_frontend_response(
            stage=ConversationStage.GREETING,
            mode=ConversationMode.INFORMATIVE,
            status=ConversationStatus.ANSWER,
            message=saludo,
            response=saludo,
            has_information=None,
            intent_slots={},
            extra={
                "is_greeting": True,
                "confidence": 1.0,
            }
        )
    
    # 4. Etapa de confirmación
    if stage == ConversationStage.AWAIT_CONFIRM.value:
        if es_confirmacion_positiva(user_text):
            return _handle_confirmation_stage(
                user_text, pending_slots, conversation_history,
                category, subcategory, student_data, perfil_id
            )
        elif es_confirmacion_negativa(user_text):
            return {
                "category": None,
                "subcategory": None,
                "confidence": 0.0,
                "summary": "Gracias por aclarar. Cuéntame nuevamente tu requerimiento en una frase y lo vuelvo a interpretar.",
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": False
            }
        else:
            # Reinterpretar
            slots = interpretar_intencion_principal(user_text)
            confirm_text = slots.get("confirm_text", "").strip()
            if not confirm_text:
                confirm_text = _confirm_text_from_slots(slots)  # Fallback
            needs_confirmation = slots.get("needs_confirmation", True)
            
            if needs_confirmation:
                return _build_need_confirm_response(confirm_text, slots, category, subcategory)
            else:
                # Si no necesita confirmación, proceder directamente
                return _handle_confirmation_stage(
                    user_text, slots, conversation_history,
                    category, subcategory, student_data, perfil_id
                )
    
    # 5. Etapa de selección de solicitud relacionada
    elif stage == ConversationStage.AWAIT_RELATED_REQUEST.value:
        # El usuario puede seleccionar una solicitud o decir "no hay solicitud relacionada"
        user_text_str = str(user_text) if user_text is not None else ""
        user_text_lower = user_text_str.lower().strip()
        
        # Buscar en el historial las solicitudes relacionadas mostradas
        related_requests_shown = []
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("bot", "assistant"):
                meta = msg.get("meta") or {}
                if isinstance(meta, dict) and meta.get("related_requests"):
                    related_requests_shown = meta.get("related_requests", [])
                    break
        
        # Detectar si el usuario dice "no hay" o similar
        no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", "sin relacionar", "no hay solicitud relacionada"]
        user_said_no_related = any(keyword in user_text_lower for keyword in no_related_keywords)
        
        # Recuperar intent_slots y mensaje confirmado
        intent_slots = pending_slots
        if not intent_slots:
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role not in ("bot", "assistant"):
                    continue
                meta = msg.get("meta") or {}
                if isinstance(meta, dict) and meta.get("intent_slots"):
                    intent_slots = meta.get("intent_slots")
                    break
        
        # Recuperar el mensaje ORIGINAL del usuario (no el interpretado)
        # El mensaje original se guarda en intent_slots["original_user_message"] cuando se interpreta la intención
        original_user_request = None
        
        # Primero, buscar el mensaje original en intent_slots
        if intent_slots:
            original_user_request = intent_slots.get("original_user_message", "")
        
        # Si no está en intent_slots, buscar en el historial (el mensaje antes de la confirmación)
        if not original_user_request:
            for i, msg in enumerate(reversed(conversation_history)):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    needs_confirm = msg.get("needs_confirmation", False)
                    meta = msg.get("meta") or {}
                    if isinstance(meta, dict):
                        needs_confirm = needs_confirm or meta.get("needs_confirmation", False)
                    
                    if needs_confirm:
                        history_list = list(conversation_history)
                        bot_index = len(history_list) - i - 1
                        if bot_index > 0:
                            for j in range(bot_index - 1, -1, -1):
                                prev_msg = history_list[j]
                                prev_role = prev_msg.get("role") or prev_msg.get("who")
                                if prev_role in ("user", "student", "estudiante"):
                                    prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                                    if prev_text and not es_confirmacion_positiva(prev_text) and not es_confirmacion_negativa(prev_text):
                                        original_user_request = prev_text
                                        break
                        if original_user_request:
                            break
        
        # Si aún no se encontró, usar el mensaje actual (última opción)
        if not original_user_request:
            original_user_request = user_text
        
        # Recuperar el answer_type desde intent_slots (ya fue determinado en la confirmación)
        answer_type = intent_slots.get("answer_type") if intent_slots else None
        
        if not answer_type:
            # Si no está en intent_slots, determinarlo ahora (fallback)
            intent_short = intent_slots.get("intent_short", "") if intent_slots else ""
            answer_type = _classify_answer_type_fallback(intent_short, intent_slots, original_user_request)
            answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)
            # Normalizar: mapear "procedimental" a "informativo" (ya no se usa "procedimental")
            if answer_type == "procedimental":
                answer_type = "informativo"
        
        print(f"🔍 [Related Request] Tipo de respuesta: {answer_type} (desde confirmación)")
        
        # Si es operativo, ir directamente al handoff sin pasar por PrivateGPT
        if answer_type == "operativo":
            print(f"✅ [Related Request] Intención operativa, yendo directamente al handoff")
            
            # Recuperar category y subcategory desde intent_slots si están disponibles
            if not category:
                category = intent_slots.get("category") if intent_slots else None
            if not subcategory:
                subcategory = intent_slots.get("subcategory") if intent_slots else None
            
            # Usar classify_with_heuristics (sin LLM)
            if not category or not subcategory:
                try:
                    heuristic_classification = classify_with_heuristics(intent_slots)
                    # Nota: classify_with_heuristics no retorna category/subcategory,
                    # pero sí department y channel que es lo que necesitamos para handoff
                    print(f"📋 [Handoff] Clasificación heurística:")
                    print(f"   Department: {heuristic_classification.get('department')}")
                    print(f"   Channel: {heuristic_classification.get('channel')}")
                except Exception as e:
                    print(f"⚠️ [Handoff] Error en clasificación heurística: {e}")
            
            # Ir directamente al handoff
            depto = _determinar_departamento_handoff(
                user_text=original_user_request,
                category=category,
                subcategory=subcategory,
                intent_slots=intent_slots,
                student_data=student_data
            )
            return _build_handoff_response(depto, student_data, category, subcategory, intent_slots)
        
        # Si es informativo, entonces sí llamar a PrivateGPT
        if user_said_no_related:
            # Usuario eligió continuar sin relacionar → Enviar mensaje confirmado a PrivateGPT API
            print(f"✅ [PrivateGPT] Usuario rechazó solicitudes relacionadas, enviando mensaje confirmado a la API")
            print(f"   Mensaje confirmado: '{original_user_request[:100]}'")
        else:
            # Usuario seleccionó una solicitud relacionada → Enviar mensaje confirmado a PrivateGPT API
            print(f"✅ [PrivateGPT] Usuario seleccionó solicitud relacionada, enviando mensaje confirmado a la API")
            print(f"   Mensaje confirmado: '{original_user_request[:100]}'")
        
        # Enviar mensaje original del usuario a PrivateGPT API (solo para intenciones informativas)
        print(f"   📍 [FLUJO] Punto de entrada (solicitud relacionada - informativo): Llamando a _call_privategpt_api()")
        try:
            privategpt_result = _call_privategpt_api(
                user_text=original_user_request,  # SOLO el mensaje original del usuario, no el interpretado
                conversation_history=conversation_history,
                category=None,  # No enviar categoría a PrivateGPT
                subcategory=None,  # No enviar subcategoría a PrivateGPT
                student_data=student_data,  # Enviar student_data para contexto de rol
                perfil_id=perfil_id  # Enviar perfil_id para identificar el perfil específico
            )
            print(f"   ✅ [FLUJO] _call_privategpt_api() retornó exitosamente")
        except Exception as e:
            print(f"   ❌ [FLUJO] Error al llamar a _call_privategpt_api(): {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
        
        has_information = privategpt_result.get("has_information", False)
        response_text = privategpt_result.get("response", "")
        fuentes = privategpt_result.get("fuentes", [])
        
        # Si tiene información, devolver respuesta con fuentes
        if has_information:
            print(f"✅ [PrivateGPT] Respuesta con información encontrada")
            print(f"   Fuentes agrupadas: {len(fuentes)}")
            
            return _build_informative_answer_response(
                resumen=response_text,
                fuentes=fuentes,
                intent_slots=intent_slots,
                category=category,
                subcategory=subcategory
            )
        
        # Si NO tiene información, determinar departamento y hacer handoff
        print(f"⚠️ [PrivateGPT] No se encontró información, derivando a agente humano")
        
        depto = _determinar_departamento_handoff(
            user_text=original_user_request,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            student_data=student_data
        )
        
        student_name = _get_student_name(student_data)
        saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
        ask_msg = (
            f"{saludo_nombre}Este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
            f"Para enviar tu solicitud, por favor:\n"
            f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
            f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
            f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
        )

        print(f"🔀 [Handoff] Derivando a: {depto}")
        
        return _build_handoff_response_new(
            resumen=ask_msg,
            depto_real=depto,
            intent_slots=intent_slots,
            needs_handoff_details=True,
            category=category,
            subcategory=subcategory,
            student_data=student_data
        )
    
    # 6. Etapa de detalles de handoff (usuario proporciona detalles y archivo para enviar al departamento)
    elif stage == ConversationStage.AWAIT_HANDOFF_DETAILS.value:
        print(f"🔍 [Handoff Details] Procesando stage await_handoff_details")
        print(f"   user_text: '{user_text[:100]}'")
        print(f"   uploaded_file: {uploaded_file.name if uploaded_file else 'None'}")
        print(f"   handoff_channel: {handoff_channel}")
        
        # Recuperar category y subcategory desde el historial si no están disponibles
        if not category or not subcategory:
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    msg_category = msg.get("category") or (msg.get("meta") or {}).get("category")
                    msg_subcategory = msg.get("subcategory") or (msg.get("meta") or {}).get("subcategory")
                    if msg_category and msg_subcategory:
                        if not category:
                            category = msg_category
                        if not subcategory:
                            subcategory = msg_subcategory
                        break
                    # También buscar en intent_slots si está disponible
                    intent_slots_msg = msg.get("intent_slots") or (msg.get("meta") or {}).get("intent_slots")
                    if intent_slots_msg and isinstance(intent_slots_msg, dict):
                        # Intentar obtener desde slots si hay información de categoría
                        if not category and intent_slots_msg.get("category"):
                            category = intent_slots_msg.get("category")
                        if not subcategory and intent_slots_msg.get("subcategory"):
                            subcategory = intent_slots_msg.get("subcategory")
        
        print(f"   category recuperada: {category}")
        print(f"   subcategory recuperada: {subcategory}")
        
        # Verificar si el usuario ya proporcionó detalles y archivo
        details_text = (user_text or "").strip()
        
        # Lógica simple: si hay archivo, proceder (sin validar longitud del texto)
        has_file = uploaded_file is not None
        
        print(f"   details_text: '{details_text}'")
        print(f"   has_file: {has_file}")
        
        if has_file:
            # Usuario proporcionó detalles Y archivo → Enviar handoff y crear solicitud
            print(f"✅ [Handoff] Usuario proporcionó detalles y archivo, enviando solicitud")
            print(f"   Detalles: '{details_text[:100]}'")
            print(f"   Archivo: {uploaded_file.name if uploaded_file else 'N/A'}")
            
            # Establecer thinking_status antes de procesar
            thinking_status_handoff = "Enviando solicitud a mis compañeros humanos"
            
            # Obtener información del estudiante
            student_name = _get_student_name(student_data)
            
            # Obtener ID del solicitante desde student_data
            solicitante_id = None
            cedula = None
            perfil_id = None
            perfil_tipo = None
            
            if student_data:
                persona = student_data.get("persona", {})
                solicitante_id = persona.get("id")
                cedula = (
                    student_data.get("datos_personales", {}).get("cedula") or
                    student_data.get("cedula") or
                    persona.get("cedula")
                )
                
                print(f"🔍 [Handoff] Cédula obtenida: {cedula}")
                print(f"🔍 [Handoff] Solicitante ID: {solicitante_id}")
                
                # Obtener perfil activo
                perfiles = student_data.get("perfiles", [])
                print(f"🔍 [Handoff] Perfiles disponibles: {len(perfiles)}")
                if perfiles:
                    # Buscar perfil principal o el primero
                    perfil_principal = next((p for p in perfiles if p.get("inscripcionprincipal")), perfiles[0])
                    perfil_id = perfil_principal.get("id")
                    print(f"🔍 [Handoff] Perfil ID seleccionado: {perfil_id}")
                    
                    # Obtener tipo de perfil desde inscripción
                    inscripcion = perfil_principal.get("inscripcion", {})
                    if isinstance(inscripcion, dict):
                        carrera = inscripcion.get("carrera", {})
                        if isinstance(carrera, dict):
                            nombre_carrera = carrera.get("nombre", "")
                            modalidad = inscripcion.get("modalidad", {})
                            if isinstance(modalidad, dict):
                                modalidad_nombre = modalidad.get("nombre", "")
                                perfil_tipo = f"{nombre_carrera} {modalidad_nombre}".strip()
                            else:
                                perfil_tipo = nombre_carrera
                    if not perfil_tipo:
                        perfil_tipo = f"Perfil {perfil_id}"
                    print(f"🔍 [Handoff] Perfil tipo: {perfil_tipo}")
                else:
                    print(f"⚠️ [Handoff] No se encontraron perfiles en student_data")
            
            # Si no hay ID, generar uno basado en cédula
            if not solicitante_id:
                if not cedula:
                    cedula = "0000000000"
                try:
                    solicitante_id = int(cedula[-6:]) if len(cedula) >= 6 else hash(cedula) % 1000000
                except:
                    solicitante_id = hash(str(cedula)) % 1000000
            
            # Determinar servicio y sigla desde categoría/subcategoría
            servicio_nombre = subcategory or category or "Solicitud General"
            servicio_sigla = "GEN"
            if category and subcategory:
                # Generar sigla desde subcategoría (primeras 3 letras)
                palabras = subcategory.split()
                if palabras:
                    servicio_sigla = "".join([p[:3].upper() for p in palabras[:2]])[:6]
                else:
                    servicio_sigla = subcategory[:6].upper()
            
            # Crear solicitud en el sistema
            try:
                solicitud = crear_solicitud(
                    solicitante_id=solicitante_id,
                    descripcion=details_text,
                    tipo=2,  # SOLICITUD
                    archivo_solicitud=uploaded_file,
                    servicio_nombre=servicio_nombre,
                    servicio_sigla=servicio_sigla,
                    departamento=handoff_channel or "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
                    agente_id=None,
                    agente_nombre="Sistema",
                    carrera_id=None,
                    requisitos=None,
                    cedula=cedula,
                    perfil_id=perfil_id,
                    perfil_tipo=perfil_tipo
                )
                print(f"✅ [Handoff] Solicitud creada: {solicitud.get('codigo')} (ID: {solicitud.get('id')})")
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"⚠️ [Handoff] Error al crear solicitud: {e}")
                # Continuar aunque falle la creación de solicitud
            
            saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
            
            # Mensaje final de confirmación
            final_message = (
                f"{saludo_nombre}✅ Tu solicitud ha sido enviada exitosamente al departamento **{handoff_channel or 'correspondiente'}**. 📋\n\n"
                f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo. ¿Hay algo mas en que te pueda ayudar?"
            )
            
            print(f"🔀 [Handoff] Solicitud enviada a: {handoff_channel}")
            
            return {
                "summary": final_message,
                "category": category,
                "subcategory": subcategory,
                "confidence": 1.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_handoff_details": False,
                "needs_handoff_file": False,
                "handoff_sent": True,
                "close_chat": True,  # Cerrar el chat después de enviar
                "confirmed": True,
                "handoff": True,
                "handoff_channel": handoff_channel,
                "intent_slots": pending_slots or {},
                "source_pdfs": [],
                "fuentes": [],
                "has_information": False,
                "thinking_status": thinking_status_handoff  # Mostrar mensaje de envío
            }
        elif not has_file:
            # Falta archivo
            print(f"⚠️ [Handoff Details] Usuario no ha subido archivo")
            return {
                "summary": f"Para enviar tu solicitud, necesito que subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.",
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_handoff_details": True,
                "needs_handoff_file": True,
                "handoff_channel": handoff_channel,
                "confirmed": True,
                "intent_slots": pending_slots or {}
            }
        else:
            # No tiene archivo
            print(f"⚠️ [Handoff Details] Usuario no ha subido archivo")
            print(f"   details_text: '{details_text}'")
            return {
                "summary": "Para enviar tu solicitud, necesito que subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.",
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_handoff_details": True,
                "needs_handoff_file": True,
                "handoff_channel": handoff_channel,
                "confirmed": True,
                "intent_slots": pending_slots or {}
            }
    
    # 7. Estado inicial: Interpretar intención y pedir confirmación
    else:
        # Stage por defecto: await_intent o ready - ambos son válidos para interpretar intención
        # await_intent es el stage por defecto cuando no hay ningún stage especial activo
        if stage not in (ConversationStage.AWAIT_INTENT.value, "ready"):
            print(f"⚠️ [ERROR] Stage es '{stage}' pero no se manejó en las condiciones anteriores!")
        
        # Interpretar intención (incluye needs_confirmation, confirm_text, answer_type)
        print(f"🔍 [Intent Parser] Interpretando intención del mensaje: '{user_text[:100]}'")
        print(f"   Stage actual: {stage}")
        intent_slots = interpretar_intencion_principal(user_text)
        
        # Guardar el mensaje original del usuario en los intent_slots (por si acaso no vino del LLM)
        if not intent_slots.get("original_user_message"):
            intent_slots["original_user_message"] = user_text
        
        print(f"📋 [Intent Parser] Intención clasificada:")
        print(f"   original_user_message: {intent_slots.get('original_user_message', 'N/A')[:100]}")
        print(f"   intent_short: {intent_slots.get('intent_short', 'N/A')}")
        print(f"   accion: {intent_slots.get('accion', 'N/A')}")
        print(f"   objeto: {intent_slots.get('objeto', 'N/A')}")
        print(f"   answer_type: {intent_slots.get('answer_type', 'N/A')}")
        print(f"   needs_confirmation: {intent_slots.get('needs_confirmation', 'N/A')}")
        
        # Usar confirm_text del LLM si está disponible, sino usar fallback
        confirm_text = intent_slots.get("confirm_text", "").strip()
        if not confirm_text:
            # Fallback: usar _confirm_text_from_slots solo si el LLM no generó confirm_text
            confirm_text = _confirm_text_from_slots(intent_slots)
            print(f"⚠️ [Intent Parser] confirm_text vacío, usando fallback")
        else:
            print(f"✅ [Intent Parser] Texto de confirmación del LLM: '{confirm_text[:100]}'")
        
        needs_confirmation = intent_slots.get("needs_confirmation", True)
        
        # Si NO necesita confirmación, proceder directamente con la intención
        # (como si el usuario ya hubiera confirmado)
        if not needs_confirmation:
            print(f"✅ [Intent Parser] No necesita confirmación, procediendo directamente con la intención")
            # Tratar como si el usuario hubiera confirmado
            return _handle_confirmation_stage(
                user_text, intent_slots, conversation_history,
                category, subcategory, student_data, perfil_id
            )
        
        # Si SÍ necesita confirmación, mostrar el mensaje de confirmación
        return _build_need_confirm_response(
            confirm_text=confirm_text,
            intent_slots=intent_slots,
            category=category,
            subcategory=subcategory
        )

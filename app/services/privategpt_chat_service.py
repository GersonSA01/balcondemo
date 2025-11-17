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
    
    # NOTA: Se eliminó normalización de texto y contexto de rol para que responda igual que el frontend directo de PrivateGPT
    # Usar texto original sin normalizar (igual que frontend directo)
    print(f"📝 [PrivateGPT] Texto del usuario (sin normalizar): '{user_text[:100]}'")
    
    # Agregar el default_query_system_prompt (igual que frontend directo de PrivateGPT)
    # Este es el mismo system prompt que usa el frontend de PrivateGPT desde settings-docker.yaml
    default_system_prompt = """Eres un asistente RAG. Debes responder exclusivamente con un JSON válido en UTF-8, sin texto adicional, sin backticks y sin bloques de código.

Formato de salida obligatorio (descripción, no imprimirla):
- Un objeto JSON con las claves:
  - has_information: booleano (true o false)
  - response: string en español, claro y natural
  - fuentes: lista de objetos; cada objeto con la clave pagina (string)
- Si no hay información relevante en el contexto:
  - imprime únicamente un objeto JSON con la clave has_information en false
  - no incluyas las claves response ni fuentes en ese caso

FILTRADO CRITICO DE DOCUMENTOS (APLICAR ANTES DE GENERAR JSON):
- Si recibes un contexto del sistema que especifica un ROL del usuario (estudiante, profesor, administrativo, etc.):
  - SOLO usa documentos que sean relevantes para ese ROL específico
  - IGNORA COMPLETAMENTE documentos que sean para otros roles
  - Si el contexto recuperado contiene SOLO información para otros roles, establece has_information=false
  - Si encuentras información mixta, SOLO menciona la parte relevante para el rol especificado en el campo response
- Si NO recibes información de rol, usa todos los documentos disponibles

Reglas:
- No imprimas nada fuera del JSON.
- No inventes datos ni páginas.
- Si no es posible identificar páginas, imprime fuentes como lista vacía.
- Ordena las páginas de menor a mayor y sin duplicados.
- Sé tolerante con errores ortográficos en la consulta; si hay información relacionada en el contexto, has_information debe ser true.

Tu salida debe ser un JSON válido que cumpla exactamente con las claves indicadas.

IMPRIME SOLO EL JSON; cualquier texto fuera del JSON se considera error."""
    
    # Construir mensajes con el system prompt (igual que frontend directo de PrivateGPT)
    messages = [
        {"role": "system", "content": default_system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    # NO agregar session_context (igual que frontend directo de PrivateGPT)
    session_context = None
    
    # Implementar búsqueda prioritaria (igual que frontend directo de PrivateGPT)
    # Primero buscar en archivos UNEMI, luego en el resto si no encuentra información relevante
    try:
        # 1. Listar todos los documentos
        all_docs_response = client.list_documents()
        all_docs = all_docs_response.get("data", []) if all_docs_response else []
        
        # 2. Separar documentos UNEMI del resto
        unemi_docs = [
            doc for doc in all_docs
            if doc.get("doc_metadata", {}).get("file_name", "").lower().startswith("unemi_")
        ]
        other_docs = [
            doc for doc in all_docs
            if not doc.get("doc_metadata", {}).get("file_name", "").lower().startswith("unemi_")
        ]
        
        print(f"🔍 [Búsqueda Prioritaria] Archivos UNEMI: {len(unemi_docs)}, Otros: {len(other_docs)}")
        
        # 3. Buscar primero en archivos UNEMI
        response = None
        if unemi_docs:
            unemi_ids = [doc.get("doc_id") for doc in unemi_docs if doc.get("doc_id")]
            context_filter_unemi = {"docs_ids": unemi_ids} if unemi_ids else None
            
            print(f"🔎 [Búsqueda Prioritaria] Buscando primero en {len(unemi_ids)} archivos UNEMI...")
            response = client.chat_completion(
                messages=messages,
                use_context=True,
                include_sources=True,
                stream=False,
                session_context=session_context,
                context_filter=context_filter_unemi
            )
            
            # Verificar si la respuesta es relevante
            if response and not response.get("error"):
                parsed = PrivateGPTResponseParser.parse(response)
                has_information = parsed.get("has_information", False)
                response_text = parsed.get("response", "")
                fuentes = parsed.get("fuentes", [])
                
                # La respuesta es relevante si tiene información y tiene fuentes o respuesta suficientemente larga
                has_sources = len(fuentes) > 0
                is_relevant = has_information and (has_sources or len(response_text.strip()) >= 30)
                
                print(f"📊 [Búsqueda Prioritaria UNEMI] has_information={has_information}, fuentes={len(fuentes)}, length={len(response_text)}, is_relevant={is_relevant}")
                
                if is_relevant:
                    print(f"✅ [Búsqueda Prioritaria] Información relevante encontrada en archivos UNEMI")
                else:
                    print(f"⚠️ [Búsqueda Prioritaria] No se encontró información relevante en UNEMI, buscando en resto...")
                    response = None  # Continuar con búsqueda en resto
        
        # 4. Si no se encontró información relevante en UNEMI, buscar en el resto
        if not response or response.get("error"):
            if other_docs:
                other_ids = [doc.get("doc_id") for doc in other_docs if doc.get("doc_id")]
                context_filter_other = {"docs_ids": other_ids} if other_ids else None
                
                print(f"🔎 [Búsqueda Prioritaria] Buscando en {len(other_ids)} archivos adicionales...")
                response = client.chat_completion(
                    messages=messages,
                    use_context=True,
                    include_sources=True,
                    stream=False,
                    session_context=session_context,
                    context_filter=context_filter_other
                )
            elif not unemi_docs:
                # Si no hay archivos UNEMI ni otros, buscar en todos
                print(f"🔎 [Búsqueda Prioritaria] No hay archivos categorizados, buscando en todos...")
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
    Extrae el rol del usuario desde student_data.
    
    Funciona tanto con los datos completos de data_unemi.json como con el payload
    reducido que envía el frontend (que suele incluir solo un perfil).
    """
    if not isinstance(student_data, dict):
        return "usuario"
    
    def _collect_perfiles(origen: Optional[Dict]) -> List[Dict]:
        perfiles_colectados: List[Dict] = []
        if not isinstance(origen, dict):
            return perfiles_colectados
        
        posibles_listas = [
            origen.get("perfiles"),
            origen.get("contexto", {}).get("perfiles") if isinstance(origen.get("contexto"), dict) else None,
        ]
        for posible in posibles_listas:
            if isinstance(posible, list):
                perfiles_colectados.extend([p for p in posible if isinstance(p, dict)])
        
        posibles_individuales = [
            origen.get("perfil"),
            origen.get("perfilprincipal"),
            origen.get("perfil_actual"),
            origen.get("contexto", {}).get("perfil") if isinstance(origen.get("contexto"), dict) else None,
            origen.get("contexto", {}).get("perfilprincipal") if isinstance(origen.get("contexto"), dict) else None,
        ]
        for posible in posibles_individuales:
            if isinstance(posible, dict):
                perfiles_colectados.append(posible)
        
        return perfiles_colectados
    
    perfiles = _collect_perfiles(student_data)
    
    # En algunos casos el student_data ES el perfil (payload reducido del frontend)
    perfil_parece_directo = any(
        key in student_data
        for key in ("es_estudiante", "es_profesor", "es_administrativo", "rol", "tipo")
    )
    if perfil_parece_directo:
        perfiles.append(student_data)
    
    # Limpiar duplicados (por id)
    vistos: set[str] = set()
    perfiles_filtrados: list[Dict] = []
    for perfil in perfiles:
        perfil_id_actual = perfil.get("id")
        key = str(perfil_id_actual) if perfil_id_actual is not None else str(id(perfil))
        if key not in vistos:
            vistos.add(key)
            perfiles_filtrados.append(perfil)
    
    if not perfiles_filtrados:
        rol_directo = student_data.get("rol") or student_data.get("role")
        if isinstance(rol_directo, str) and rol_directo.strip():
            return rol_directo.strip().lower()
        return "usuario"
    
    def _perfil_activo(perfil: Dict) -> bool:
        if isinstance(perfil.get("status"), bool):
            return perfil["status"]
        if isinstance(perfil.get("activo"), bool):
            return perfil["activo"]
        return True  # asume activo si no se especifica
    
    perfiles_activos = [p for p in perfiles_filtrados if _perfil_activo(p)]
    if not perfiles_activos:
        perfiles_activos = perfiles_filtrados
    
    def _coincide_id(perfil: Dict, objetivo: Optional[str]) -> bool:
        if objetivo is None:
            return False
        return str(perfil.get("id")) == str(objetivo)
    
    perfil_seleccionado = None
    if perfil_id:
        perfil_seleccionado = next(
            (p for p in perfiles_activos if _coincide_id(p, perfil_id)),
            None
        )
    
    if not perfil_seleccionado:
        perfil_seleccionado = next(
            (p for p in perfiles_activos if p.get("inscripcionprincipal") or p.get("principal")),
            None
        )
    
    if not perfil_seleccionado and perfiles_activos:
        perfil_seleccionado = perfiles_activos[0]
    
    if not perfil_seleccionado:
        return "usuario"
    
    # Determinar rol según flags del perfil
    if perfil_seleccionado.get("es_estudiante"):
        return "estudiante"
    if perfil_seleccionado.get("es_profesor"):
        return "profesor"
    if perfil_seleccionado.get("es_administrativo"):
        return "administrativo"
    if perfil_seleccionado.get("es_externo"):
        return "externo"
    if perfil_seleccionado.get("es_postulanteempleo"):
        return "postulante_empleo"
    if perfil_seleccionado.get("es_postulante"):
        return "postulante"
    
    rol_explicito = perfil_seleccionado.get("rol") or perfil_seleccionado.get("role")
    if isinstance(rol_explicito, str) and rol_explicito.strip():
        return rol_explicito.strip().lower()
    
    # Fallback: usar el tipo del perfil
    tipo = (perfil_seleccionado.get("tipo") or "").upper()
    if "ESTUDIANTE" in tipo or "INGENIER" in tipo or "SOFTWARE" in tipo or "ADMISI" in tipo:
        return "estudiante"
    if "PROFESOR" in tipo:
        return "profesor"
    if "ADMINISTRATIVO" in tipo:
        return "administrativo"
    if "EXTERNO" in tipo:
        return "externo"
    if "POSTULANTE" in tipo:
        return "postulante"
    
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
    # Filtrado crítico deshabilitado - solo indicar el rol sin restricciones
    # Consulta todos los documentos como en el front de PrivateGPT
    contexto_rol = f"ROL DEL USUARIO: {rol.upper()}" if rol and rol != "usuario" else "ROL DEL USUARIO: GENERAL"
    
    # Construir mensajes: sistema con rol + usuario
    # PrivateGPT combinará automáticamente este system message con default_query_system_prompt
    # de settings-docker.yaml. Solo indicamos el rol sin restricciones de filtrado.
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


def _get_requirements_from_history(
    conversation_history: List[Dict],
    prefer_multi_req_confirmation: bool = False
) -> tuple[list[dict], int]:
    """
    Recupera requirements y current_requirement_index desde el historial de conversación.
    
    Args:
        conversation_history: Lista de mensajes del historial
        prefer_multi_req_confirmation: Si True, prioriza mensajes con is_multi_req_confirmation
    
    Returns:
        Tupla (requirements, current_requirement_index)
    """
    requirements = []
    current_req_index = 0
    
    print(f"🔍 [Requirements] Buscando en historial de {len(conversation_history)} mensajes...")
    
    for i, msg in enumerate(reversed(conversation_history)):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            # Buscar en múltiples lugares
            meta = msg.get("meta") or {}
            extra_from_meta = meta.get("extra") or {}
            extra_from_msg = msg.get("extra") or {}
            
            # Priorizar meta.extra sobre extra directo
            extra = extra_from_meta if extra_from_meta else extra_from_msg
            
            # Debug: mostrar qué hay en cada mensaje
            if i < 3:  # Solo mostrar los primeros 3 mensajes del bot para no saturar
                has_reqs = isinstance(extra, dict) and extra.get("requirements")
                has_multi_req = isinstance(extra, dict) and extra.get("is_multi_req_confirmation")
                print(f"   Mensaje {i+1}: role={role}, has_requirements={has_reqs}, is_multi_req_confirmation={has_multi_req}")
                if has_reqs:
                    reqs_count = len(extra.get("requirements", []))
                    print(f"      → Encontrados {reqs_count} requirements en este mensaje")
            
            # También buscar directamente en el nivel superior del mensaje (para compatibilidad)
            reqs_from_top = msg.get("requirements")
            
            if isinstance(extra, dict) and extra.get("requirements"):
                reqs = extra.get("requirements", [])
                idx = extra.get("current_requirement_index", 0)
                
                # Si preferimos multi_req_confirmation y este mensaje lo tiene, usarlo
                if prefer_multi_req_confirmation and extra.get("is_multi_req_confirmation"):
                    requirements = reqs
                    current_req_index = idx
                    print(f"✅ [Requirements] Recuperados desde mensaje con is_multi_req_confirmation: {len(requirements)} requerimientos, índice: {current_req_index}")
                    break
                # Si no hay preferencia o no encontramos uno con multi_req_confirmation, usar el primero encontrado
                elif not prefer_multi_req_confirmation or not requirements:
                    requirements = reqs
                    current_req_index = idx
                    if not prefer_multi_req_confirmation:
                        print(f"✅ [Requirements] Recuperados desde historial: {len(requirements)} requerimientos, índice: {current_req_index}")
                        break
            # Fallback: buscar en el nivel superior del mensaje
            elif reqs_from_top and isinstance(reqs_from_top, list):
                requirements = reqs_from_top
                current_req_index = msg.get("current_requirement_index", 0)
                print(f"✅ [Requirements] Recuperados desde nivel superior del mensaje: {len(requirements)} requerimientos, índice: {current_req_index}")
                if not prefer_multi_req_confirmation:
                    break
    
    if not requirements:
        print(f"⚠️ [Requirements] No se encontraron requirements en el historial")
        # Debug: mostrar estructura de los mensajes del bot
        bot_messages = [msg for msg in conversation_history if (msg.get("role") or msg.get("who")) in ("bot", "assistant")]
        print(f"   Total mensajes del bot en historial: {len(bot_messages)}")
        for i, msg in enumerate(bot_messages[-3:]):  # Últimos 3 mensajes
            print(f"   Mensaje bot {i+1}:")
            print(f"      meta keys: {list(msg.get('meta', {}).keys())}")
            print(f"      extra keys: {list(msg.get('extra', {}).keys())}")
            if msg.get("meta", {}).get("extra"):
                print(f"      meta.extra keys: {list(msg.get('meta', {}).get('extra', {}).keys())}")
    
    return requirements, current_req_index


def _propagate_requirements_to_response(
    response: dict,
    requirements: list[dict],
    current_req_index: int
) -> dict:
    """
    Propaga requirements y current_requirement_index a una respuesta.
    Asegura que estén tanto en extra como en meta.extra.
    
    Args:
        response: Diccionario de respuesta
        requirements: Lista de requerimientos
        current_req_index: Índice del requerimiento actual
    
    Returns:
        Respuesta modificada con requirements propagados
    """
    if not response:
        response = {}
    
    # Asegurar que extra existe
    if "extra" not in response:
        response["extra"] = {}
    
    response["extra"]["requirements"] = requirements
    response["extra"]["current_requirement_index"] = current_req_index
    
    # También guardar en meta para persistencia en historial
    if "meta" not in response:
        response["meta"] = {}
    if "extra" not in response["meta"]:
        response["meta"]["extra"] = {}
    
    response["meta"]["extra"]["requirements"] = requirements
    response["meta"]["extra"]["current_requirement_index"] = current_req_index
    
    return response


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
        
        msg_extra = msg.get("extra") or {}
        if isinstance(msg_extra, dict):
            if not needs_confirm:
                needs_confirm = msg_extra.get("needs_confirmation", False)
            if confirmed_status is None:
                confirmed_status = msg_extra.get("confirmed")
            if not slot_payload:
                slot_payload = msg_extra.get("intent_slots")
            if not needs_related_selection:
                needs_related_selection = msg_extra.get("needs_related_request_selection", False)
            if not needs_handoff_details:
                needs_handoff_details = msg_extra.get("needs_handoff_details", False)
            if not handoff_channel:
                handoff_channel = msg_extra.get("handoff_channel")
        
        handoff_sent_flag = msg.get("handoff_sent")
        if not handoff_sent_flag and isinstance(meta, dict):
            handoff_sent_flag = meta.get("handoff_sent")
        if not handoff_sent_flag and isinstance(msg_extra, dict):
            handoff_sent_flag = msg_extra.get("handoff_sent")
        
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
    
    # Asegurar que meta existe si hay campos que deben ir ahí
    if "meta" not in base:
        base["meta"] = {}
    
    # Si hay extra en la respuesta, también asegurar que esté en meta.extra
    if "extra" in base and isinstance(base["extra"], dict):
        if "extra" not in base["meta"]:
            base["meta"]["extra"] = {}
        # Copiar campos importantes de extra a meta.extra para persistencia
        important_fields = ["requirements", "current_requirement_index", "is_multi_req_confirmation"]
        for field in important_fields:
            if field in base["extra"]:
                base["meta"]["extra"][field] = base["extra"][field]
    
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


def _is_requirement_complete(conversation_history: List[Dict]) -> bool:
    """
    Determina si el requerimiento actual está completo.
    
    Un requerimiento se considera completo cuando:
    1. PrivateGPT respondió con has_information=True (respuesta informativa completa)
    2. Se ejecutó la función para crear una solicitud en el JSON (handoff completado)
    3. El usuario canceló o rechazó explícitamente
    
    Args:
        conversation_history: Historial de la conversación
        
    Returns:
        True si el requerimiento está completo, False si está en progreso
    """
    if not conversation_history:
        return True  # Sin historial, no hay requerimiento activo
    
    # Buscar el último mensaje del bot
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            # Caso 1: Respuesta informativa completa (has_information=True)
            if msg.get("has_information") == True:
                meta = msg.get("meta") or {}
                if isinstance(meta, dict) and meta.get("has_information") == True:
                    return True
                # Verificar si tiene fuentes (indica respuesta completa)
                if msg.get("fuentes") or msg.get("source_pdfs"):
                    return True
                if isinstance(meta, dict) and (meta.get("fuentes") or meta.get("source_pdfs")):
                    return True
            
            # Caso 2: Handoff completado (solicitud creada en JSON)
            # Cuando handoff_sent=True, significa que la solicitud fue creada exitosamente
            meta = msg.get("meta") or {}
            if isinstance(meta, dict):
                if meta.get("handoff_sent") == True:
                    # Solicitud creada exitosamente → requerimiento completo
                    return True
            if msg.get("handoff_sent") == True:
                # Solicitud creada exitosamente → requerimiento completo
                return True
            
            # Caso 3: Respuesta de error o cancelación
            if msg.get("status") == "error" or msg.get("stage") == "await_intent":
                # Si el mensaje anterior del usuario fue una cancelación explícita
                return True
            
            # Si el mensaje tiene stage=ANSWER_READY, el requerimiento está completo
            if msg.get("stage") == ConversationStage.ANSWER_READY.value:
                return True
            
            break
    
    return False


def _is_new_intent(user_text: str, conversation_history: List[Dict]) -> bool:
    """
    Determina si el mensaje del usuario es un nuevo intento/requerimiento.
    
    Un mensaje se considera nuevo intento cuando:
    1. No hay requerimiento activo (requerimiento anterior completado)
    2. El mensaje no es una confirmación (sí/no)
    3. El mensaje no es una respuesta a solicitudes relacionadas
    4. El mensaje no es una continuación del flujo actual (handoff details, etc.)
    5. El mensaje es suficientemente largo y diferente del contexto anterior
    
    Args:
        user_text: Mensaje del usuario
        conversation_history: Historial de la conversación
        
    Returns:
        True si es un nuevo intento, False si es continuación del flujo actual
    """
    user_text_str = str(user_text) if user_text is not None else ""
    user_text_lower = user_text_str.lower().strip()
    
    # Verificar si el requerimiento anterior está completo
    if not _is_requirement_complete(conversation_history):
        # Si hay un requerimiento activo, verificar si el mensaje es una continuación
        # o un nuevo intento
        
        # No es nuevo si es una confirmación
        if es_confirmacion_positiva(user_text) or es_confirmacion_negativa(user_text):
            return False
        
        # No es nuevo si es respuesta a solicitudes relacionadas
        no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                               "sin relacionar", "no hay solicitud relacionada"]
        if any(keyword in user_text_lower for keyword in no_related_keywords):
            return False
        
        # No es nuevo si contiene números (selección de solicitud relacionada)
        if any(str(i) in user_text_str for i in range(1, 10)):
            return False
        
        # Si el mensaje es muy largo (>50 caracteres) y el requerimiento anterior está completo,
        # probablemente es un nuevo intento
        if len(user_text_str) > 50:
            # Verificar si el último mensaje del bot fue una respuesta completa
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    # Si fue respuesta informativa completa, este es nuevo intento
                    if msg.get("has_information") == True:
                        return True
                    if msg.get("fuentes") or msg.get("source_pdfs"):
                        return True
                    break
        
        return False
    
    # Si el requerimiento anterior está completo, este es un nuevo intento
    # (a menos que sea una confirmación o respuesta específica)
    
    # No es nuevo si es una confirmación
    if es_confirmacion_positiva(user_text) or es_confirmacion_negativa(user_text):
        return False
    
    # No es nuevo si es respuesta a solicitudes relacionadas
    no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                           "sin relacionar", "no hay solicitud relacionada"]
    if any(keyword in user_text_lower for keyword in no_related_keywords):
        return False
    
    # Si llegamos aquí, es un nuevo intento
    return True


def _should_reset_conversation_context(conversation_history: List[Dict]) -> bool:
    """
    Determina si debemos resetear el contexto de conversación.
    
    El contexto debe resetearse cuando:
    1. El requerimiento actual está completo
    2. No hay requerimientos pendientes en la cola
    
    Args:
        conversation_history: Historial de la conversación
        
    Returns:
        True si debemos resetear el contexto, False si debemos mantenerlo
    """
    # Verificar si el requerimiento está completo
    if not _is_requirement_complete(conversation_history):
        return False
    
    # Verificar si hay requerimientos pendientes en la cola
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            meta = msg.get("meta") or {}
            extra = meta.get("extra") or {}
            if isinstance(extra, dict):
                requirements = extra.get("requirements", [])
                if requirements:
                    # Verificar si hay requerimientos pendientes
                    pending = [r for r in requirements if r.get("status") == "pending"]
                    if pending:
                        return False  # Hay requerimientos pendientes, no resetear
            break
    
    return True  # No hay requerimientos activos ni pendientes, resetear contexto


def _finish_requirement_and_maybe_next(
    base_response: dict,
    requirements: list[dict],
    current_index: int
) -> dict:
    """
    Marca un requerimiento como terminado y ofrece opciones si hay más pendientes.
    
    Args:
        base_response: Respuesta base que ya se construyó
        requirements: Lista de requerimientos con status
        current_index: Índice del requerimiento actual
    
    Returns:
        Respuesta modificada con opciones de siguiente requerimiento
    """
    print(f"📋 [Finish Requirement] Iniciando con {len(requirements) if requirements else 0} requirements, índice: {current_index}")
    
    if not requirements or current_index >= len(requirements):
        print(f"⚠️ [Finish Requirement] No hay requirements válidos o índice fuera de rango")
        return base_response
    
    # 1) Marcar como terminado
    requirements[current_index]["status"] = "done"
    print(f"✅ [Finish Requirement] Requerimiento {current_index} marcado como 'done': {requirements[current_index].get('summary', 'N/A')}")
    
    remaining = [r for r in requirements if r["status"] == "pending"]
    print(f"📋 [Finish Requirement] Requerimientos pendientes: {len(remaining)}")
    
    # Asegurar que extra existe
    if "extra" not in base_response:
        base_response["extra"] = {}
    
    base_response["extra"]["requirements"] = requirements
    base_response["extra"]["current_requirement_index"] = current_index
    
    # También guardar en meta para que el frontend pueda encontrarlo en el historial
    if "meta" not in base_response:
        base_response["meta"] = {}
    if "extra" not in base_response["meta"]:
        base_response["meta"]["extra"] = {}
    base_response["meta"]["extra"]["requirements"] = requirements
    base_response["meta"]["extra"]["current_requirement_index"] = current_index
    
    if not remaining:
        # No hay más requerimientos pendientes → limpiar estados y cerrar
        print(f"📋 [Finish Requirement] No hay más requerimientos pendientes, limpiando estados")
        base_response["extra"]["has_more_requirements"] = False
        base_response["meta"]["extra"]["has_more_requirements"] = False
        # Limpiar requirements del historial ya que todo está completado
        base_response["extra"]["clear_requirements"] = True
        base_response["meta"]["extra"]["clear_requirements"] = True
        base_response["close_chat"] = False  # No cerrar automáticamente, pero limpiar estados
        return base_response
    
    # Hay más requerimientos pendientes → mostrar menú
    print(f"📋 [Finish Requirement] Hay {len(remaining)} requerimientos pendientes, preparando menú")
    next_req = remaining[0]
    next_summary = next_req.get("summary", "otro requerimiento")
    print(f"📋 [Finish Requirement] Siguiente requerimiento: {next_summary}")
    
    base_response["extra"]["has_more_requirements"] = True
    base_response["extra"]["next_requirement_id"] = next_req["id"]
    # Encontrar el índice del siguiente requerimiento
    next_index_candidates = [i for i, r in enumerate(requirements) if r["id"] == next_req["id"]]
    base_response["extra"]["next_requirement_index"] = next_index_candidates[0] if next_index_candidates else None
    base_response["extra"]["ui_next_step"] = "multi_requirement_menu"
    base_response["extra"]["multi_requirement_options"] = [
        {
            "id": "continue_current",
            "label": "Seguir con este mismo tema"
        },
        {
            "id": "go_next_requirement",
            "label": f"Pasar al siguiente requerimiento: {next_summary}"
        },
        {
            "id": "close_all",
            "label": "No hacer nada más, cerrar"
        }
    ]
    
    # También guardar en meta
    base_response["meta"]["extra"]["has_more_requirements"] = True
    base_response["meta"]["extra"]["next_requirement_id"] = next_req["id"]
    base_response["meta"]["extra"]["next_requirement_index"] = base_response["extra"]["next_requirement_index"]
    base_response["meta"]["extra"]["ui_next_step"] = "multi_requirement_menu"
    base_response["meta"]["extra"]["multi_requirement_options"] = base_response["extra"]["multi_requirement_options"]
    
    print(f"✅ [Finish Requirement] Menú configurado:")
    print(f"   has_more_requirements: {base_response['extra'].get('has_more_requirements')}")
    print(f"   ui_next_step: {base_response['extra'].get('ui_next_step')}")
    print(f"   multi_requirement_options: {len(base_response['extra'].get('multi_requirement_options', []))} opciones")
    
    # IMPORTANTE: Si viene de un handoff, NO agregar el menú al mensaje de handoff
    # El menú se mostrará como un mensaje separado después de que el usuario vea la confirmación
    # El frontend detectará has_more_requirements y mostrará el menú automáticamente
    if base_response.get("handoff_sent"):
        # Para handoff, NO modificar el mensaje - dejarlo solo con la confirmación de solicitud
        print(f"📋 [Finish Requirement] Handoff detectado - menú se mostrará como mensaje separado")
        print(f"   El frontend mostrará el menú automáticamente basado en has_more_requirements=True")
    else:
        # Para flujos normales (no handoff), agregar el menú al mensaje
        menu_message = (
        f"\n\nAdemás, en tu mensaje también mencionaste otro requerimiento:"
        f" **{next_summary}**.\n\n"
            "¿Qué deseas hacer ahora?"
    )
        base_response["message"] += menu_message
        print(f"📋 [Finish Requirement] Mensaje de menú agregado (normal): {menu_message[:100]}")
    
        # Asegurar que response y summary estén actualizados con el mensaje completo
        if base_response.get("message"):
            base_response["response"] = base_response["message"]
            base_response["summary"] = base_response["message"]
        
        print(f"✅ [Finish Requirement] Respuesta final preparada:")
        print(f"   message length: {len(base_response.get('message', ''))}")
        print(f"   response length: {len(base_response.get('response', ''))}")
        print(f"   summary length: {len(base_response.get('summary', ''))}")
        print(f"   extra.has_more_requirements: {base_response.get('extra', {}).get('has_more_requirements')}")
        print(f"   extra.ui_next_step: {base_response.get('extra', {}).get('ui_next_step')}")
        
        return base_response


def _build_handoff_response(
    depto: str,
    student_data: Optional[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    intent_slots: Optional[Dict],
    needs_handoff_details: bool = True,
    reason: str = "Solicitud operativa que requiere intervención humana"
) -> Dict[str, Any]:
    """
    Construye respuesta de handoff unificada.
    Usa _build_handoff_response_new internamente para consistencia.
    """
    student_name = _get_student_name(student_data)
    saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
    
    if needs_handoff_details:
        ask_msg = (
                f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
                f"Para enviar tu solicitud, por favor:\n"
                f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
                f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
                f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
            )
    else:
        ask_msg = (
            f"{saludo_nombre}Tu solicitud ha sido enviada exitosamente al departamento **{depto}**. \n\n"
            f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo."
        )
    
    return _build_handoff_response_new(
        resumen=ask_msg,
        depto_real=depto,
        intent_slots=intent_slots,
        needs_handoff_details=needs_handoff_details,
        category=category,
        subcategory=subcategory,
        student_data=student_data
    )


def _handle_confirmation_stage(
    user_text: str,
    pending_slots: Optional[Dict],
    conversation_history: List[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    student_data: Optional[Dict],
    perfil_id: Optional[str] = None,
    requirements: Optional[List[Dict]] = None,
    current_req_index: int = 0
) -> Dict[str, Any]:
    """Maneja la etapa de confirmación cuando el usuario confirma."""
    intent_slots = _recover_intent_slots(conversation_history, pending_slots)
    
    # Recuperar requirements desde el historial si no se pasaron usando función centralizada
    if requirements is None:
        requirements, current_req_index = _get_requirements_from_history(conversation_history)
    
    if not intent_slots:
        return {
            "category": None,
            "subcategory": None,
            "confidence": 0.0,
            "summary": "⚠️ No puedo procesar tu solicitud en este momento. Por favor, intenta nuevamente o ingresa tu solicitud manualmente a través del formulario del Balcón de Servicios.",
            "message": "⚠️ No puedo procesar tu solicitud en este momento. Por favor, intenta nuevamente o ingresa tu solicitud manualmente a través del formulario del Balcón de Servicios.",
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": None,
            "has_information": False,
        }
    
    # Si hay múltiples requerimientos, usar el original_user_message del requerimiento actual
    # Esto asegura que solo se procese la intención específica del requerimiento actual
    original_user_request = None
    if requirements and current_req_index < len(requirements):
        current_req = requirements[current_req_index]
        req_slots = current_req.get("slots", {})
        req_original = req_slots.get("original_user_message", "")
        if req_original and req_original.strip():
            original_user_request = req_original
            # También actualizar intent_slots para que sea consistente
            intent_slots["original_user_message"] = req_original
            print(f"✅ [Confirmation] Usando original_user_message del requerimiento actual: '{original_user_request[:100]}'")
    
    # Si no se encontró en el requerimiento actual, usar la función helper
    if not original_user_request:
        original_user_request = _recover_original_user_request(intent_slots, conversation_history, user_text)
        # Si aún así se recupera el mensaje completo y hay múltiples requerimientos, usar el intent_short
        if requirements and len(requirements) > 1:
            if original_user_request and len(original_user_request.split()) > 10:  # Mensaje largo probablemente es el completo
                current_req = requirements[current_req_index] if current_req_index < len(requirements) else None
                if current_req:
                    intent_short = current_req.get("summary") or current_req.get("slots", {}).get("intent_short", "")
                    if intent_short:
                        original_user_request = intent_short
                        # También actualizar intent_slots para que sea consistente
                        intent_slots["original_user_message"] = intent_short
                        print(f"✅ [Confirmation] Corrigiendo a intent_short del requerimiento actual: '{original_user_request[:100]}'")
    
    # Usar answer_type del LLM si está disponible (V3), sino usar fallback
    # NOTA: Se eliminó _aplicar_excepciones_informativas para que responda igual que PrivateGPT frontend
    answer_type = intent_slots.get("answer_type")
    if not answer_type or answer_type not in ("informativo", "operativo"):
        intent_short = intent_slots.get("intent_short", "")
        answer_type = _classify_answer_type_fallback(intent_short, intent_slots, original_user_request)
        # answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)  # ELIMINADO
        
        # Asegurar que answer_type sea solo "informativo" o "operativo"
        if answer_type not in ("informativo", "operativo"):
            answer_type = "informativo"  # Fallback por defecto
    
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
            # Verificar que original_user_request sea el del requerimiento actual cuando hay múltiples requerimientos
            if requirements and len(requirements) > 1 and current_req_index < len(requirements):
                current_req_check = requirements[current_req_index]
                req_slots_check = current_req_check.get("slots", {})
                req_original_check = req_slots_check.get("original_user_message", "")
                if req_original_check and req_original_check.strip():
                    # Asegurar que se use el mensaje específico del requerimiento actual
                    if original_user_request != req_original_check:
                        original_user_request = req_original_check
                        intent_slots["original_user_message"] = req_original_check
                        print(f"✅ [Handoff] Corrigiendo original_user_request al del requerimiento actual: '{original_user_request[:100]}'")
            
            print(f"🔍 [Handoff] Llamando a find_related_requests con user_request: '{original_user_request[:100]}'")
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
                    
                    response = {
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
                    
                    # Incluir requirements en extra si están disponibles
                    if requirements:
                        if "extra" not in response:
                            response["extra"] = {}
                        response["extra"]["requirements"] = requirements
                        response["extra"]["current_requirement_index"] = current_req_index
                    
                    return response
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
        # Verificar que original_user_request sea el del requerimiento actual cuando hay múltiples requerimientos
        if requirements and len(requirements) > 1 and current_req_index < len(requirements):
            current_req_check = requirements[current_req_index]
            req_slots_check = current_req_check.get("slots", {})
            req_original_check = req_slots_check.get("original_user_message", "")
            if req_original_check and req_original_check.strip():
                # Asegurar que se use el mensaje específico del requerimiento actual
                if original_user_request != req_original_check:
                    original_user_request = req_original_check
                    intent_slots["original_user_message"] = req_original_check
                    print(f"✅ [Related Requests] Corrigiendo original_user_request al del requerimiento actual: '{original_user_request[:100]}'")
        
        print(f"🔍 [Related Requests] Llamando a find_related_requests con user_request: '{original_user_request[:100]}'")
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
            
            response = {
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.85,
                "summary": user_message,
                "message": user_message,
                "response": user_message,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_related_request_selection": True,
                "related_requests": related_requests,
                "no_related_request_option": True,
                "confirmed": True,
                "intent_slots": intent_slots,
                "reasoning": related_requests_result.get("reasoning", ""),
                "extra": {}
            }
            # Incluir requirements en el extra
            response["extra"]["requirements"] = requirements
            response["extra"]["current_requirement_index"] = current_req_index
            return response
        
        # Si no hay solicitudes relacionadas (no_related=True), continuar directamente con el flujo normal
        # sin mostrar mensaje de confirmación - simplemente llamar a PrivateGPT
        # elif hay_solicitudes_previas and no_related:  # ❌ ELIMINADO - no mostrar mensaje, continuar flujo normal
        
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
            # Usar los requirements que ya están disponibles en la función
            # Si no están disponibles, intentar recuperarlos desde el historial
            # Primero intentar usar los parámetros de la función directamente
            requirements_resp = requirements if requirements else []
            current_req_index_resp = current_req_index
            
            print(f"🔍 [Multi-Req] Buscando requirements - disponibles como parámetro: {len(requirements_resp) if requirements_resp else 0}")
            
            if not requirements_resp:
                # Si no hay requirements disponibles, intentar recuperarlos desde el historial
                # Buscar en mensajes con is_multi_req_confirmation primero, luego en cualquier mensaje con requirements
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("bot", "assistant"):
                        meta = msg.get("meta") or {}
                        extra = meta.get("extra") or {}
                        
                        # También buscar directamente en el mensaje
                        if not extra:
                            extra = msg.get("extra") or {}
                        
                        if isinstance(extra, dict):
                            # Priorizar mensajes con is_multi_req_confirmation
                            if extra.get("is_multi_req_confirmation") and extra.get("requirements"):
                                requirements_resp = extra.get("requirements", [])
                                current_req_index_resp = extra.get("current_requirement_index", 0)
                                print(f"📋 [Multi-Req] Requirements recuperados desde mensaje con is_multi_req_confirmation: {len(requirements_resp)} requerimientos")
                                break
                            # Si no hay is_multi_req_confirmation, buscar cualquier mensaje con requirements
                            elif extra.get("requirements") and not requirements_resp:
                                requirements_resp = extra.get("requirements", [])
                                current_req_index_resp = extra.get("current_requirement_index", 0)
                                print(f"📋 [Multi-Req] Requirements recuperados desde historial: {len(requirements_resp)} requerimientos")
                                # No hacer break aquí para seguir buscando uno con is_multi_req_confirmation
                
                # Si aún no se encontraron, buscar en el mensaje de confirmación múltiple específicamente
                if not requirements_resp:
                    for msg in reversed(conversation_history):
                        role = msg.get("role") or msg.get("who")
                        if role in ("bot", "assistant"):
                            meta = msg.get("meta") or {}
                            extra = meta.get("extra") or {}
                            if isinstance(extra, dict) and extra.get("is_multi_req_confirmation"):
                                requirements_resp = extra.get("requirements", [])
                                current_req_index_resp = extra.get("current_requirement_index", 0)
                                print(f"📋 [Multi-Req] Requirements recuperados desde mensaje de confirmación múltiple: {len(requirements_resp)} requerimientos")
                                break
                
                # Fallback SIMPLE: usar los requirements que ya se recuperaron al inicio de classify_with_privategpt
                if not requirements_resp and requirements:
                    requirements_resp = requirements
                    current_req_index_resp = current_req_index
                    print(f"📋 [Multi-Req] Usando requirements desde contexto actual: {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
            
            response = _build_informative_answer_response(
                resumen=response_text,
                fuentes=fuentes,
                intent_slots=intent_slots,
                category=category,
                subcategory=subcategory
            )
            
            # Incluir requirements en la respuesta antes de llamar a _finish_requirement_and_maybe_next
            if requirements_resp:
                if "extra" not in response:
                    response["extra"] = {}
                response["extra"]["requirements"] = requirements_resp
                response["extra"]["current_requirement_index"] = current_req_index_resp
                print(f"📋 [Multi-Req] Llamando a _finish_requirement_and_maybe_next con {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
            else:
                print(f"⚠️ [Multi-Req] No hay requirements disponibles para mostrar menú")
            
            # Finalizar requerimiento y ofrecer siguiente si hay más
            return _finish_requirement_and_maybe_next(response, requirements_resp, current_req_index_resp)
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
                f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
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
    perfil_id: str = None,
    control_action: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clasificador principal con flujo.
    
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
    
    # Recuperar requirements desde el historial al inicio para tenerlos disponibles en todo el flujo
    requirements, current_req_index = _get_requirements_from_history(
        conversation_history,
        prefer_multi_req_confirmation=True
    )
    print(f"📋 [classify_with_privategpt] Requirements recuperados al inicio: {len(requirements)} requerimientos, índice: {current_req_index}")
    
    # 0. Manejar control_action (acciones sin LLM)
    if control_action:
        # Los requirements ya se recuperaron al inicio, usar esos
        print(f"📋 [Control Action] Usando requirements recuperados al inicio: {len(requirements)} requerimientos")
        
        if control_action == "go_next_requirement":
            # Mover al siguiente requerimiento pendiente
            remaining_indices = [i for i, r in enumerate(requirements) if r.get("status") == "pending"]
            if remaining_indices:
                # Encontrar el siguiente índice después del actual
                next_indices = [i for i in remaining_indices if i > current_req_index]
                if not next_indices:
                    # Si no hay siguiente, tomar el primero pendiente
                    next_indices = [remaining_indices[0]]
                if next_indices:
                    current_req_index = next_indices[0]
                    next_req = requirements[current_req_index]
                    # Usar los slots del siguiente requerimiento directamente (copiar para no mutar el historial)
                    intent_slots = dict(next_req.get("slots", {}) or {})
                    # Asegurar que el original_user_message esté presente desde el requerimiento
                    if not intent_slots.get("original_user_message"):
                        # Usar el mensaje original completo del usuario (ya que el LLM separó las intenciones)
                        # O buscar desde el historial el mensaje original completo
                        for msg in reversed(conversation_history):
                            role = msg.get("role") or msg.get("who")
                            if role in ("user", "student", "estudiante"):
                                prev_text = msg.get("content") or msg.get("text", "")
                                if prev_text and prev_text.strip():
                                    # Buscar el mensaje que contiene múltiples requerimientos
                                    if len(prev_text.split()) > 5:  # Mensaje largo probablemente tiene múltiples requerimientos
                                        intent_slots["original_user_message"] = prev_text
                                        break
                        # Si no se encontró, usar el summary como fallback
                        if not intent_slots.get("original_user_message"):
                            intent_slots["original_user_message"] = next_req.get("summary", "")
                    
                    # Asegurar que answer_type esté presente
                    if not intent_slots.get("answer_type") or intent_slots.get("answer_type") not in ("informativo", "operativo"):
                        # Intentar usar el answer_type guardado en el requerimiento
                        fallback_answer_type = next_req.get("answer_type")
                        if fallback_answer_type in ("informativo", "operativo"):
                            intent_slots["answer_type"] = fallback_answer_type
                        else:
                            intent_short_req = intent_slots.get("intent_short", "")
                            original_msg_req = intent_slots.get("original_user_message", "")
                            answer_type_req = _classify_answer_type_fallback(intent_short_req, intent_slots, original_msg_req)
                            # answer_type_req = _aplicar_excepciones_informativas(answer_type_req, intent_short_req, intent_slots, original_msg_req)  # ELIMINADO
                            # Asegurar que answer_type sea solo "informativo" o "operativo"
                            if answer_type_req not in ("informativo", "operativo"):
                                answer_type_req = "informativo"  # Fallback por defecto
                            intent_slots["answer_type"] = answer_type_req
                    else:
                        # Guardar answer_type en el requerimiento para persistencia futura
                        next_req["answer_type"] = intent_slots.get("answer_type")
                    
                    print(f"🔄 [Multi-Req] Cambiando al requerimiento {current_req_index + 1}: {next_req.get('summary', 'N/A')}")
                    print(f"   original_user_message: {intent_slots.get('original_user_message', 'N/A')[:100]}")
                    print(f"   answer_type: {intent_slots.get('answer_type', 'N/A')}")
                    
                    # Proceder directamente con el flujo usando estos slots
                    # Saltar interpretación de intención ya que tenemos los slots
                    return _handle_confirmation_stage(
                        user_text="",  # No hay texto nuevo, solo usar los slots
                        pending_slots=intent_slots,
                        conversation_history=conversation_history,
                        category=category,
                        subcategory=subcategory,
                        student_data=student_data,
                        perfil_id=perfil_id,
                        requirements=requirements,
                        current_req_index=current_req_index
                    )
            # No hay más requerimientos pendientes
            return _build_frontend_response(
                stage=ConversationStage.AWAIT_INTENT,
                mode=ConversationMode.INFORMATIVE,
                status=ConversationStatus.ANSWER,
                message="No hay más requerimientos pendientes. ¿En qué más puedo ayudarte?",
                has_information=False,
                extra={
                    "has_more_requirements": False,
                    "clear_requirements": True
                }
            )
        elif control_action == "close_all":
            # Limpiar todo y cerrar
            print(f"🔒 [Multi-Req] Usuario decidió cerrar, limpiando estados...")
            return _build_frontend_response(
                stage=ConversationStage.ANSWER_READY,
                mode=ConversationMode.INFORMATIVE,
                status=ConversationStatus.ANSWER,
                message="Perfecto, hemos terminado. Si necesitas algo más, estaré aquí para ayudarte. 👋",
                has_information=False,
                extra={
                    "has_more_requirements": False,
                    "clear_requirements": True,
                    "close_chat": True
                }
            )
        elif control_action == "continue_current":
            # Mantener el requerimiento actual activo
            # El siguiente mensaje del usuario se tratará como follow-up normal
            # Recuperar el requerimiento actual y continuar con él
            if requirements and current_req_index < len(requirements):
                current_req = requirements[current_req_index]
                intent_slots = current_req.get("slots", {})
                print(f"🔄 [Multi-Req] Continuando con el requerimiento actual: {current_req.get('summary', 'N/A')}")
                # Continuar con el flujo normal pero usando los slots del requerimiento actual
                # El user_text se procesará como follow-up
                pass
            else:
                # No hay requerimiento actual válido, continuar flujo normal
                pass
        elif control_action == "new_requirement":
            # Limpiar cola y resetear para nuevo requerimiento
            print(f"🔄 [Multi-Req] Usuario quiere empezar un requerimiento nuevo, limpiando cola...")
            requirements = []
            current_req_index = 0
            # Continuar como mensaje nuevo normal (el user_text se procesará normalmente)
    
    # Recuperar requirements desde el historial si existen
    requirements = []
    current_req_index = 0
    
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            meta = msg.get("meta") or {}
            extra = meta.get("extra") or {}
            if isinstance(extra, dict) and extra.get("requirements"):
                requirements = extra.get("requirements", [])
                current_req_index = extra.get("current_requirement_index", 0)
                break
    
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
    # PERO primero verificar si estamos en stage de selección de solicitudes relacionadas
    # porque "no hay solicitud relacionada" NO es una confirmación negativa
    
    # Detectar stage primero para evitar falsos positivos
    stage_temp, _, _ = _detect_stage_from_history(conversation_history)
    
    # Si estamos en stage de selección de solicitudes relacionadas, NO tratar como confirmación
    if stage_temp == ConversationStage.AWAIT_RELATED_REQUEST.value:
        # Verificar si el usuario dice "no hay solicitud relacionada" o similar
        user_text_lower = str(user_text).lower().strip()
        no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                               "sin relacionar", "no hay solicitud relacionada", "ninguna es", "ninguna solicitud"]
        user_said_no_related = any(keyword in user_text_lower for keyword in no_related_keywords)
        
        if user_said_no_related:
            # NO es una confirmación, es una respuesta a la pregunta de solicitudes relacionadas
            # Continuar con el flujo normal sin tratar como confirmación
            is_confirmation_positive = False
            is_confirmation_negative = False
        else:
            # Puede ser una confirmación normal
            is_confirmation_positive = es_confirmacion_positiva(user_text)
            is_confirmation_negative = es_confirmacion_negativa(user_text)
    else:
        # Verificar confirmaciones normalmente
        is_confirmation_positive = es_confirmacion_positiva(user_text)
        is_confirmation_negative = es_confirmacion_negativa(user_text)
    
    # Si es una confirmación, buscar en el historial si hay un mensaje del bot con needs_confirmation
    if is_confirmation_positive or is_confirmation_negative:
        # PRIMERO verificar si es confirmación de múltiples requerimientos
        is_multi_req_check = False
        requirements_check = []
        current_req_index_check = 0
        for msg_check in reversed(conversation_history):
            role_check = msg_check.get("role") or msg_check.get("who")
            if role_check in ("bot", "assistant"):
                meta_check = msg_check.get("meta") or {}
                extra_check = meta_check.get("extra") or {}
                if isinstance(extra_check, dict):
                    if extra_check.get("is_multi_req_confirmation"):
                        is_multi_req_check = True
                    if extra_check.get("requirements"):
                        requirements_check = extra_check.get("requirements", [])
                        current_req_index_check = extra_check.get("current_requirement_index", 0)
                        if is_multi_req_check:
                            break
        
        # Si es confirmación de múltiples requerimientos, manejar aquí
        if is_multi_req_check and requirements_check:
            if is_confirmation_positive:
                # Usuario dijo "sí" a "¿te parece?" → proceder directamente con el primer requerimiento
                if current_req_index_check < len(requirements_check):
                    first_req = requirements_check[current_req_index_check]
                    first_req_slots = first_req.get("slots", {})
                    needs_confirmation_first = first_req_slots.get("needs_confirmation", False)
                    
                    print(f"✅ [Multi-Req] Usuario confirmó '¿te parece?', procediendo con el primer requerimiento")
                    print(f"   needs_confirmation del primer requerimiento: {needs_confirmation_first}")
                    
                    # Si el primer requerimiento NO necesita confirmación, proceder directamente
                    if not needs_confirmation_first:
                        print(f"✅ [Multi-Req] Primer requerimiento no necesita confirmación, procediendo directamente")
                        return _handle_confirmation_stage(
                            user_text="",  # No hay texto nuevo, solo usar los slots
                            pending_slots=first_req_slots,
                            conversation_history=conversation_history,
                            category=category,
                            subcategory=subcategory,
                            student_data=student_data,
                            perfil_id=perfil_id,
                            requirements=requirements_check,
                            current_req_index=current_req_index_check
                        )
                    else:
                        # Si SÍ necesita confirmación, mostrar confirmación del primer requerimiento
                        confirm_text_first = first_req_slots.get("confirm_text", "").strip()
                        if not confirm_text_first:
                            confirm_text_first = _confirm_text_from_slots(first_req_slots)
                        
                        print(f"✅ [Multi-Req] Primer requerimiento necesita confirmación, mostrando confirmación")
                        
                        response = _build_need_confirm_response(
                            confirm_text=confirm_text_first,
                            intent_slots=first_req_slots,
                            category=category,
                            subcategory=subcategory
                        )
                        
                        # Incluir requirements para mantener el contexto
                        if "extra" not in response:
                            response["extra"] = {}
                        response["extra"]["requirements"] = requirements_check
                        response["extra"]["current_requirement_index"] = current_req_index_check
                        
                        return response
            elif is_confirmation_negative:
                # Usuario dijo "no" a "¿te parece?" → pasar al segundo requerimiento
                if len(requirements_check) > 1:
                    next_index = 1  # Segundo requerimiento (índice 1)
                    if next_index < len(requirements_check):
                        second_req = requirements_check[next_index]
                        second_req_slots = second_req.get("slots", {})
                        confirm_text_second = second_req_slots.get("confirm_text", "").strip()
                        if not confirm_text_second:
                            confirm_text_second = _confirm_text_from_slots(second_req_slots)
                        
                        print(f"❌ [Multi-Req] Usuario rechazó '¿te parece?', pasando al segundo requerimiento")
                        
                        # Mostrar confirmación del segundo requerimiento
                        response = _build_need_confirm_response(
                            confirm_text=confirm_text_second,
                            intent_slots=second_req_slots,
                            category=category,
                            subcategory=subcategory
                        )
                        
                        # Incluir requirements actualizados
                        if "extra" not in response:
                            response["extra"] = {}
                        response["extra"]["requirements"] = requirements_check
                        response["extra"]["current_requirement_index"] = next_index
                        
                        return response
        
        # Si NO es confirmación de múltiples requerimientos, seguir con flujo normal
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
                        # Recuperar requirements desde el historial
                        requirements_confirm = []
                        current_req_index_confirm = 0
                        for msg_req in reversed(conversation_history):
                            role_req = msg_req.get("role") or msg_req.get("who")
                            if role_req in ("bot", "assistant"):
                                meta_req = msg_req.get("meta") or {}
                                extra_req = meta_req.get("extra") or {}
                                if isinstance(extra_req, dict) and extra_req.get("requirements"):
                                    requirements_confirm = extra_req.get("requirements", [])
                                    current_req_index_confirm = extra_req.get("current_requirement_index", 0)
                                    break
                        
                        return _handle_confirmation_stage(
                            user_text, pending_slots, conversation_history,
                            category, subcategory, student_data, perfil_id,
                            requirements_confirm, current_req_index_confirm
                        )
                    elif is_confirmation_negative:
                        print(f"❌ [Confirmation] Confirmación negativa detectada")
                        # Verificar si es confirmación de múltiples requerimientos
                        is_multi_req_neg = False
                        requirements_neg = []
                        current_req_index_neg = 0
                        for msg_check in reversed(conversation_history):
                            role_check = msg_check.get("role") or msg_check.get("who")
                            if role_check in ("bot", "assistant"):
                                meta_check = msg_check.get("meta") or {}
                                extra_check = meta_check.get("extra") or {}
                                if isinstance(extra_check, dict):
                                    if extra_check.get("is_multi_req_confirmation"):
                                        is_multi_req_neg = True
                                    if extra_check.get("requirements"):
                                        requirements_neg = extra_check.get("requirements", [])
                                        current_req_index_neg = extra_check.get("current_requirement_index", 0)
                                        if is_multi_req_neg:
                                            break
                        
                        if is_multi_req_neg and requirements_neg and len(requirements_neg) > 1:
                            # Usuario dijo "no" a "¿te parece?" → pasar al segundo requerimiento
                            next_index = 1  # Segundo requerimiento (índice 1)
                            if next_index < len(requirements_neg):
                                second_req = requirements_neg[next_index]
                                second_req_slots = second_req.get("slots", {})
                                confirm_text_second = second_req_slots.get("confirm_text", "").strip()
                                if not confirm_text_second:
                                    confirm_text_second = _confirm_text_from_slots(second_req_slots)
                                
                                # Mostrar confirmación del segundo requerimiento
                                response = _build_need_confirm_response(
                                    confirm_text=confirm_text_second,
                                    intent_slots=second_req_slots,
                                    category=category,
                                    subcategory=subcategory
                                )
                                
                                # Incluir requirements actualizados
                                if "extra" not in response:
                                    response["extra"] = {}
                                response["extra"]["requirements"] = requirements_neg
                                response["extra"]["current_requirement_index"] = next_index
                                
                                return response
                        
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
    # Si ya detectamos el stage arriba (para evitar falsos positivos), reutilizarlo
    if 'stage_temp' in locals():
        stage, pending_slots, handoff_channel = stage_temp, None, None
        # Re-detectar para obtener pending_slots y handoff_channel completos
        _, pending_slots, handoff_channel = _detect_stage_from_history(conversation_history)
        stage = stage_temp  # Mantener el stage detectado arriba
    else:
        stage, pending_slots, handoff_channel = _detect_stage_from_history(conversation_history)
    
    print(f"📊 [Stage Detection] Stage final detectado: {stage}")
    
    # 6. Etapa de detalles de handoff (usuario proporciona detalles y archivo para enviar al departamento)
    # Verificar PRIMERO si estamos en AWAIT_HANDOFF_DETAILS para procesar directamente
    if stage == ConversationStage.AWAIT_HANDOFF_DETAILS.value:
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
            thinking_status_handoff = "Generando la solicitud"
            
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
                f"{saludo_nombre} Tu solicitud ha sido enviada exitosamente al departamento **{handoff_channel or 'correspondiente'}**. \n\n"
                f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo."
            )
            
            print(f"🔀 [Handoff] Solicitud enviada a: {handoff_channel}")
            
            # Recuperar requirements desde el historial usando función centralizada
            requirements_final, current_req_index_final = _get_requirements_from_history(
                conversation_history,
                prefer_multi_req_confirmation=True
            )
            
            print(f"📋 [Handoff] Requirements recuperados: {len(requirements_final)} requerimientos, índice actual: {current_req_index_final}")
            if requirements_final:
                for i, req in enumerate(requirements_final):
                    print(f"   {i+1}. {req.get('summary', 'N/A')} (status: {req.get('status', 'N/A')})")
            
            # Construir respuesta usando _build_frontend_response para asegurar stage correcto
            response = _build_frontend_response(
                stage=ConversationStage.ANSWER_READY,  # Stage finalizado, no buscar más
                mode=ConversationMode.HANDOFF,
                status=ConversationStatus.ANSWER,
                message=final_message,
                response=final_message,
                has_information=False,
                intent_slots=pending_slots or {},
                extra={
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": 1.0,
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "needs_handoff_details": False,
                    "needs_handoff_file": False,
                    "handoff_sent": True,
                    "close_chat": False,  # No cerrar automáticamente si hay más requerimientos
                    "confirmed": True,
                    "handoff": True,
                    "handoff_channel": handoff_channel,
                    "source_pdfs": [],
                    "fuentes": [],
                    "thinking_status": thinking_status_handoff,  # Mostrar mensaje de envío
                }
            )
            
            # Asegurar que category, subcategory, thinking_status y handoff_sent estén en el nivel superior también
            response["category"] = category
            response["subcategory"] = subcategory
            response["thinking_status"] = thinking_status_handoff  # Asegurar que esté en nivel superior
            response["handoff_sent"] = True  # Asegurar que esté en nivel superior para que _finish_requirement_and_maybe_next lo detecte
            
            # Asegurar propagación de requirements antes de finalizar
            response = _propagate_requirements_to_response(response, requirements_final, current_req_index_final)
            
            # Para handoff, NO llamar a _finish_requirement_and_maybe_next porque agregaría el menú al mensaje
            # En su lugar, marcar el requerimiento como done y configurar los flags para que el frontend muestre el menú como mensaje separado
            if requirements_final and current_req_index_final < len(requirements_final):
                requirements_final[current_req_index_final]["status"] = "done"
                print(f"✅ [Handoff] Requerimiento {current_req_index_final} marcado como 'done': {requirements_final[current_req_index_final].get('summary', 'N/A')}")
                
                remaining = [r for r in requirements_final if r["status"] == "pending"]
                if remaining:
                    # Hay más requerimientos pendientes - configurar flags para que el frontend muestre el menú como mensaje separado
                    next_req = remaining[0]
                    next_summary = next_req.get("summary", "otro requerimiento")
                    
                    response["extra"]["requirements"] = requirements_final
                    response["extra"]["current_requirement_index"] = current_req_index_final
                    response["extra"]["has_more_requirements"] = True
                    response["extra"]["next_requirement_id"] = next_req["id"]
                    next_index_candidates = [i for i, r in enumerate(requirements_final) if r["id"] == next_req["id"]]
                    response["extra"]["next_requirement_index"] = next_index_candidates[0] if next_index_candidates else None
                    response["extra"]["ui_next_step"] = "multi_requirement_menu"
                    response["extra"]["multi_requirement_options"] = [
                        {
                            "id": "continue_current",
                            "label": "Seguir con este mismo tema"
                        },
                        {
                            "id": "go_next_requirement",
                            "label": f"Pasar al siguiente requerimiento: {next_summary}"
                        },
                        {
                            "id": "close_all",
                            "label": "No hacer nada más, cerrar"
                        }
                    ]
                    
                    # También guardar en meta
                    if "meta" not in response:
                        response["meta"] = {}
                    if "extra" not in response["meta"]:
                        response["meta"]["extra"] = {}
                    response["meta"]["extra"]["requirements"] = requirements_final
                    response["meta"]["extra"]["current_requirement_index"] = current_req_index_final
                    response["meta"]["extra"]["has_more_requirements"] = True
                    response["meta"]["extra"]["next_requirement_id"] = next_req["id"]
                    response["meta"]["extra"]["next_requirement_index"] = response["extra"]["next_requirement_index"]
                    response["meta"]["extra"]["ui_next_step"] = "multi_requirement_menu"
                    response["meta"]["extra"]["multi_requirement_options"] = response["extra"]["multi_requirement_options"]
                    
                    print(f"📋 [Handoff] Menú configurado para mostrar como mensaje separado")
                    print(f"   El frontend debería detectar has_more_requirements=True y mostrar el menú automáticamente")
                else:
                    # No hay más requerimientos pendientes
                    response["extra"]["has_more_requirements"] = False
                    response["close_chat"] = False
            
            return response
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
    
    # Verificaciones intermedias (solo si NO estamos en AWAIT_HANDOFF_DETAILS)
    if es_greeting(user_text):
        # 4. Si es saludo, respuesta natural
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
        # Verificar si es una confirmación de múltiples requerimientos
        is_multi_req_confirmation = False
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("bot", "assistant"):
                meta = msg.get("meta") or {}
                extra = meta.get("extra") or {}
                if isinstance(extra, dict) and extra.get("is_multi_req_confirmation"):
                    is_multi_req_confirmation = True
                    # Recuperar requirements desde el historial
                    if not requirements:
                        requirements = extra.get("requirements", [])
                        current_req_index = extra.get("current_requirement_index", 0)
                    break
        
        if is_multi_req_confirmation:
            # Manejar confirmación de múltiples requerimientos
            if es_confirmacion_positiva(user_text):
                # Usuario dijo "sí" → mostrar confirmación del primer requerimiento
                if requirements and current_req_index < len(requirements):
                    first_req = requirements[current_req_index]
                    first_req_slots = first_req.get("slots", {})
                    confirm_text_first = first_req_slots.get("confirm_text", "").strip()
                    if not confirm_text_first:
                        confirm_text_first = _confirm_text_from_slots(first_req_slots)
                    
                    # Mostrar confirmación del primer requerimiento
                    response = _build_need_confirm_response(
                        confirm_text=confirm_text_first,
                        intent_slots=first_req_slots,
                        category=category,
                        subcategory=subcategory
                    )
                    
                    # Incluir requirements para mantener el contexto
                    if "extra" not in response:
                        response["extra"] = {}
                    response["extra"]["requirements"] = requirements
                    response["extra"]["current_requirement_index"] = current_req_index
                    
                    return response
            elif es_confirmacion_negativa(user_text):
                # Usuario dijo "no" → pasar al segundo requerimiento y mostrar su confirmación
                if requirements and len(requirements) > 1:
                    # Mover al siguiente requerimiento
                    next_index = 1  # Segundo requerimiento (índice 1)
                    if next_index < len(requirements):
                        second_req = requirements[next_index]
                        second_req_slots = second_req.get("slots", {})
                        confirm_text_second = second_req_slots.get("confirm_text", "").strip()
                        if not confirm_text_second:
                            confirm_text_second = _confirm_text_from_slots(second_req_slots)
                        
                        # Actualizar current_req_index
                        current_req_index = next_index
                        
                        # Mostrar confirmación del segundo requerimiento
                        response = _build_need_confirm_response(
                            confirm_text=confirm_text_second,
                            intent_slots=second_req_slots,
                            category=category,
                            subcategory=subcategory
                        )
                        
                        # Incluir requirements actualizados
                        if "extra" not in response:
                            response["extra"] = {}
                        response["extra"]["requirements"] = requirements
                        response["extra"]["current_requirement_index"] = current_req_index
                        
                        return response
                    else:
                        return _build_frontend_response(
                            stage=ConversationStage.AWAIT_INTENT,
                            mode=ConversationMode.INFORMATIVE,
                            status=ConversationStatus.ANSWER,
                            message="No hay más requerimientos pendientes. ¿En qué más puedo ayudarte?",
                            has_information=False,
                            extra={"has_more_requirements": False}
                        )
                else:
                    return _build_frontend_response(
                        stage=ConversationStage.AWAIT_INTENT,
                        mode=ConversationMode.INFORMATIVE,
                        status=ConversationStatus.ANSWER,
                        message="Gracias por aclarar. Cuéntame nuevamente tu requerimiento en una frase y lo vuelvo a interpretar.",
                        has_information=False
                    )
        
        # Confirmación normal (no múltiples requerimientos)
        if es_confirmacion_positiva(user_text):
            return _handle_confirmation_stage(
                user_text, pending_slots, conversation_history,
                category, subcategory, student_data, perfil_id,
                requirements, current_req_index
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
    if stage == ConversationStage.AWAIT_RELATED_REQUEST.value:
        # Usar función helper para determinar si es un nuevo intento
        if _is_new_intent(user_text, conversation_history):
            print(f"🔄 [Stage Detection] Detectado nuevo intento usando _is_new_intent(), tratando como nuevo intento")
            # Tratar como nuevo intento - continuar con el flujo normal
            stage = ConversationStage.AWAIT_INTENT.value
        else:
            # El usuario está respondiendo a las solicitudes relacionadas mostradas
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
            no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                                   "sin relacionar", "no hay solicitud relacionada"]
            user_said_no_related = any(keyword in user_text_lower for keyword in no_related_keywords)
            
            # Detectar qué solicitud relacionada seleccionó el usuario (si seleccionó alguna)
            selected_related_request = None
            
            # Si el usuario dice "no hay solicitud relacionada", limpiar cualquier selección anterior
            if user_said_no_related:
                selected_related_request = None
                print(f"🔄 [Related Request] Usuario rechazó solicitudes relacionadas, limpiando selección anterior")
            else:
                # Primero, intentar recuperar la solicitud relacionada seleccionada del historial
                # (por si el usuario ya la seleccionó anteriormente y está haciendo una pregunta de seguimiento)
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("bot", "assistant"):
                        meta = msg.get("meta") or {}
                        extra = meta.get("extra") or {}
                        if isinstance(extra, dict) and extra.get("selected_related_request"):
                            selected_related_request = extra.get("selected_related_request")
                            print(f"✅ [Related Request] Recuperada solicitud relacionada seleccionada del historial: {selected_related_request.get('codigo', 'N/A')}")
                            break
            
            # Si no se encontró en el historial, intentar detectar la selección del mensaje actual
            if not selected_related_request and not user_said_no_related and related_requests_shown:
                # Intentar detectar por número (1, 2, 3, etc.)
                import re
                number_match = re.search(r'\b([1-9])\b', user_text_str)
                if number_match:
                    selected_index = int(number_match.group(1)) - 1
                    if 0 <= selected_index < len(related_requests_shown):
                        selected_related_request = related_requests_shown[selected_index]
                        print(f"✅ [Related Request] Usuario seleccionó solicitud #{selected_index + 1}: {selected_related_request.get('codigo', 'N/A')}")
                
                # Si no se detectó por número, intentar por código
                if not selected_related_request:
                    for req in related_requests_shown:
                        codigo = req.get("codigo", "") or req.get("codigo_generado", "")
                        if codigo and codigo.lower() in user_text_lower:
                            selected_related_request = req
                            print(f"✅ [Related Request] Usuario seleccionó solicitud por código: {codigo}")
                            break
            
            # Recuperar intent_slots y mensaje confirmado
            # Primero buscar el mensaje del bot que mostró las solicitudes relacionadas,
            # porque ese mensaje debería tener el intent_slots con original_user_message
            intent_slots = pending_slots
            if not intent_slots:
                # Buscar primero el mensaje con related_requests (el que mostró las solicitudes relacionadas)
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("bot", "assistant"):
                        meta = msg.get("meta") or {}
                        if isinstance(meta, dict) and meta.get("related_requests"):
                            # Este es el mensaje que mostró las solicitudes relacionadas
                            msg_intent_slots = msg.get("intent_slots") or meta.get("intent_slots")
                            if msg_intent_slots and isinstance(msg_intent_slots, dict):
                                intent_slots = msg_intent_slots
                                print(f"✅ [Related Request] intent_slots recuperado desde mensaje con related_requests")
                                break
                
                # Si no se encontró, buscar cualquier mensaje del bot con intent_slots
            if not intent_slots:
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role not in ("bot", "assistant"):
                        continue
                    meta = msg.get("meta") or {}
                    if isinstance(meta, dict) and meta.get("intent_slots"):
                        intent_slots = meta.get("intent_slots")
                        break
            
            # Recuperar el mensaje ORIGINAL del usuario usando la función helper
            # Esta función busca primero en intent_slots["original_user_message"] que se guarda
            # cuando se interpreta la intención inicial, y se preserva a través del historial
            original_user_request = _recover_original_user_request(intent_slots, conversation_history, user_text)
            
            # Si hay múltiples requerimientos, intentar obtener el original_user_message del requerimiento actual
            # desde los requirements guardados en el historial
            if not original_user_request or original_user_request == user_text:
                # Buscar requirements en el historial para obtener el requerimiento actual
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("bot", "assistant"):
                        meta = msg.get("meta") or {}
                        extra = meta.get("extra") or {}
                        if isinstance(extra, dict) and extra.get("requirements"):
                            requirements_hist = extra.get("requirements", [])
                            current_req_index_hist = extra.get("current_requirement_index", 0)
                            if requirements_hist and current_req_index_hist < len(requirements_hist):
                                current_req_hist = requirements_hist[current_req_index_hist]
                                req_slots = current_req_hist.get("slots", {})
                                req_original = req_slots.get("original_user_message", "")
                                if req_original and req_original.strip() and req_original != user_text:
                                    original_user_request = req_original
                                    print(f"✅ [Related Request] Mensaje original del requerimiento actual desde historial: '{original_user_request[:100]}'")
                                    break
            
            # Si aún no tenemos el mensaje original y tenemos intent_slots, intentar obtenerlo directamente
            if not original_user_request or original_user_request == user_text:
                if intent_slots and isinstance(intent_slots, dict):
                    direct_original = intent_slots.get("original_user_message", "")
                    if direct_original and direct_original.strip() and direct_original != user_text:
                        original_user_request = direct_original
                        print(f"✅ [Related Request] Mensaje original obtenido directamente desde intent_slots: '{original_user_request[:100]}'")
            
            # Si el usuario dijo "no hay solicitud relacionada" y el mensaje recuperado es el texto actual,
            # buscar más atrás en el historial para encontrar el mensaje original
            if user_said_no_related and original_user_request == user_text:
                print(f"⚠️ [Related Request] El mensaje recuperado es la respuesta actual, buscando mensaje original anterior...")
                # Primero intentar obtener el original_user_message desde el mensaje con related_requests
                history_list = list(conversation_history)
                for i, msg in enumerate(reversed(history_list)):
                    role = msg.get("role") or msg.get("who")
                    if role in ("bot", "assistant"):
                        meta = msg.get("meta") or {}
                        if isinstance(meta, dict) and meta.get("related_requests"):
                            # Este es el mensaje que mostró las solicitudes relacionadas
                            # Intentar obtener original_user_message desde su intent_slots
                            msg_intent_slots = msg.get("intent_slots") or meta.get("intent_slots")
                            if msg_intent_slots and isinstance(msg_intent_slots, dict):
                                msg_original = msg_intent_slots.get("original_user_message", "")
                                if msg_original and msg_original.strip() and msg_original != user_text:
                                    original_user_request = msg_original
                                    print(f"✅ [Related Request] Mensaje original recuperado desde mensaje con related_requests: '{original_user_request[:100]}'")
                                    break
                            # Si no está en intent_slots, buscar el mensaje del usuario ANTES de este mensaje del bot
                            if original_user_request == user_text:
                                # Calcular el índice real en la lista (reversed)
                                bot_index = len(history_list) - i - 1
                                if bot_index > 0:
                                    for j in range(bot_index - 1, -1, -1):
                                        prev_msg = history_list[j]
                                        prev_role = prev_msg.get("role") or prev_msg.get("who")
                                        if prev_role in ("user", "student", "estudiante"):
                                            prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                                            if prev_text and prev_text.strip():
                                                # Saltarse solo confirmaciones, no verificamos palabras clave
                                                is_confirm = es_confirmacion_positiva(prev_text) or es_confirmacion_negativa(prev_text)
                                                if not is_confirm:
                                                    original_user_request = prev_text
                                                    print(f"✅ [Related Request] Mensaje original encontrado antes de solicitudes relacionadas: '{original_user_request[:100]}'")
                                                    break
                                    if original_user_request and original_user_request != user_text:
                                        break
                            if original_user_request and original_user_request != user_text:
                                break
            
                # Si aún no encontramos un mensaje válido, buscar en intent_slots de cualquier mensaje del bot
                if not original_user_request or original_user_request == user_text:
                    # Buscar el mensaje del bot que pidió confirmación y obtener intent_slots desde ahí
                    for msg in reversed(conversation_history):
                        role = msg.get("role") or msg.get("who")
                        if role in ("bot", "assistant"):
                            meta = msg.get("meta") or {}
                            msg_intent_slots = msg.get("intent_slots") or meta.get("intent_slots")
                            if msg_intent_slots and isinstance(msg_intent_slots, dict):
                                msg_original = msg_intent_slots.get("original_user_message", "")
                                if msg_original and msg_original.strip() and msg_original != user_text:
                                    original_user_request = msg_original
                                    print(f"✅ [Related Request] Mensaje original recuperado desde intent_slots del historial: '{original_user_request[:100]}'")
                                    break
                        if original_user_request and original_user_request != user_text:
                            break
            
            # Recuperar el answer_type desde intent_slots (ya fue determinado en la confirmación)
            answer_type = intent_slots.get("answer_type") if intent_slots else None
            
            if not answer_type:
                # Si no está en intent_slots, determinarlo ahora (fallback)
                intent_short = intent_slots.get("intent_short", "") if intent_slots else ""
                answer_type = _classify_answer_type_fallback(intent_short, intent_slots, original_user_request)
                # answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)  # ELIMINADO
                # Asegurar que answer_type sea solo "informativo" o "operativo"
                if answer_type not in ("informativo", "operativo"):
                    answer_type = "informativo"  # Fallback por defecto
            
            # Procesar la respuesta a solicitudes relacionadas
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
                response = _build_handoff_response(depto, student_data, category, subcategory, intent_slots)
                # Finalizar requerimiento y ofrecer siguiente si hay más
                return _finish_requirement_and_maybe_next(response, requirements, current_req_index)
            
            # Si es informativo, entonces sí llamar a PrivateGPT
            if user_said_no_related:
                # Usuario eligió continuar sin relacionar → Enviar mensaje confirmado a PrivateGPT API
                # El mensaje original ya fue recuperado arriba con la lógica mejorada
                if not original_user_request or not original_user_request.strip() or original_user_request == user_text:
                    print(f"❌ [PrivateGPT] ERROR: No se pudo encontrar mensaje original válido para enviar a PrivateGPT")
                    print(f"   Mensaje recuperado: '{original_user_request[:100] if original_user_request else 'None'}'")
                    print(f"   Mensaje actual del usuario: '{user_text[:100]}'")
                    # Retornar un error o mensaje apropiado
                    return {
                        "category": category,
                        "subcategory": subcategory,
                        "confidence": 0.0,
                        "summary": "Lo siento, no pude encontrar tu mensaje original. Por favor, vuelve a describir tu requerimiento.",
                        "campos_requeridos": [],
                        "needs_confirmation": False,
                        "confirmed": False
                    }
                
                # Verificar si hay múltiples requerimientos y usar el mensaje específico del requerimiento actual
                # Recuperar requirements desde el historial si no están disponibles como parámetros
                requirements_check = requirements if requirements else []
                current_req_index_check = current_req_index
                
                if not requirements_check:
                    # Buscar requirements en el historial
                    for msg in reversed(conversation_history):
                        role = msg.get("role") or msg.get("who")
                        if role in ("bot", "assistant"):
                            meta = msg.get("meta") or {}
                            extra = meta.get("extra") or {}
                            if isinstance(extra, dict) and extra.get("requirements"):
                                requirements_check = extra.get("requirements", [])
                                current_req_index_check = extra.get("current_requirement_index", 0)
                                break
                
                # Si hay múltiples requerimientos, usar el mensaje específico del requerimiento actual
                if requirements_check and len(requirements_check) > 1 and current_req_index_check < len(requirements_check):
                    current_req_check = requirements_check[current_req_index_check]
                    req_slots_check = current_req_check.get("slots", {})
                    req_original_check = req_slots_check.get("original_user_message", "")
                    if req_original_check and req_original_check.strip():
                        # Verificar si el mensaje recuperado es el completo (más de 10 palabras probablemente es el completo)
                        if original_user_request and len(original_user_request.split()) > 10:
                            original_user_request = req_original_check
                            print(f"✅ [PrivateGPT] Corrigiendo a mensaje específico del requerimiento actual: '{original_user_request[:100]}'")
                        elif not original_user_request or original_user_request == user_text:
                            original_user_request = req_original_check
                            print(f"✅ [PrivateGPT] Usando mensaje específico del requerimiento actual: '{original_user_request[:100]}'")
                
                print(f"✅ [PrivateGPT] Usuario rechazó solicitudes relacionadas, enviando mensaje original a la API")
                print(f"   Mensaje original recuperado: '{original_user_request[:100]}'")
                # Construir mensaje sin contexto de solicitud relacionada
                message_for_privategpt = original_user_request
            else:
                # Usuario seleccionó una solicitud relacionada → Enviar mensaje confirmado a PrivateGPT API
                if selected_related_request:
                    # Verificar si hay múltiples requerimientos y usar el mensaje específico del requerimiento actual
                    # Recuperar requirements desde el historial si no están disponibles como parámetros
                    requirements_check = requirements if requirements else []
                    current_req_index_check = current_req_index
                    
                    if not requirements_check:
                        # Buscar requirements en el historial
                        for msg in reversed(conversation_history):
                            role = msg.get("role") or msg.get("who")
                            if role in ("bot", "assistant"):
                                meta = msg.get("meta") or {}
                                extra = meta.get("extra") or {}
                                if isinstance(extra, dict) and extra.get("requirements"):
                                    requirements_check = extra.get("requirements", [])
                                    current_req_index_check = extra.get("current_requirement_index", 0)
                                    break
                    
                    # Si hay múltiples requerimientos, usar el mensaje específico del requerimiento actual
                    if requirements_check and len(requirements_check) > 1 and current_req_index_check < len(requirements_check):
                        current_req_check = requirements_check[current_req_index_check]
                        req_slots_check = current_req_check.get("slots", {})
                        req_original_check = req_slots_check.get("original_user_message", "")
                        if req_original_check and req_original_check.strip():
                            # Verificar si el mensaje recuperado es el completo (más de 10 palabras probablemente es el completo)
                            if original_user_request and len(original_user_request.split()) > 10:
                                original_user_request = req_original_check
                                print(f"✅ [PrivateGPT] Corrigiendo a mensaje específico del requerimiento actual (con solicitud relacionada): '{original_user_request[:100]}'")
                            elif not original_user_request or original_user_request == user_text:
                                original_user_request = req_original_check
                                print(f"✅ [PrivateGPT] Usando mensaje específico del requerimiento actual (con solicitud relacionada): '{original_user_request[:100]}'")
                    
                    print(f"✅ [PrivateGPT] Usuario seleccionó solicitud relacionada: {selected_related_request.get('codigo', 'N/A')}")
                    # Construir mensaje enriquecido con información de la solicitud relacionada seleccionada
                    codigo_seleccionado = selected_related_request.get("codigo", "") or selected_related_request.get("codigo_generado", "")
                    descripcion_seleccionada = selected_related_request.get("descripcion", "")[:200]  # Primeros 200 caracteres
                    
                    message_for_privategpt = (
                        f"{original_user_request}\n\n"
                        f"[CONTEXTO: Solicitud relacionada seleccionada - Código: {codigo_seleccionado}]\n"
                        f"Descripción de la solicitud relacionada: {descripcion_seleccionada}"
                    )
                    print(f"   Mensaje enriquecido con solicitud relacionada: '{message_for_privategpt[:150]}...'")
                else:
                    # No se detectó selección específica, usar mensaje original
                    print(f"✅ [PrivateGPT] Usuario respondió a solicitudes relacionadas pero no se detectó selección específica")
                    message_for_privategpt = original_user_request
            
            # Guardar la solicitud relacionada seleccionada en el historial para referencia futura
            if selected_related_request:
                # Crear un mensaje del sistema que guarde la selección
                selection_message = {
                    "role": "system",
                    "content": f"Usuario seleccionó solicitud relacionada: {selected_related_request.get('codigo', 'N/A')} - {selected_related_request.get('descripcion', '')[:100]}",
                    "meta": {
                        "selected_related_request": selected_related_request,
                        "selected_related_request_id": selected_related_request.get("id"),
                        "selected_related_request_codigo": selected_related_request.get("codigo") or selected_related_request.get("codigo_generado", "")
                    }
                }
                # Agregar al historial temporalmente para que esté disponible en el contexto
                conversation_history_with_selection = conversation_history + [selection_message]
            else:
                conversation_history_with_selection = conversation_history
            
            # Enviar mensaje original del usuario a PrivateGPT API (solo para intenciones informativas)
            print(f"   📍 [FLUJO] Punto de entrada (solicitud relacionada - informativo): Llamando a _call_privategpt_api()")
            try:
                privategpt_result = _call_privategpt_api(
                    user_text=message_for_privategpt,  # Mensaje enriquecido con contexto de solicitud relacionada si aplica
                    conversation_history=conversation_history_with_selection,  # Historial con información de selección
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
                
                # Recuperar requirements desde el historial usando función centralizada
                requirements_resp, current_req_index_resp = _get_requirements_from_history(
                    conversation_history,
                    prefer_multi_req_confirmation=True
                )
                
                # Fallback: usar los requirements que ya se recuperaron al inicio de classify_with_privategpt
                if not requirements_resp and requirements:
                    requirements_resp = requirements
                    current_req_index_resp = current_req_index
                    print(f"📋 [Multi-Req] Usando requirements desde contexto actual: {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
                
                response = _build_informative_answer_response(
                    resumen=response_text,
                    fuentes=fuentes,
                    intent_slots=intent_slots,
                    category=category,
                    subcategory=subcategory
                )
                
                # Guardar información de la solicitud relacionada seleccionada en la respuesta
                if selected_related_request:
                    if "extra" not in response:
                        response["extra"] = {}
                    response["extra"]["selected_related_request"] = selected_related_request
                    response["extra"]["selected_related_request_id"] = selected_related_request.get("id")
                    response["extra"]["selected_related_request_codigo"] = selected_related_request.get("codigo") or selected_related_request.get("codigo_generado", "")
                    # También guardar en meta para persistencia en historial
                    if "meta" not in response:
                        response["meta"] = {}
                    if "extra" not in response["meta"]:
                        response["meta"]["extra"] = {}
                    response["meta"]["extra"]["selected_related_request"] = selected_related_request
                    response["meta"]["extra"]["selected_related_request_id"] = selected_related_request.get("id")
                    response["meta"]["extra"]["selected_related_request_codigo"] = selected_related_request.get("codigo") or selected_related_request.get("codigo_generado", "")
                
                # Finalizar requerimiento y ofrecer siguiente si hay más
                if requirements_resp:
                    # Asegurar propagación de requirements antes de finalizar
                    response = _propagate_requirements_to_response(response, requirements_resp, current_req_index_resp)
                    
                    print(f"📋 [Multi-Req] Llamando a _finish_requirement_and_maybe_next con {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
                    return _finish_requirement_and_maybe_next(response, requirements_resp, current_req_index_resp)
                else:
                    print(f"⚠️ [Multi-Req] No hay requirements disponibles, retornando respuesta sin menú")
                    return response
            
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
                f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
                f"Para enviar tu solicitud, por favor:\n"
                f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
                f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
                f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
            )

            print(f"🔀 [Handoff] Derivando a: {depto}")
            
            response = _build_handoff_response_new(
                resumen=ask_msg,
                depto_real=depto,
                intent_slots=intent_slots,
                needs_handoff_details=True,
                category=category,
                subcategory=subcategory,
                student_data=student_data
            )
            # Usar los requirements recuperados al inicio de classify_with_privategpt
            # Si no están disponibles, intentar recuperarlos del historial
            requirements_resp = requirements if requirements else []
            current_req_index_resp = current_req_index
            
            if not requirements_resp:
                print(f"⚠️ [Handoff] No hay requirements en contexto actual, buscando en historial...")
                requirements_resp, current_req_index_resp = _get_requirements_from_history(
                    conversation_history,
                    prefer_multi_req_confirmation=True
                )
                if not requirements_resp:
                    # Último intento sin preferencia
                    requirements_resp, current_req_index_resp = _get_requirements_from_history(
                        conversation_history,
                        prefer_multi_req_confirmation=False
                    )
            
            print(f"📋 [Handoff] Requirements para finalizar: {len(requirements_resp) if requirements_resp else 0} requerimientos, índice: {current_req_index_resp}")
            if requirements_resp:
                for i, req in enumerate(requirements_resp):
                    print(f"   {i+1}. {req.get('summary', 'N/A')} (status: {req.get('status', 'N/A')})")
            
            # IMPORTANTE: NO llamar a _finish_requirement_and_maybe_next aquí porque agregaría el menú al mensaje inicial de handoff
            # El menú solo debe aparecer DESPUÉS de que se confirme la creación de la solicitud
            # Por ahora, solo propagar los requirements para mantener el contexto, pero NO mostrar el menú todavía
            response = _propagate_requirements_to_response(response, requirements_resp, current_req_index_resp)
            
            print(f"📋 [Handoff] Mensaje inicial de handoff construido - menú se mostrará después de confirmar la solicitud")
            
            return response
    
    # 7. Estado inicial: Interpretar intención y pedir confirmación
    if stage not in (
        ConversationStage.AWAIT_HANDOFF_DETAILS.value,
        ConversationStage.AWAIT_CONFIRM.value,
        ConversationStage.AWAIT_RELATED_REQUEST.value,
    ):
        # Stage por defecto: await_intent o ready - ambos son válidos para interpretar intención
        # await_intent es el stage por defecto cuando no hay ningún stage especial activo
        if stage not in (ConversationStage.AWAIT_INTENT.value, "ready"):
            print(f"⚠️ [ERROR] Stage es '{stage}' pero no se manejó en las condiciones anteriores!")
        
        # Interpretar intención (incluye needs_confirmation, confirm_text, answer_type)
        print(f"🔍 [Intent Parser] Interpretando intención del mensaje: '{user_text[:100]}'")
        print(f"   Stage actual: {stage}")
        intent_slots_original = interpretar_intencion_principal(user_text)
        
        # Guardar el mensaje original del usuario en los intent_slots (por si acaso no vino del LLM)
        if not intent_slots_original.get("original_user_message"):
            intent_slots_original["original_user_message"] = user_text
        
        # Crear/actualizar cola de requerimientos
        multi_intent = intent_slots_original.get("multi_intent", False)
        intents_list = intent_slots_original.get("intents", [])
        
        # Si no hay requirements previos o control_action == "new_requirement", crear nueva cola
        if not requirements or control_action == "new_requirement":
            requirements = []
            for idx, r in enumerate(intents_list):
                # Asegurar que cada slot tenga el original_user_message
                slot_with_original = dict(r)  # Copiar el slot
                if not slot_with_original.get("original_user_message"):
                    # Si hay múltiples requerimientos, cada uno debe tener su propio mensaje específico
                    # Usar el intent_short para construir un mensaje específico para cada requerimiento
                    intent_short_req = slot_with_original.get("intent_short", "")
                    if multi_intent and len(intents_list) > 1:
                        # Para múltiples intenciones, usar el intent_short como mensaje original específico
                        # Esto asegura que cada requerimiento solo procese su propia intención
                        slot_with_original["original_user_message"] = intent_short_req
                        print(f"📋 [Multi-Req] Requerimiento {idx + 1} - original_user_message específico: '{intent_short_req[:100]}'")
                    else:
                        # Si solo hay una intención, usar el mensaje completo
                        slot_with_original["original_user_message"] = intent_slots_original.get("original_user_message", user_text)
                
                # Asegurar que cada requerimiento detecte su answer_type si no está presente
                if not slot_with_original.get("answer_type") or slot_with_original.get("answer_type") not in ("informativo", "operativo"):
                    intent_short_req = slot_with_original.get("intent_short", "")
                    original_msg_req = slot_with_original.get("original_user_message", user_text)
                    answer_type_req = _classify_answer_type_fallback(intent_short_req, slot_with_original, original_msg_req)
                    # answer_type_req = _aplicar_excepciones_informativas(answer_type_req, intent_short_req, slot_with_original, original_msg_req)  # ELIMINADO
                    # Asegurar que answer_type sea solo "informativo" o "operativo"
                    if answer_type_req not in ("informativo", "operativo"):
                        answer_type_req = "informativo"  # Fallback por defecto
                    slot_with_original["answer_type"] = answer_type_req
                    print(f"📋 [Multi-Req] Requerimiento {idx + 1} - answer_type detectado: {answer_type_req}")
                
                requirements.append({
                    "id": r.get("id", f"req_{idx + 1}"),
                    "summary": r.get("intent_short", ""),
                    "slots": slot_with_original,
                    "answer_type": slot_with_original.get("answer_type", "informativo"),
                    "status": "pending"
                })
            current_req_index = 0
        else:
            # Actualizar requirements existentes si hay nuevos intents
            # Solo agregar nuevos requerimientos si multi_intent es True
            if multi_intent and len(intents_list) > len(requirements):
                # Agregar nuevos requerimientos a la cola
                for idx, r in enumerate(intents_list[len(requirements):], start=len(requirements)):
                    # Asegurar que cada slot tenga el original_user_message
                    slot_with_original = dict(r)  # Copiar el slot
                    if not slot_with_original.get("original_user_message"):
                        # Si hay múltiples requerimientos, cada uno debe tener su propio mensaje específico
                        intent_short_req = slot_with_original.get("intent_short", "")
                        if multi_intent and len(intents_list) > 1:
                            # Para múltiples intenciones, usar el intent_short como mensaje original específico
                            slot_with_original["original_user_message"] = intent_short_req
                            print(f"📋 [Multi-Req] Requerimiento {idx + 1} (nuevo) - original_user_message específico: '{intent_short_req[:100]}'")
                        else:
                            # Si solo hay una intención, usar el mensaje completo
                            slot_with_original["original_user_message"] = intent_slots_original.get("original_user_message", user_text)
                    
                    # Asegurar que cada requerimiento detecte su answer_type si no está presente
                    if not slot_with_original.get("answer_type") or slot_with_original.get("answer_type") not in ("informativo", "operativo"):
                        intent_short_req = slot_with_original.get("intent_short", "")
                        original_msg_req = slot_with_original.get("original_user_message", user_text)
                        answer_type_req = _classify_answer_type_fallback(intent_short_req, slot_with_original, original_msg_req)
                        # answer_type_req = _aplicar_excepciones_informativas(answer_type_req, intent_short_req, slot_with_original, original_msg_req)  # ELIMINADO
                        # Asegurar que answer_type sea solo "informativo" o "operativo"
                        if answer_type_req not in ("informativo", "operativo"):
                            answer_type_req = "informativo"  # Fallback por defecto
                        slot_with_original["answer_type"] = answer_type_req
                        print(f"📋 [Multi-Req] Requerimiento {idx + 1} (nuevo) - answer_type detectado: {answer_type_req}")
                    
                    requirements.append({
                        "id": r.get("id", f"req_{idx + 1}"),
                        "summary": r.get("intent_short", ""),
                        "slots": slot_with_original,
                        "answer_type": slot_with_original.get("answer_type", "informativo"),
                        "status": "pending"
                    })
        
        # Obtener requerimiento activo
        if requirements and current_req_index < len(requirements):
            current_req = requirements[current_req_index]
            # Usar los slots del requerimiento activo para el flujo
            intent_slots = current_req.get("slots", intent_slots_original)
            # Asegurar que intent_slots tenga original_user_message del requerimiento específico
            if not intent_slots.get("original_user_message"):
                # Si hay múltiples requerimientos, usar el intent_short del requerimiento actual
                if multi_intent and len(requirements) > 1:
                    intent_slots["original_user_message"] = current_req.get("summary", current_req.get("slots", {}).get("intent_short", ""))
                else:
                    intent_slots["original_user_message"] = intent_slots_original.get("original_user_message", user_text)
        else:
            # Fallback: usar intent_slots principal
            current_req = None
            intent_slots = intent_slots_original
        
        print(f"📋 [Intent Parser] Intención clasificada:")
        print(f"   multi_intent: {multi_intent}")
        print(f"   total_requirements: {len(requirements)}")
        print(f"   current_requirement_index: {current_req_index}")
        print(f"   original_user_message: {intent_slots.get('original_user_message', 'N/A')[:100]}")
        # Verificar que original_user_message esté guardado
        if not intent_slots.get('original_user_message'):
            print(f"⚠️ [Intent Parser] ADVERTENCIA: original_user_message no está en intent_slots, guardándolo ahora...")
            intent_slots["original_user_message"] = user_text
            print(f"   ✅ original_user_message guardado: '{user_text[:100]}'")
        print(f"   intent_short: {intent_slots.get('intent_short', 'N/A')}")
        print(f"   accion: {intent_slots.get('accion', 'N/A')}")
        print(f"   objeto: {intent_slots.get('objeto', 'N/A')}")
        print(f"   answer_type: {intent_slots.get('answer_type', 'N/A')}")
        print(f"   needs_confirmation: {intent_slots.get('needs_confirmation', 'N/A')}")
        
        # Si hay múltiples requerimientos, proceder directamente con el primero sin confirmación
        if multi_intent and len(requirements) > 1:
            print(f"📋 [Multi-Intent] Detectados {len(requirements)} requerimientos:")
            for i, req in enumerate(requirements):
                print(f"   {i+1}. {req.get('summary', 'N/A')} (status: {req.get('status')})")
            
                # Obtener el primer requerimiento y proceder directamente sin mostrar confirmación
                first_req = requirements[0]
                first_req_slots = first_req.get("slots", intent_slots_original)
                
                print(f"✅ [Multi-Req] Procediendo directamente con el primer requerimiento sin confirmación")
                print(f"   Primer requerimiento: {first_req.get('summary', 'N/A')}")
                print(f"   needs_confirmation: {first_req_slots.get('needs_confirmation', False)}")
                
                # Proceder directamente con el primer requerimiento usando _handle_confirmation_stage
                # Esto manejará automáticamente si necesita confirmación o no
                return _handle_confirmation_stage(
                    user_text=user_text,
                    pending_slots=first_req_slots,
                    conversation_history=conversation_history,
                category=category,
                    subcategory=subcategory,
                    student_data=student_data,
                    perfil_id=perfil_id,
                    requirements=requirements,
                    current_req_index=current_req_index
                )
        
        # Si solo hay un requerimiento, seguir flujo normal 
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
                category, subcategory, student_data, perfil_id,
                requirements, current_req_index
            )
        
        # Si SÍ necesita confirmación, mostrar el mensaje de confirmación
        response = _build_need_confirm_response(
            confirm_text=confirm_text,
            intent_slots=intent_slots,
            category=category,
            subcategory=subcategory
        )
        
        # Incluir requirements en el extra
        if "extra" not in response:
            response["extra"] = {}
        response["extra"]["requirements"] = requirements
        response["extra"]["current_requirement_index"] = current_req_index
        
        return response

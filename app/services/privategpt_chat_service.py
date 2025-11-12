# app/services/privategpt_chat_service.py
"""
Servicio de chat usando PrivateGPT API.
Flujo: Saludo → Interpretar Intención → Confirmar → Solicitudes Relacionadas → PrivateGPT API (con mensaje confirmado)
"""
from typing import Dict, List, Any, Optional
import json
import re
from .privategpt_client import get_privategpt_client, PrivateGPTClient
from .handoff import get_departamento_real, classify_with_llm, _classify_answer_type_fallback
from .intent_parser import (
    es_greeting,
    interpretar_intencion_principal,
    _confirm_text_from_slots,
    es_confirmacion_positiva,
    es_confirmacion_negativa,
    obtener_primer_nombre
)
from .related_request_matcher import find_related_requests, load_student_requests
from pathlib import Path


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


def _call_privategpt_api(
    user_text: str,  # SOLO el mensaje confirmado del usuario (no "sí" o "correcto")
    conversation_history: List[Dict],
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None
) -> Dict[str, Any]:
    """
    Llama a la API de PrivateGPT con el mensaje confirmado del usuario.
    
    Returns:
        {
            "has_information": bool,
            "response": str,
            "fuentes": [{"archivo": str, "pagina": str}, ...],
            "error": str or None
        }
    """
    client = get_privategpt_client()
    
    if not client.is_available():
        return {
            "has_information": False,
            "response": "Lo siento, el servicio de inteligencia artificial no está disponible en este momento. Por favor, intenta más tarde o contacta al administrador.",
            "fuentes": [],
            "error": "PrivateGPT no disponible"
        }
    
    # Construir mensajes para PrivateGPT
    # PrivateGPT es un sistema RAG que busca en documentos basándose SOLO en la consulta actual
    # NO necesita contexto del sistema (información del estudiante, categoría, etc.)
    # NO necesita historial de conversación
    # Solo necesita el mensaje original del usuario
    
    messages = [
        {
            "role": "user",
            "content": user_text
        }
    ]
    
    print(f"📤 [PrivateGPT] Enviando mensaje a la API:")
    print(f"   Mensaje: '{user_text[:100]}'")
    print(f"   Total de mensajes: {len(messages)}")
    
    try:
        
        response = client.chat_completion(
            messages=messages,
            use_context=True,
            include_sources=True,
            stream=False
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
        
        # Procesar respuesta de PrivateGPT
        print(f"📥 [PrivateGPT] Respuesta recibida:")
        print(f"   Keys en respuesta: {list(response.keys())}")
        
        # Debug: Mostrar estructura completa de la respuesta (primeros 2000 caracteres)
        import json
        response_str = json.dumps(response, indent=2, default=str)
        print(f"   Estructura completa (primeros 2000 chars):\n{response_str[:2000]}")
        
        # PrivateGPT puede devolver el formato nuevo (has_information, response, fuentes)
        # o el formato estándar de chat completions (choices, message, content)
        has_information = response.get("has_information", False)
        response_text = response.get("response", "")
        fuentes = response.get("fuentes", [])
        
        # Si no está en el formato nuevo, procesar formato estándar de chat completions
        if not response_text and "choices" in response:
            choices = response.get("choices", [])
            print(f"   🔍 Procesando formato estándar de chat completions")
            print(f"   Número de choices: {len(choices)}")
            
            if choices:
                choice = choices[0]
                print(f"   Keys en choice[0]: {list(choice.keys())}")
                
                message = choice.get("message", {})
                print(f"   Keys en message: {list(message.keys()) if isinstance(message, dict) else 'N/A'}")
                
                content_raw = message.get("content", "") if isinstance(message, dict) else ""
                
                # PrivateGPT puede devolver el content como JSON string o como texto plano
                # Intentar parsear como JSON primero
                try:
                    if isinstance(content_raw, str) and content_raw.strip().startswith("{"):
                        content_parsed = json.loads(content_raw)
                        # Si es un objeto JSON con "response", usar ese campo
                        if isinstance(content_parsed, dict) and "response" in content_parsed:
                            response_text = content_parsed.get("response", "")
                            # Si también tiene fuentes en el JSON, agregarlas
                            if "fuentes" in content_parsed and not fuentes:
                                fuentes_json = content_parsed.get("fuentes", [])
                                for fuente in fuentes_json:
                                    if isinstance(fuente, dict):
                                        fuentes.append({
                                            "archivo": fuente.get("archivo", ""),
                                            "pagina": str(fuente.get("pagina", ""))
                                        })
                            # Si tiene has_information, usarlo
                            if "has_information" in content_parsed:
                                has_information = content_parsed.get("has_information", False)
                            print(f"   ✅ Content parseado como JSON, response extraído: {len(response_text)} caracteres")
                        else:
                            # No es el formato esperado, usar el texto completo
                            response_text = content_raw
                    else:
                        # No es JSON, usar como texto plano
                        response_text = content_raw
                except (json.JSONDecodeError, ValueError) as e:
                    # Si falla el parseo, usar el texto completo
                    print(f"   ⚠️ No se pudo parsear content como JSON: {e}")
                    response_text = content_raw
                
                # Buscar fuentes en diferentes ubicaciones posibles
                # 1. En el nivel de response
                if "sources" in response:
                    print(f"   ✅ Encontradas fuentes en response.sources")
                    fuentes_raw = response.get("sources", [])
                    print(f"   Número de fuentes en response.sources: {len(fuentes_raw)}")
                    for source in fuentes_raw:
                        if isinstance(source, dict):
                            print(f"   Fuente raw: {json.dumps(source, indent=2, default=str)[:500]}")
                            fuentes.append({
                                "archivo": source.get("document", {}).get("doc_metadata", {}).get("file_name", source.get("file_name", "")),
                                "pagina": str(source.get("document", {}).get("doc_metadata", {}).get("page_label", source.get("page", "")))
                            })
                
                # 2. En choice[0]
                if "sources" in choice:
                    print(f"   ✅ Encontradas fuentes en choice[0].sources")
                    fuentes_raw = choice.get("sources", [])
                    print(f"   Número de fuentes en choice[0].sources: {len(fuentes_raw)}")
                    for source in fuentes_raw:
                        if isinstance(source, dict):
                            print(f"   Fuente raw: {json.dumps(source, indent=2, default=str)[:500]}")
                            # Intentar extraer archivo y página de diferentes formatos
                            archivo = ""
                            pagina = ""
                            
                            # Formato 1: source.document.doc_metadata.file_name
                            if "document" in source:
                                doc = source.get("document", {})
                                if "doc_metadata" in doc:
                                    metadata = doc.get("doc_metadata", {})
                                    archivo = metadata.get("file_name", metadata.get("file_name", ""))
                                    pagina = str(metadata.get("page_label", metadata.get("page", "")))
                            
                            # Formato 2: source.file_name directamente
                            if not archivo:
                                archivo = source.get("file_name", source.get("document_name", ""))
                            if not pagina:
                                pagina = str(source.get("page", source.get("page_number", "")))
                            
                            if archivo:
                                fuentes.append({
                                    "archivo": archivo,
                                    "pagina": pagina
                                })
                
                # 3. En message (si existe)
                if isinstance(message, dict) and "sources" in message:
                    print(f"   ✅ Encontradas fuentes en message.sources")
                    fuentes_raw = message.get("sources", [])
                    print(f"   Número de fuentes en message.sources: {len(fuentes_raw)}")
                    for source in fuentes_raw:
                        if isinstance(source, dict):
                            print(f"   Fuente raw: {json.dumps(source, indent=2, default=str)[:500]}")
                            fuentes.append({
                                "archivo": source.get("document", {}).get("doc_metadata", {}).get("file_name", source.get("file_name", "")),
                                "pagina": str(source.get("document", {}).get("doc_metadata", {}).get("page_label", source.get("page", "")))
                            })
                
                # 4. Buscar en context (si existe)
                if "context" in choice:
                    context = choice.get("context", {})
                    print(f"   Keys en context: {list(context.keys()) if isinstance(context, dict) else 'N/A'}")
                    if isinstance(context, dict) and "citations" in context:
                        citations = context.get("citations", [])
                        print(f"   Número de citations: {len(citations)}")
                        for citation in citations:
                            if isinstance(citation, dict):
                                print(f"   Citation raw: {json.dumps(citation, indent=2, default=str)[:500]}")
                                fuentes.append({
                                    "archivo": citation.get("document", {}).get("doc_metadata", {}).get("file_name", citation.get("file_name", "")),
                                    "pagina": str(citation.get("document", {}).get("doc_metadata", {}).get("page_label", citation.get("page", "")))
                                })
                
                # Si hay fuentes, asumir que hay información
                if fuentes:
                    has_information = True
                    print(f"   ✅ Se encontraron {len(fuentes)} fuentes")
                else:
                    print(f"   ⚠️ No se encontraron fuentes en ninguna ubicación")
                    # Determinar si hay información relevante basándose en la respuesta
                    # Si la respuesta menciona que no hay información o que el contexto no contiene información, entonces no hay información
                    response_lower = response_text.lower()
                    no_info_keywords = [
                        "no contiene información",
                        "no tengo información",
                        "no se encontró información",
                        "no hay información",
                        "contexto no contiene",
                        "no contiene información específica"
                    ]
                    has_information = not any(keyword in response_lower for keyword in no_info_keywords)
                    print(f"   has_information determinado por keywords: {has_information}")
        
        # Si aún no hay respuesta, usar mensaje por defecto
        if not response_text:
            response_text = "No pude procesar tu solicitud."
        
        # Agrupar fuentes por archivo y consolidar páginas
        print(f"   🔍 [Agrupación] Antes de agrupar:")
        print(f"   Fuentes recibidas: {len(fuentes)}")
        if fuentes:
            print(f"   Ejemplo de fuente (primeras 2): {json.dumps(fuentes[:2], indent=2, default=str)}")
        
        fuentes_agrupadas = _agrupar_fuentes_por_archivo(fuentes)
        
        print(f"   📊 Resultado final:")
        print(f"   has_information: {has_information}")
        print(f"   response length: {len(response_text)} caracteres")
        print(f"   Fuentes originales: {len(fuentes)}")
        print(f"   Fuentes agrupadas: {len(fuentes_agrupadas)}")
        
        if fuentes_agrupadas:
            print(f"   ✅ Fuentes agrupadas correctamente:")
            for i, fuente in enumerate(fuentes_agrupadas, 1):
                archivo = fuente.get("archivo", "N/A")
                paginas = fuente.get("paginas", [])
                if paginas:
                    paginas_str = ", ".join(paginas)
                    print(f"      {i}. {archivo} (páginas: {paginas_str})")
                else:
                    print(f"      {i}. {archivo} (sin páginas)")
            print(f"   📋 Formato de fuentes agrupadas: {json.dumps(fuentes_agrupadas[:1], indent=2, default=str) if fuentes_agrupadas else '[]'}")
        else:
            print(f"   ⚠️ No se encontraron fuentes en la respuesta")
            # Si no hay fuentes, mostrar parte de la respuesta para debugging
            if not has_information:
                print(f"   Respuesta (primeros 200 chars): {response_text[:200]}")
        
        # Formatear fuentes para incluir en la respuesta (opcional, para mostrar en el texto)
        # Pero mantener las fuentes originales y agrupadas en el dict para el frontend
        fuentes_texto = _formatear_fuentes_para_respuesta(fuentes_agrupadas)
        
        # Si hay fuentes, agregarlas al final de la respuesta
        response_final = response_text
        if fuentes_agrupadas and has_information:
            # Solo agregar si no están ya en la respuesta
            if "Fuentes:" not in response_text and "fuentes:" not in response_text.lower():
                response_final = response_text + fuentes_texto
        
        print(f"   ✅ [Agrupación] Devolviendo {len(fuentes_agrupadas)} fuentes agrupadas")
        
        return {
            "has_information": has_information,
            "response": response_final,
            "fuentes": fuentes_agrupadas,  # Devolver fuentes agrupadas en lugar de las originales
            "error": None
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ [PrivateGPT] Excepción: {str(e)}")
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
            print(f"🔍 [Excepciones] '{excepcion}' detectado - convirtiendo de operativo a informativo")
            print(f"   Intent: '{intent_short}'")
            print(f"   Acción: '{accion}', Objeto: '{objeto}'")
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
            print(f"🔍 [Excepciones] Patrón '{patron}' detectado en texto - convirtiendo a informativo")
            return "informativo"
    
    return answer_type


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
    
    # Si hay intent_slots, intentar usar LLM para clasificar
    if intent_slots:
        intent_short = intent_slots.get("intent_short", "")
        if intent_short:
            try:
                llm_classification = classify_with_llm(
                    user_text, intent_short, category, subcategory, intent_slots, include_taxonomy=False
                )
                depto_llm = llm_classification.get("department")
                if depto_llm:
                    print(f"🏢 [Handoff] Departamento desde LLM: {depto_llm}")
                    return depto_llm
            except Exception as e:
                print(f"⚠️ [Handoff] Error al usar LLM para determinar departamento: {e}")
    
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
    uploaded_file: Any = None
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
    
    # 2. Detectar estado del flujo desde el historial
    stage = "ready"  # ready, await_confirm, await_related_request, await_handoff_details
    pending_slots = None
    handoff_channel = None
    
    print(f"🔍 [Stage Detection] Analizando historial de {len(conversation_history)} mensajes")
    
    # Buscar en el historial el último estado
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
            stage = "ready"
            pending_slots = None
            handoff_channel = None
            break
        
        if needs_handoff_details:
            stage = "await_handoff_details"
            if slot_payload:
                pending_slots = slot_payload
            if handoff_channel:
                print(f"✅ [Stage Detection] Stage detectado: {stage}, handoff_channel: {handoff_channel}")
                break
            if not handoff_channel:
                handoff_channel = msg.get("handoff_channel")
            print(f"✅ [Stage Detection] Stage detectado: {stage}, handoff_channel: {handoff_channel}")
            break
        
        if confirmed_status is False:
            stage = "ready"
            pending_slots = None
            break
        
        if needs_related_selection:
            stage = "await_related_request"
            if slot_payload:
                pending_slots = slot_payload
            break
        
        if slot_payload:
            pending_slots = slot_payload
            if needs_confirm:
                stage = "await_confirm"
            break
        
        if needs_confirm:
            stage = "await_confirm"
            history_list = list(conversation_history)
            bot_index = len(history_list) - i - 1
            if bot_index > 0:
                prev_msg = history_list[bot_index - 1]
                prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                if prev_text:
                    slots_prev = interpretar_intencion_principal(prev_text)
                    pending_slots = slots_prev
            break
    
    print(f"📊 [Stage Detection] Stage final detectado: {stage}")
    if stage == "await_handoff_details":
        print(f"   handoff_channel: {handoff_channel}")
        print(f"   pending_slots: {pending_slots is not None}")
    
    # 3. Si es saludo, respuesta natural
    if es_greeting(user_text):
        nombre = obtener_primer_nombre(student_data)
        saludo = f"Hola{' ' + nombre if nombre else ''}! 👋 Soy tu asistente virtual del Balcón de Servicios UNEMI. Estoy aquí para ayudarte con tus consultas y solicitudes. ¿En qué puedo asistirte hoy?"
        
        return {
            "summary": saludo,
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": None,
            "is_greeting": True,
            "handoff": False,
            "intent_slots": {},
            "source_pdfs": [],
            "fuentes": []
        }
    
    # 4. Etapa de confirmación
    if stage == "await_confirm":
        if es_confirmacion_positiva(user_text):
            # Usuario confirmó → buscar solicitudes relacionadas
            # Recuperar slots de intención
            intent_slots = pending_slots
            if not intent_slots:
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
                        intent_slots = payload
                        break
            
            if not intent_slots:
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        prev_text = msg.get("content") or msg.get("text", "")
                        if prev_text:
                            intent_slots = interpretar_intencion_principal(prev_text)
                            break
            
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
            
            # ===== ANALIZAR SI ES SOLICITUD O INFORMACIÓN =====
            # Obtener el mensaje ORIGINAL del usuario para el análisis
            original_user_request = None
            if intent_slots:
                original_user_request = intent_slots.get("original_user_message", "")
            
            if not original_user_request:
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        msg_text = msg.get("content") or msg.get("text", "")
                        if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text):
                            original_user_request = msg_text
                            break
            
            if not original_user_request:
                original_user_request = user_text
            
            # Determinar si es solicitud (operativo) o información (informativo)
            intent_short = intent_slots.get("intent_short", "")
            answer_type = _classify_answer_type_fallback(intent_short, intent_slots)
            
            # Aplicar reglas de excepciones: ciertas solicitudes deben tratarse como información
            answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)
            
            print(f"🔍 [Análisis] Intención confirmada: '{intent_short[:80]}'")
            print(f"   Tipo de respuesta: {answer_type}")
            print(f"   Acción: {intent_slots.get('accion', 'N/A')}")
            
            # Si es SOLICITUD (operativo), hacer handoff directamente sin llamar a PrivateGPT
            if answer_type == "operativo":
                print(f"✅ [Handoff Directo] Es una solicitud operativa, derivando directamente a agente humano")
                
                depto = _determinar_departamento_handoff(
                    user_text=original_user_request,
                    category=category,
                    subcategory=subcategory,
                    intent_slots=intent_slots,
                    student_data=student_data
                )
                
                perfil = student_data or {}
                student_name = (
                    perfil.get("credenciales", {}).get("nombre_completo")
                    if perfil.get("credenciales") else None
                )
                if not student_name:
                    student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
                
                saludo_nombre = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
                ask_msg = (
                    f"{saludo_nombre}Entiendo que necesitas realizar una solicitud. Para procesarla correctamente, te voy a conectar con mis compañeros humanos del departamento **{depto}**. 💁\n\n"
                    f"Para enviar tu solicitud, necesito que:\n"
                    f"1. Describes nuevamente tu solicitud con todos los detalles\n"
                    f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
                )
                
                print(f"🔀 [Handoff] Derivando solicitud a: {depto}")
                
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
                    "intent_slots": intent_slots,
                    "handoff": True,
                    "handoff_reason": "Solicitud operativa que requiere intervención humana"
                }
            
            # Si es INFORMACIÓN (informativo), continuar con el flujo normal (buscar solicitudes relacionadas → PrivateGPT)
            print(f"✅ [Información] Es una consulta informativa, continuando con búsqueda de información")
            
            # ===== BUSCAR SOLICITUDES RELACIONADAS =====
            # original_user_request ya fue obtenido arriba en el análisis
            
            print(f"🔍 [Related Requests] Buscando solicitudes relacionadas...")
            print(f"   Mensaje original del usuario: '{original_user_request[:100]}'")
            
            # Nota: El thinking_status "Buscando solicitudes relacionadas" se maneja en el frontend
            # Buscar solicitudes relacionadas
            related_requests_result = find_related_requests(
                user_request=original_user_request,
                intent_slots=intent_slots,
                student_data=student_data,
                max_results=3
            )
            
            print(f"🔍 [Related Requests] Resultado: {len(related_requests_result.get('related_requests', []))} solicitudes relacionadas")
            
            # Verificar si hay solicitudes previas del estudiante
            solicitudes_previas = load_student_requests(student_data)
            hay_solicitudes_previas = len(solicitudes_previas) > 0
            
            # Si hay solicitudes relacionadas, retornarlas para que el usuario seleccione
            related_requests = related_requests_result.get("related_requests", [])
            no_related = related_requests_result.get("no_related", False)
            
            if related_requests and not no_related:
                # HAY solicitudes relacionadas: usar mensaje generado por el LLM
                reasoning = related_requests_result.get("reasoning", "")
                user_message = related_requests_result.get("user_message", "")
                
                # Si el LLM no generó mensaje, usar uno por defecto
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
                    "summary": user_message,  # Usar mensaje generado por el LLM
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "needs_related_request_selection": True,
                    "related_requests": related_requests,
                    "no_related_request_option": True,
                    "confirmed": True,
                    "intent_slots": intent_slots,
                    "reasoning": reasoning,
                    "thinking_status": "Pensando en una explicación para el usuario"  # Estado cuando se genera el mensaje
                }
            elif hay_solicitudes_previas and no_related:
                # NO hay solicitudes relacionadas PERO hay solicitudes previas: usar mensaje generado por el LLM
                user_message = related_requests_result.get("user_message", "")
                
                # Si el LLM no generó mensaje, usar uno por defecto
                if not user_message:
                    primer_nombre = obtener_primer_nombre(student_data)
                    mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                    user_message = f"{mensaje_inicio}No he encontrado solicitudes relacionadas con tu requerimiento.\n\n¿Deseas continuar sin relacionar tu solicitud con ninguna solicitud previa?"
                
                print(f"🔍 [Related Requests] No hay solicitudes relacionadas, pero hay {len(solicitudes_previas)} solicitudes previas. Mostrando opción para continuar.")
                
                return {
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": 0.85,
                    "summary": user_message,  # Usar mensaje generado por el LLM
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "needs_related_request_selection": True,
                    "related_requests": [],  # Lista vacía
                    "no_related_request_option": True,  # Mostrar botón "No hay solicitud relacionada"
                    "confirmed": True,
                    "intent_slots": intent_slots,
                    "reasoning": related_requests_result.get("reasoning", "No hay solicitudes relacionadas")
                }
            
            # ===== NO HAY SOLICITUDES PREVIAS O NO HAY SOLICITUDES RELACIONADAS: Enviar mensaje confirmado a PrivateGPT API =====
            print(f"✅ [PrivateGPT] No hay solicitudes relacionadas ni previas, enviando mensaje confirmado a la API")
            print(f"   Mensaje confirmado: '{original_user_request[:100]}'")
            
            # Nota: El thinking_status se enviará en la respuesta después de llamar a PrivateGPT
            privategpt_result = _call_privategpt_api(
                user_text=original_user_request,  # SOLO el mensaje original del usuario, no el interpretado
                conversation_history=conversation_history,
                category=None,  # No enviar categoría a PrivateGPT
                subcategory=None,  # No enviar subcategoría a PrivateGPT
                student_data=None  # No enviar información del estudiante a PrivateGPT
            )
            
            has_information = privategpt_result.get("has_information", False)
            response_text = privategpt_result.get("response", "")
            fuentes = privategpt_result.get("fuentes", [])
            
            # Si tiene información, devolver respuesta con fuentes
            if has_information:
                # Las fuentes ahora vienen agrupadas: [{"archivo": str, "paginas": [str, ...]}, ...]
                source_pdfs = [f.get("archivo", "") for f in fuentes if f.get("archivo")]
                source_pdfs = list(set(source_pdfs))  # Eliminar duplicados
                
                print(f"✅ [PrivateGPT] Respuesta con información encontrada")
                print(f"   Fuentes agrupadas: {len(fuentes)}")
                print(f"   PDFs únicos: {', '.join(source_pdfs)}")
                
                return {
                    "summary": response_text,
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": 0.9,
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "confirmed": True,
                    "is_greeting": False,
                    "handoff": False,
                    "intent_slots": intent_slots,
                    "source_pdfs": source_pdfs,
                    "fuentes": fuentes,
                    "has_information": True,
                    "thinking_status": "Leyendo para dar una mejor respuesta"  # Estado cuando se busca en documentos
                }
            
            # Si NO tiene información, determinar departamento y hacer handoff
            print(f"⚠️ [PrivateGPT] No se encontró información, derivando a agente humano")
            
            depto = _determinar_departamento_handoff(
                user_text=original_user_request,
            category=category,
            subcategory=subcategory,
                intent_slots=intent_slots,
                student_data=student_data
            )
            
            perfil = student_data or {}
            student_name = (
                perfil.get("credenciales", {}).get("nombre_completo")
                if perfil.get("credenciales") else None
            )
            if not student_name:
                student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
            
            saludo_nombre = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
            ask_msg = (
                f"{saludo_nombre}No tengo información suficiente para responder tu consulta. 😔\n\n"
                f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{depto}**? 💁\n\n"
                f"Para enviar tu solicitud, necesito que:\n"
                f"1. Describes nuevamente tu solicitud con todos los detalles\n"
                f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
            )
            
            print(f"🔀 [Handoff] Derivando a: {depto}")
            
            return {
                "summary": ask_msg,
            "category": category,
            "subcategory": subcategory,
                "confidence": 0.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": True,
                "is_greeting": False,
                "handoff": True,
                "handoff_reason": "No se encontró información en los documentos",
                "handoff_channel": depto,
                "handoff_sent": False,
                "needs_handoff_details": True,
                "needs_handoff_file": True,
                "handoff_file_max_size_mb": 4,
                "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],
                "handoff_auto": False,
                "as_chat_message": True,
                "allow_new_query": False,
                "reset_context": False,
                "intent_slots": intent_slots,
                "source_pdfs": [],
                "fuentes": [],
                "has_information": False,
                "department": depto
            }
        
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
            return {
                "category": None,
                "subcategory": None,
                "confidence": 0.85,
                "summary": _confirm_text_from_slots(slots),
                "campos_requeridos": [],
                "needs_confirmation": True,
            "confirmed": None,
                "intent_slots": slots
            }
    
    # 5. Etapa de selección de solicitud relacionada
    elif stage == "await_related_request":
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
        
        if user_said_no_related:
            # Usuario eligió continuar sin relacionar → Enviar mensaje confirmado a PrivateGPT API
            print(f"✅ [PrivateGPT] Usuario rechazó solicitudes relacionadas, enviando mensaje confirmado a la API")
            print(f"   Mensaje confirmado: '{original_user_request[:100]}'")
        else:
            # Usuario seleccionó una solicitud relacionada → Enviar mensaje confirmado a PrivateGPT API
            print(f"✅ [PrivateGPT] Usuario seleccionó solicitud relacionada, enviando mensaje confirmado a la API")
            print(f"   Mensaje confirmado: '{original_user_request[:100]}'")
        
        # Enviar mensaje original del usuario a PrivateGPT API
        privategpt_result = _call_privategpt_api(
            user_text=original_user_request,  # SOLO el mensaje original del usuario, no el interpretado
            conversation_history=conversation_history,
            category=None,  # No enviar categoría a PrivateGPT
            subcategory=None,  # No enviar subcategoría a PrivateGPT
            student_data=None  # No enviar información del estudiante a PrivateGPT
        )
        
        has_information = privategpt_result.get("has_information", False)
        response_text = privategpt_result.get("response", "")
        fuentes = privategpt_result.get("fuentes", [])
        
        # Si tiene información, devolver respuesta con fuentes
        if has_information:
            # Las fuentes ahora vienen agrupadas: [{"archivo": str, "paginas": [str, ...]}, ...]
            source_pdfs = [f.get("archivo", "") for f in fuentes if f.get("archivo")]
            source_pdfs = list(set(source_pdfs))  # Eliminar duplicados
            
            print(f"✅ [PrivateGPT] Respuesta con información encontrada")
            print(f"   Fuentes agrupadas: {len(fuentes)}")
            print(f"   PDFs únicos: {', '.join(source_pdfs)}")
            
            return {
                "summary": response_text,
            "category": category,
            "subcategory": subcategory,
                "confidence": 0.9,
            "campos_requeridos": [],
            "needs_confirmation": False,
                "confirmed": True,
            "is_greeting": False,
                "handoff": False,
            "intent_slots": intent_slots,
                "source_pdfs": source_pdfs,
                "fuentes": fuentes,
                "has_information": True,
                "thinking_status": "Leyendo para dar una mejor respuesta"  # Estado cuando se busca en documentos
            }
        
        # Si NO tiene información, determinar departamento y hacer handoff
        print(f"⚠️ [PrivateGPT] No se encontró información, derivando a agente humano")
        
        depto = _determinar_departamento_handoff(
            user_text=original_user_request,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            student_data=student_data
        )
        
        perfil = student_data or {}
        student_name = (
            perfil.get("credenciales", {}).get("nombre_completo")
            if perfil.get("credenciales") else None
        )
        if not student_name:
            student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
        
        saludo_nombre = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
        ask_msg = (
            f"{saludo_nombre}No tengo información suficiente para responder tu consulta. 😔\n\n"
            f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{depto}**? 💁\n\n"
            f"Para enviar tu solicitud, necesito que:\n"
            f"1. Describes nuevamente tu solicitud con todos los detalles\n"
            f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
        )
        
        print(f"🔀 [Handoff] Derivando a: {depto}")
        
        return {
            "summary": ask_msg,
            "category": category,
            "subcategory": subcategory,
            "confidence": 0.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "is_greeting": False,
            "handoff": True,
            "handoff_reason": "No se encontró información en los documentos",
            "handoff_channel": depto,
            "handoff_sent": False,
            "needs_handoff_details": True,
            "needs_handoff_file": True,
            "handoff_file_max_size_mb": 4,
            "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],
            "handoff_auto": False,
            "as_chat_message": True,
            "allow_new_query": False,
            "reset_context": False,
            "intent_slots": intent_slots,
            "source_pdfs": [],
            "fuentes": [],
            "has_information": False,
            "department": depto
        }
    
    # 6. Etapa de detalles de handoff (usuario proporciona detalles y archivo para enviar al departamento)
    elif stage == "await_handoff_details":
        print(f"🔍 [Handoff Details] Procesando stage await_handoff_details")
        print(f"   user_text: '{user_text[:100]}'")
        print(f"   uploaded_file: {uploaded_file.name if uploaded_file else 'None'}")
        print(f"   handoff_channel: {handoff_channel}")
        
        # Verificar si el usuario ya proporcionó detalles y archivo
        details_text = (user_text or "").strip()
        is_confirmation_only = es_confirmacion_positiva(details_text) or es_confirmacion_negativa(details_text)
        
        # Verificar si tiene detalles sustanciales (no solo confirmación) y archivo
        has_substantial_details = len(details_text) > 0 and not is_confirmation_only
        has_file = uploaded_file is not None
        
        print(f"   details_text: '{details_text}'")
        print(f"   is_confirmation_only: {is_confirmation_only}")
        print(f"   has_substantial_details: {has_substantial_details} (len={len(details_text)})")
        print(f"   has_file: {has_file}")
        
        if has_substantial_details and has_file:
            # Usuario proporcionó detalles Y archivo → Enviar handoff y cerrar flujo
            print(f"✅ [Handoff] Usuario proporcionó detalles y archivo, enviando solicitud")
            print(f"   Detalles: '{details_text[:100]}'")
            print(f"   Archivo: {uploaded_file.name if uploaded_file else 'N/A'}")
            
            # Aquí se enviaría la solicitud al sistema (por ahora solo confirmamos)
            # TODO: Integrar con el sistema de solicitudes del balcón
            
            # Obtener información del estudiante para el mensaje
            perfil = student_data or {}
            student_name = (
                perfil.get("credenciales", {}).get("nombre_completo")
                if perfil.get("credenciales") else None
            )
            if not student_name:
                student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
            
            saludo_nombre = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
            
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
                "has_information": False
            }
        elif has_substantial_details and not has_file:
            # Tiene detalles pero falta archivo
            print(f"⚠️ [Handoff Details] Usuario tiene detalles pero falta archivo")
            return {
                "summary": f"Perfecto, recibí los detalles de tu solicitud. Ahora necesito que subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud para poder procesarla.",
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
        elif not has_substantial_details and has_file:
            # Tiene archivo pero falta detalles
            print(f"⚠️ [Handoff Details] Usuario tiene archivo pero falta detalles")
            return {
                "summary": "Gracias por subir el archivo. Ahora necesito que describas tu solicitud con todos los detalles para poder procesarla correctamente.",
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
            # No tiene ni detalles ni archivo (o solo confirmación)
            print(f"⚠️ [Handoff Details] Usuario no tiene detalles ni archivo (o solo confirmación)")
            print(f"   details_text: '{details_text}'")
            print(f"   is_confirmation_only: {is_confirmation_only}")
            return {
                "summary": "Para enviar tu solicitud, necesito que:\n1. Describes tu solicitud con todos los detalles\n2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud",
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
        # Verificar que realmente no estemos en un stage especial
        if stage != "ready":
            print(f"⚠️ [ERROR] Stage es '{stage}' pero no se manejó en las condiciones anteriores!")
        
        # Interpretar intención
        print(f"🔍 [Intent Parser] Interpretando intención del mensaje: '{user_text[:100]}'")
        print(f"   Stage actual: {stage}")
        intent_slots = interpretar_intencion_principal(user_text)
        
        # Guardar el mensaje original del usuario en los intent_slots
        # Esto es importante porque PrivateGPT necesita el mensaje original, no el interpretado
        intent_slots["original_user_message"] = user_text
        
        print(f"📋 [Intent Parser] Intención clasificada:")
        print(f"   original_user_message: {intent_slots.get('original_user_message', 'N/A')[:100]}")
        print(f"   intent_short: {intent_slots.get('intent_short', 'N/A')}")
        print(f"   accion: {intent_slots.get('accion', 'N/A')}")
        print(f"   objeto: {intent_slots.get('objeto', 'N/A')}")
        print(f"   asignatura: {intent_slots.get('asignatura', 'N/A')}")
        print(f"   detalle_libre: {intent_slots.get('detalle_libre', 'N/A')[:100]}")
        
        confirm_text = _confirm_text_from_slots(intent_slots)
        print(f"✅ [Intent Parser] Texto de confirmación generado: '{confirm_text[:100]}'")
        
        return {
            "category": None,
            "subcategory": None,
            "confidence": 0.85,
            "summary": confirm_text,
            "campos_requeridos": [],
            "needs_confirmation": True,
            "confirmed": None,
            "intent_slots": intent_slots,
            "thinking_status": "Entendiendo el requerimiento del usuario"  # Estado cuando se interpreta la intención
        }

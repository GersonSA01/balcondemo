# app/services/privategpt_service.py
"""
Servicio para llamadas a PrivateGPT API.
Maneja la comunicación con PrivateGPT, agrupación de fuentes y formateo de respuestas.
"""
from typing import Dict, List, Any, Optional
from .privategpt_client import get_privategpt_client
from .privategpt_response_parser import PrivateGPTResponseParser


def agrupar_fuentes_por_archivo(fuentes: List[Dict]) -> List[Dict]:
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


def formatear_fuentes_para_respuesta(fuentes_agrupadas: List[Dict]) -> str:
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


def call_privategpt_api(
    user_text: str,
    conversation_history: List[Dict],
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None,
    perfil_id: str = None
) -> Dict[str, Any]:
    """
    Llama a la API de PrivateGPT con el mensaje confirmado del usuario.
    
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
    
    print(f"📝 [PrivateGPT] Texto del usuario (sin normalizar): '{user_text[:100]}'")
    
    # Agregar el default_query_system_prompt (igual que frontend directo de PrivateGPT)
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
    
    # Construir mensajes con el system prompt
    messages = [
        {"role": "system", "content": default_system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    session_context = None
    
    # Implementar búsqueda prioritaria: primero UNEMI, luego resto
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
        
        fuentes_agrupadas = agrupar_fuentes_por_archivo(fuentes)
        
        # Formatear fuentes para incluir en la respuesta (opcional)
        fuentes_texto = formatear_fuentes_para_respuesta(fuentes_agrupadas)
        
        # Si hay fuentes, agregarlas al final de la respuesta
        response_final = response_text
        if fuentes_agrupadas and has_information:
            # Solo agregar si no están ya en la respuesta
            if "Fuentes:" not in response_text and "fuentes:" not in response_text.lower():
                response_final = response_text + fuentes_texto
        
        return {
            "has_information": has_information,
            "response": response_final,
            "fuentes": fuentes_agrupadas,
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


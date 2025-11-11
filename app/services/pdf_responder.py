# app/services/pdf_responder.py
"""Respuesta con RAG desde PDFs."""
import re
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from .config import llm
from .retriever import get_retriever


def responder_desde_pdfs(intent_text: str, incluir_fuente: bool = False, docs_override: list = None) -> dict:
    """
    Responde usando PDFs con RAG (versión neutral o con fuente).
    
    Args:
        intent_text: Query del usuario
        incluir_fuente: Si True, antepone "Según {pdf}:", si False responde directo
        docs_override: Si se proporciona, usa estos docs en lugar de hacer retrieval
    
    Returns:
        Respuesta generada
    """
    # Recuperar contexto
    try:
        if docs_override is not None:
            docs = docs_override
        else:
            # Solo obtener retriever si realmente se necesita
            retriever = get_retriever()
            docs = retriever.invoke(intent_text)
    except Exception:
        docs = []
    
    # Recolectar TODOS los PDFs únicos de los docs (incluyendo JSONs estructurados)
    source_pdfs = set()
    source_images = set()
    pdf_name = "los documentos"
    
    if docs:
        for doc in docs:
            # Obtener metadata
            if hasattr(doc, 'metadata'):
                metadata = doc.metadata
            elif isinstance(doc, dict):
                metadata = doc.get('metadata', {})
            else:
                metadata = {}
            
            # Verificar si es un documento JSON estructurado
            source_type = metadata.get('source_type', '')
            
            if source_type == 'json_structured':
                # Documento JSON: puede tener archivo (PDF o imagen)
                archivo = metadata.get('archivo', '')
                titulo = metadata.get('titulo', '')
                
                if archivo:
                    if archivo.endswith('.pdf'):
                        source_pdfs.add(archivo)
                        if not pdf_name or pdf_name == "los documentos":
                            pdf_name = archivo
                    elif archivo.endswith(('.png', '.jpg', '.jpeg')):
                        source_images.add(archivo)
                
                # También agregar título como referencia
                if titulo and (not pdf_name or pdf_name == "los documentos"):
                    pdf_name = titulo
            else:
                # Documento PDF tradicional
                pdf = metadata.get('source_pdf')
                if pdf:
                    source_pdfs.add(pdf)
                    if not pdf_name or pdf_name == "los documentos":
                        pdf_name = pdf
    
    # Limpiar nombre del PDF principal
    pdf_name_clean = pdf_name.replace(".pdf", "").replace("_", " ").replace("-", " ")
    
    # Lista de PDFs fuente (incluir también imágenes de JSONs)
    source_pdfs_list = sorted(list(source_pdfs))
    source_images_list = sorted(list(source_images))
    
    # Combinar PDFs e imágenes para la lista de fuentes
    all_sources = source_pdfs_list + source_images_list
    
    # Extraer texto de documentos con metadatos (páginas)
    def format_docs(documents):
        if not documents:
            return "No se encontró contexto relevante."
        result = []
        for i, d in enumerate(documents, start=1):
            if hasattr(d, "page_content"):
                content = d.page_content
                metadata = getattr(d, "metadata", {})
            elif isinstance(d, dict):
                content = d.get("page_content", str(d))
                metadata = d.get("metadata", {})
            else:
                content = str(d)
                metadata = {}
            
            # Incluir información de fuente
            source_type = metadata.get("source_type", "")
            page = metadata.get("page", metadata.get("page_number", None))
            
            # Determinar fuente según el tipo
            if source_type == "json_structured":
                # Documento JSON estructurado
                titulo = metadata.get("titulo", "información estructurada")
                archivo = metadata.get("archivo", "")
                source_label = titulo
                if archivo:
                    source_label = f"{titulo} ({archivo})"
                result.append(f"[Fuente: {source_label}]\n{content}")
            else:
                # Documento PDF tradicional
                source_pdf = metadata.get("source_pdf", "documento")
                if page is not None:
                    result.append(f"[Fuente: {source_pdf}, Página {page}]\n{content}")
                else:
                    result.append(f"[Fuente: {source_pdf}]\n{content}")
        
        formatted = "\n\n".join(result)
        return formatted
    
    # Template del prompt con respuesta JSON estructurada
    template = """
Eres un asistente académico experto en normativas universitarias. Tu tarea es responder preguntas usando SOLO la información del contexto proporcionado.

CONTEXTO DEL REGLAMENTO:
{context}

CONSULTA DEL USUARIO:
{question}

INSTRUCCIONES ESTRICTAS:
1. Analiza el contexto cuidadosamente y determina si contiene información útil para responder la consulta.
2. Responde en español, lenguaje claro y directo.
3. Cita artículos específicos si los hay (ej: "según el Art. 15...", "el artículo 32 indica...").
4. Si el contexto menciona procedimientos, plazos, requisitos o responsables, detállalos.
5. IMPORTANTE: Si el usuario pregunta "¿cómo hacer X?" o "¿puedo hacer X?" y el reglamento dice que NO se permite o NO se acepta, esa ES la respuesta correcta y SÍ tienes información. Ejemplo: si pregunta "¿cómo justificar una falta?" y el reglamento dice "no se aceptarán justificaciones", responde que no se pueden justificar y explica la política.
6. Si el contexto menciona contactos, correos, enlaces o pasos específicos, inclúyelos en tu respuesta.
7. NO inventes, NO supongas, NO agregues información externa.
8. Sé conciso pero completo (2-5 oraciones idealmente).
9. Si hay múltiples opciones o pasos, enuméralos claramente.

Responde ESTRICTAMENTE en formato JSON con esta estructura:
{{
  "has_information": true/false,
  "confidence": "high/medium/low",
  "answer": "tu respuesta aquí",
  "sources": [
    {{"doc": "nombre_del_pdf.pdf", "page": 15}},
    {{"doc": "otro_documento.pdf", "page": 23}}
  ]
}}

IMPORTANTE SOBRE CITAS:
- SIEMPRE debes incluir al menos una cita en "sources" con el nombre del documento y número de página
- Si no puedes identificar la página exacta, usa el número de página más cercano del contexto
- Si NO hay citas, la respuesta será RECHAZADA
- Las citas deben corresponder a los documentos del contexto proporcionado

Criterios para "has_information":
- true: El contexto contiene información relevante, clara y útil para responder (incluso si es para decir que algo NO está permitido)
- false: El contexto NO contiene información relevante o útil para esta consulta específica

Criterios para "confidence":
- high: La información es explícita y directa
- medium: La información está presente pero es indirecta o parcial
- low: La información es vaga o ambigua

RESPONDE SOLO CON EL JSON, sin explicaciones adicionales:
"""
    
    prompt = ChatPromptTemplate.from_template(template)
    
    # Cadena RAG
    rag_chain = (
        {"context": lambda x: format_docs(docs if docs_override else retriever.invoke(x)), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    
    respuesta_json = {}
    try:
        respuesta_raw = rag_chain.invoke(intent_text)
        
        # Parsear JSON de la respuesta
        try:
            # Limpiar markdown si existe
            if respuesta_raw.startswith("```json"):
                respuesta_raw = respuesta_raw.replace("```json", "").replace("```", "").strip()
            elif respuesta_raw.startswith("```"):
                respuesta_raw = respuesta_raw.replace("```", "").strip()
            
            respuesta_json = json.loads(respuesta_raw)
            has_info = respuesta_json.get("has_information", True)
            llm_confidence = respuesta_json.get("confidence", "medium")
            respuesta_base = respuesta_json.get("answer", respuesta_raw)
            sources = respuesta_json.get("sources", [])
            
            # V2: Rechazar respuesta si no hay citas (P5)
            if not sources or len(sources) == 0:
                print("⚠️ [V2] Respuesta rechazada: no hay citas con páginas")
                has_info = False  # Forzar handoff
            
            print(f"📊 [LLM Self-Evaluation] has_info={has_info}, confidence={llm_confidence}, sources={len(sources)}")
            
        except json.JSONDecodeError:
            # Si falla el parsing, asumir que tiene info y usar respuesta directa
            print("⚠️ [JSON Parse Failed] Usando respuesta directa")
            has_info = True
            llm_confidence = "medium"
            respuesta_base = respuesta_raw
            
    except Exception as e:
        respuesta_base = f"Error al consultar el reglamento: {str(e)}"
        has_info = False
        llm_confidence = "low"
    
    # Usar la auto-evaluación del LLM en lugar de validación por keywords
    # Si el LLM dice que NO tiene información, generar mensaje apropiado
    if not has_info:
        no_info_msg = "No se encontró información específica sobre tu consulta en el reglamento disponible."
        if incluir_fuente:
            respuesta_texto = f"Según {pdf_name_clean}: {no_info_msg}"
        else:
            respuesta_texto = no_info_msg
        
        return {
            "respuesta": respuesta_texto,
            "source_pdfs": source_pdfs_list,
            "has_information": False,  # LLM evaluó que NO hay info
            "llm_confidence": llm_confidence
        }
    
    # Respuesta final: con o sin fuente
    if incluir_fuente:
        if not respuesta_base.lower().startswith("según"):
            respuesta_texto = f"Según {pdf_name_clean}: {respuesta_base}"
        else:
            respuesta_texto = respuesta_base
    else:
        # Versión neutral: remover "Según..." si existe
        if respuesta_base.lower().startswith("según"):
            # Buscar el primer ":" y tomar lo que sigue
            idx = respuesta_base.find(":")
            if idx > 0:
                respuesta_texto = respuesta_base[idx+1:].strip()
        else:
            respuesta_texto = respuesta_base
    
    # Retornar dict con respuesta, PDFs fuente y auto-evaluación del LLM
    # Extraer sources de la respuesta JSON si están disponibles
    sources_citations = []
    try:
        if 'respuesta_json' in locals() and respuesta_json and "sources" in respuesta_json:
            sources_citations = respuesta_json.get("sources", [])
    except:
        pass
    
    return {
        "respuesta": respuesta_texto,
        "source_pdfs": source_pdfs_list,  # PDFs tradicionales
        "source_images": source_images_list,  # Imágenes de JSONs estructurados
        "all_sources": all_sources,  # Todas las fuentes (PDFs + imágenes)
        "has_information": has_info,  # Auto-evaluación del LLM
        "llm_confidence": llm_confidence,  # Confianza del LLM
        "sources": sources_citations  # Citas con páginas (V2)
    }


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
    
    # Recolectar TODOS los PDFs únicos de los docs
    source_pdfs = set()
    pdf_name = "los documentos"
    
    if docs:
        for doc in docs:
            pdf = None
            if hasattr(doc, 'metadata') and doc.metadata.get('source_pdf'):
                pdf = doc.metadata['source_pdf']
            elif isinstance(doc, dict) and doc.get('metadata', {}).get('source_pdf'):
                pdf = doc['metadata']['source_pdf']
            
            if pdf:
                source_pdfs.add(pdf)
                if not pdf_name or pdf_name == "los documentos":
                    pdf_name = pdf
    
    # Limpiar nombre del PDF principal
    pdf_name_clean = pdf_name.replace(".pdf", "").replace("_", " ").replace("-", " ")
    
    # Lista de PDFs fuente
    source_pdfs_list = sorted(list(source_pdfs))
    
    # Extraer texto de documentos
    def format_docs(documents):
        if not documents:
            return "No se encontró contexto relevante."
        result = []
        for i, d in enumerate(documents, start=1):
            if hasattr(d, "page_content"):
                content = d.page_content
            elif isinstance(d, dict):
                content = d.get("page_content", str(d))
            else:
                content = str(d)
            # Sin número de página/fragmento en versión neutral
            result.append(content)
        
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
  "answer": "tu respuesta aquí"
}}

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
            
            print(f"📊 [LLM Self-Evaluation] has_info={has_info}, confidence={llm_confidence}")
            
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
    return {
        "respuesta": respuesta_texto,
        "source_pdfs": source_pdfs_list,
        "has_information": has_info,  # Auto-evaluación del LLM
        "llm_confidence": llm_confidence  # Confianza del LLM
    }


def responder_con_reglamento(intent_text: str) -> dict:
    """
    Responde usando el reglamento con RAG y SIEMPRE antepone:
    'Según {nombre_pdf}: <respuesta>'
    
    Returns:
        dict con "respuesta" y "source_pdfs"
    """
    # Wrapper sobre responder_desde_pdfs con incluir_fuente=True
    return responder_desde_pdfs(intent_text, incluir_fuente=True)


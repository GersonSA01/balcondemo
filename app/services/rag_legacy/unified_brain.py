from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from ..config import llm, guarded_ainvoke, guarded_invoke, GOOGLE_API_KEY
from langchain_google_genai import ChatGoogleGenerativeAI
import json
import re


class Brain(BaseModel):
    intent_short: str
    confidence: float
    resolution_mode: str = "informativa"
    operationality_score: float = 0.0
    decision_reasons: List[str] = Field(default_factory=list)
    ticket_title: Optional[str] = None
    needs_confirmation: bool
    confirm_text: Optional[str] = None
    needs_context: bool
    enriched_query: str
    query_rag: str
    taxonomy: Dict[str, str] = {}
    handoff_needed: bool = False
    handoff_depto: Optional[str] = None
    related_query: Optional[str] = None


def _format_instructions() -> str:
    # Instrucciones de salida JSON estricta
    return (
        "Devuelve SOLO JSON válido con la siguiente forma:\n"
        "{\n"
        '  "intent_short": "string",\n'
        '  "confidence": 0.0,\n'
        '  "resolution_mode": "informativa|operativa",\n'
        '  "operationality_score": 0.0,\n'
        '  "decision_reasons": ["..."],\n'
        '  "ticket_title": "string or null",\n'
        '  "needs_confirmation": true,\n'
        '  "confirm_text": "string or null",\n'
        '  "needs_context": false,\n'
        '  "enriched_query": "string",\n'
        '  "query_rag": "string",\n'
        '  "taxonomy": {"category": "string", "subcategory": "string"},\n'
        '  "handoff_needed": false,\n'
        '  "handoff_depto": "string or null",\n'
        '  "related_query": "string or null"\n'
        "}"
    )

_FEWSHOTS = """
[CRITERIOS]
- "OPERATIVA": el usuario expresa intención de que la UNIVERSIDAD EJECUTE una acción o trámite en su nombre
  (cambiar, inscribir, abrir, homologar, generar certificado, reasignar, retirar, subir documentos, corregir datos, resolver caso, etc.),
  aunque lo diga implícito o con lenguaje coloquial. También cuando requiere derivación a un área humana.
- "INFORMATIVA": el usuario solo pide explicación, requisitos, fechas, políticas, pasos o definiciones; no pide que ejecuten nada.

[NOTAS]
- No dependas de palabras exactas. Decide por sentido/propósito global.
- Si el mensaje es ambiguo pero sugiere acción institucional → inclina a "operativa".
- Establece "operationality_score" ∈ [0..1] y justifica brevemente en "decision_reasons".

[EJEMPLOS]
User: "Estoy pensando en pasarme a otra carrera, ¿qué tan complicado es?"
→ informativa (score≈0.35) ; intent_short="cambio_carrera_info"

User: "Quiero cambiarme de carrera"
→ operativa (score≈0.85) ; intent_short="cambio_carrera"

User: "¿Qué documentos piden para homologar materias?"
→ informativa (score≈0.30) ; intent_short="homologacion_info"

User: "Necesito que me homologuen materias del instituto donde estaba"
→ operativa (score≈0.80) ; intent_short="homologacion"

User: "Si falto 3 días, ¿pierdo la materia?"
→ informativa (score≈0.20)

User: "Ayúdame a retirar una materia ya inscrita"
→ operativa (score≈0.75) ; intent_short="retiro_materia"
"""


def _build_prompt(user_text: str, history: List[Dict], student_profile: Dict) -> str:
    """Helper para construir el prompt del cerebro."""
    # Tomar más mensajes para mejor análisis semántico (últimos 8 mensajes = 4 turnos)
    history_trimmed = (history or [])[-8:]
    
    # Construir resumen de contexto conversacional (SEMÁNTICO, sin filtros de keywords)
    # Incluir TODO el contexto relevante y dejar que el LLM haga análisis semántico completo
    context_summary = ""
    if history_trimmed and len(history_trimmed) >= 2:
        context_lines = []
        # Incluir TODOS los mensajes del historial recortado (sin filtrar por keywords)
        # El LLM hará el análisis semántico, NO filtrar por keywords
        for msg in history_trimmed:
            role = msg.get("role") or msg.get("who", "")
            text = msg.get("content") or msg.get("text", "")
            if role in ("user", "student", "estudiante"):
                # Incluir preguntas completas del usuario (hasta 300 chars para mantener contexto semántico completo)
                context_lines.append(f"Usuario: {text[:300]}")
            elif role in ("bot", "assistant"):
                # Incluir respuestas completas del bot (hasta 500 chars para capturar temas y detalles semánticos)
                # NO filtrar por keywords - incluir TODO para análisis semántico completo
                # El LLM necesita ver el contexto completo para detectar relaciones semánticas
                context_lines.append(f"Bot: {text[:500]}")
        if context_lines:
            context_summary = "\n".join(context_lines)
            # Agregar indicador de que hay contexto previo
            context_summary = f"[CONVERSACIÓN PREVIA - Últimos {len(context_lines)} mensajes - ANÁLISIS SEMÁNTICO REQUERIDO]\n{context_summary}"
    
    return (
        "Eres un orquestador semántico. ANALIZA EL CONTEXTO CONVERSACIONAL usando comprensión semántica, NO solo keywords.\n"
        f"{_FEWSHOTS}\n\n"
        "CONTEXTO CONVERSACIONAL (últimos mensajes):\n"
        f"{context_summary if context_summary else 'No hay conversación previa.'}\n\n"
        "Tareas: (1) intención+confianza; "
        "(2) decidir resolution_mode (informativa|operativa) y operationality_score [0..1]; "
        "da razones breves en 'decision_reasons'; si operativa, propone 'ticket_title' y 'handoff_depto'; "
        "(3) ANÁLISIS SEMÁNTICO DE CONTEXTO (CRÍTICO - NO USAR KEYWORDS COMO FILTRO):\n"
        "   - ANALIZA SEMÁNTICAMENTE el SIGNIFICADO y la RELACIÓN entre pregunta y contexto.\n"
        "   - NO uses keywords ('y', 'para', 'también') como filtro principal.\n"
        "   - PROCESO: (1) Identifica TEMA PRINCIPAL del contexto, (2) Identifica QUÉ pregunta la pregunta actual, "
        "(3) Determina si hay RELACIÓN SEMÁNTICA (amplía/especifica/continúa el tema).\n"
        "   - EJEMPLOS DE ANÁLISIS SEMÁNTICO (sin depender de keywords):\n"
        "     * Contexto completo: 'Exámenes finales: 24-29 noviembre. Fechas por sedes: Quito 9-14 diciembre'\n"
        "       Pregunta: 'y para la sede de quito?'\n"
        "       → Análisis semántico: La pregunta se refiere a 'fechas de exámenes finales para Quito' "
        "(relación semántica clara con tema 'exámenes finales')\n"
        "       → needs_context=true, enriched_query='fechas de exámenes finales para la sede de Quito'\n"
        "     * Contexto: 'Cambio de paralelo requiere documentos: certificado, solicitud'\n"
        "       Pregunta: 'qué documentos necesito?'\n"
        "       → Análisis semántico: Se refiere a 'documentos para cambio de paralelo' "
        "(relación semántica con tema 'cambio de paralelo')\n"
        "       → needs_context=true, enriched_query='documentos necesarios para cambio de paralelo'\n"
        "   - REGLAS:\n"
        "     * Si hay relación semántica → needs_context=true (independiente de keywords)\n"
        "     * enriched_query = [TEMA_PRINCIPAL_CONTEXTO] + [PREGUNTA_ACTUAL] (auto-contenida)\n"
        "     * query_rag = enriched_query si hay contexto\n"
        "     * confirm_text debe incluir contexto si needs_context=true:\n"
        "       '¿Te refieres a [tema del contexto] [pregunta]?'\n"
        "(4) query_rag: query concisa y específica para búsqueda en documentos (usar enriched_query si tiene contexto); "
        "(5) taxonomy {category,subcategory}; "
        "(6) confirm_text: si needs_confirmation=true, generar texto de confirmación NATURAL que incluya el contexto si existe.\n\n"
        f"PREGUNTA ACTUAL DEL USUARIO: {user_text}\n\n"
        f"StudentProfile: {json.dumps(student_profile or {}, ensure_ascii=False)}\n\n"
        f"{_format_instructions()}\n"
        "JSON:"
    )


def _parse_brain_response(response) -> Brain:
    """Helper para parsear la respuesta del LLM a objeto Brain."""
    content = getattr(response, "content", str(response)).strip()
    # Limpiar cercas de markdown si existieran
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(content)
    except Exception:
        # Intento de extraer bloque JSON
        m = re.search(r"\{[\s\S]*\}", content)
        data = json.loads(m.group(0)) if m else {}
    # Normalizar mínimos
    if "taxonomy" not in data or not isinstance(data.get("taxonomy"), dict):
        data["taxonomy"] = {}
    # Defaults robustos
    data.setdefault("resolution_mode", "informativa")
    data.setdefault("operationality_score", 0.0)
    data.setdefault("decision_reasons", [])
    # Construir modelo
    return Brain(**data)


async def unified_brain(user_text: str, history: List[Dict], student_profile: Dict) -> Brain:
    """Versión async del cerebro (usa gRPC aio)."""
    prompt = _build_prompt(user_text, history, student_profile)
    response = await guarded_ainvoke(llm, prompt)
    return _parse_brain_response(response)


def unified_brain_sync(user_text: str, history: List[Dict], student_profile: Dict) -> Brain:
    """
    Versión SÍNCRONA del cerebro para evitar gRPC aio/loops.
    Fuerza transport REST (HTTP) y usa .invoke().
    """
    # Configura el LLM sin gRPC (REST)
    llm_sync = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        transport="rest",  # <- clave: REST, no gRPC
        temperature=0,
        api_key=GOOGLE_API_KEY,
        max_retries=0,  # los reintentos los maneja guarded_invoke
    )
    
    prompt = _build_prompt(user_text, history, student_profile)
    try:
        response = guarded_invoke(llm_sync, prompt)
    except Exception as e:
        # Último salvavidas: si algo raro pasa, reintenta con otra instancia REST
        print(f"⚠️ Error en primera llamada sync, reintentando: {e}")
        llm_sync = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            transport="rest",
            temperature=0,
            api_key=GOOGLE_API_KEY,
            max_retries=0,
        )
        response = guarded_invoke(llm_sync, prompt)
    
    return _parse_brain_response(response)



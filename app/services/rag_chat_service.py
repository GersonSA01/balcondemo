# app/services/rag_chat_service.py
"""
Servicio RAG simplificado para chatbot.
Punto de entrada principal: classify_with_rag()
"""
from typing import Dict, List, Any
import re

# Imports de módulos internos
from .config import TAU_NORMA, TAU_EXPAND, TAU_MIN, FEATURE_FLAGS
from .retriever import get_retriever
from .intent_parser import (
    interpretar_intencion_principal,
    _confirm_text_from_slots,
    es_confirmacion_positiva,
    es_confirmacion_negativa,
    es_greeting
)
from .answerability import answerability_score, gen_query_variants_llm
from .pdf_responder import responder_desde_pdfs
from .query_planner import (
    plan_queries,
    rrf_fuse,
    detect_entities,
    route_by_entity,
)
from .hierarchical_router import hierarchical_candidates
from .handoff import should_handoff
from .conversation_context import (
    enrich_query_with_context,
    should_use_conversational_mode
)
from .deterministic_router import route_by_taxonomy, get_folders_for_family
from .config import TAU_SKIP_CONFIRM
from .json_retriever import get_json_retriever, search_structured_info, format_json_item_as_document


# === INDUSTRIAL QUERY UNDERSTANDING ===
# Mapa de canonización: normaliza frases del usuario a términos del dominio
_CANON_MAP = [
    (r"\bjustificar( una)? falta(s)?\b", "justificación de inasistencias"),
    (r"\bjustificaci[oó]n( de)? (falta|inasistenc)[a-z]*\b", "justificación de inasistencias"),
    (r"\bexcusa(s)? por (falta|ausencia|inasistenc)[a-z]*\b", "justificación de inasistencias"),
    (r"\bpermiso(s)? por (falta|inasistenc)[a-z]*\b", "permiso académico por inasistencia"),
    (r"\b(certificado m[eé]dic[oa])\b", "certificado médico para justificar inasistencia"),
    # EPUNEMI y certificados
    (r"\bcertificado(s)? de (curso|jornada|webinar|capacitaci[oó]n|formaci[oó]n)[a-z ]*( de )?(epunemi|unemi)\b", "certificados EPUNEMI no recibidos"),
    (r"\bcertificado(s)? (no (llega|lleg[oó]|recib[ií])|que no (llega|llegan|lleg[oó]))\b", "certificados EPUNEMI no recibidos"),
    (r"\b(epunemi|unemi).*(certificado|curso|jornada|webinar)\b", "certificados EPUNEMI no recibidos"),
    (r"\b(certificado|curso|jornada).*(epunemi|unemi)\b", "certificados EPUNEMI no recibidos"),
]

# Expansiones de sinónimos por concepto canónico
_SYNONYM_EXPANSIONS = {
    "justificación de inasistencias": [
        "política de asistencia",
        "asistencia mínima requerida",
        "porcentaje de asistencia obligatorio",
        "faltas permitidas",
        "ausencias justificadas",
        "requisitos de asistencia",
        "artículo sobre asistencia",
        "reglamento de asistencia a clases",
    ],
    "certificados EPUNEMI no recibidos": [
        "certificados que no llegan EPUNEMI",
        "validar certificado EPUNEMI",
        "descargar certificado EPUNEMI",
        "certificado no recibido por correo EPUNEMI",
        "validación de certificados en línea EPUNEMI",
        "sistema SAGEST certificados",
        "contactar centro de servicios EPUNEMI",
        "certificados de formación continua",
        "certificados de jornadas académicas",
        "correo info@epunemi.com certificados",
    ],
}

def _canonicalize_query(q: str) -> str:
    """Normaliza la query a términos canónicos del dominio."""
    txt = q or ""
    for pat, rep in _CANON_MAP:
        txt = re.sub(pat, rep, txt, flags=re.IGNORECASE)
    return txt.strip()

def _obtener_primer_nombre(student_data: Dict = None) -> str:
    """
    Extrae el primer nombre del estudiante desde student_data.
    
    Args:
        student_data: Diccionario con datos del estudiante
    
    Returns:
        Primer nombre del estudiante o string vacío si no se encuentra
    """
    if not student_data:
        return ""
    try:
        credenciales = student_data.get("credenciales", {})
        nombre_completo = credenciales.get("nombre_completo") or credenciales.get("nombre") or ""
        if nombre_completo and isinstance(nombre_completo, str):
            partes = nombre_completo.strip().split()
            if partes:
                return partes[0]
    except Exception:
        pass
    return ""


def _expand_with_synonyms(q: str) -> list[str]:
    """Expande la query con sinónimos del dominio."""
    q_canon = _canonicalize_query(q)
    variants = [q_canon]
    
    for concept, synonyms in _SYNONYM_EXPANSIONS.items():
        if concept.lower() in q_canon.lower():
            variants.extend(synonyms)
    
    # Deduplicar manteniendo orden
    seen, result = set(), []
    for v in variants:
        key = v.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(v)
    
    return result


def classify_with_rag(
    user_text: str, 
    conversation_history: List[Dict] = None,
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None
) -> Dict[str, Any]:
    """
    Clasificador principal con RAG.
    
    Args:
        user_text: Mensaje del usuario
        conversation_history: Historial de conversación
        category: Categoría seleccionada por el usuario (opcional)
        subcategory: Subcategoría seleccionada por el usuario (opcional)
        student_data: Datos del estudiante logueado (opcional)
    
    Devuelve dict compatible:
    {
        category, subcategory, confidence, summary, 
        campos_requeridos, needs_confirmation, confirmed, 
        is_greeting, handoff, handoff_reason, intent_slots
    }
    
    Flujo:
    1. Detectar saludo → respuesta de bienvenida
    2. Interpretar intención → pedir confirmación
    3. Si usuario confirma → buscar en PDFs con 4 niveles de confianza
    4. Si no hay contenido suficiente → derivar al agente
    """
    conversation_history = conversation_history or []
    
    # Log de contexto recibido (para debugging)
    if category and subcategory:
        print(f"[RAG Service] Contexto: {category} > {subcategory}")
    if student_data:
        nombre = student_data.get("credenciales", {}).get("nombre_completo", "N/A")
        print(f"[RAG Service] Estudiante: {nombre}")
    
    # Detectar estado del flujo desde el historial
    stage = "ready"  # ready, await_confirm
    pending_slots = None

    # Buscar en el historial el último estado
    for i, msg in enumerate(reversed(conversation_history)):
        role = msg.get("role") or msg.get("who")
        if role not in ("bot", "assistant"):
            continue

        # Verificar si el último mensaje del bot necesitaba confirmación
        needs_confirm = msg.get("needs_confirmation", False)
        confirmed_status = msg.get("confirmed")
        slot_payload = msg.get("intent_slots")
        
        # Buscar también en meta (el frontend guarda data completa ahí)
        meta = msg.get("meta") or {}
        if isinstance(meta, dict):
            if not needs_confirm:
                needs_confirm = meta.get("needs_confirmation", False)
            if confirmed_status is None:
                confirmed_status = meta.get("confirmed")
            if not slot_payload:
                slot_payload = meta.get("intent_slots")

        # Si el usuario negó explícitamente (confirmed=False), resetear estado
        if confirmed_status is False:
            stage = "ready"
            pending_slots = None
            break

        if slot_payload:
            pending_slots = slot_payload
            if needs_confirm:
                stage = "await_confirm"
            break

        # Si no hay slots pero el mensaje pedía confirmación, recuperar del mensaje anterior
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
    
    # 1. Si es saludo, respuesta natural
    if es_greeting(user_text):
        return {
            "category": None,
            "subcategory": None,
            "confidence": 0.15,
            "summary": "Hola 👋 Soy tu asistente virtual del Balcón de Servicios. Cuéntame tu solicitud en lenguaje natural y te guío al trámite correcto.",
            "campos_requeridos": [],
            "is_greeting": True,
            "needs_confirmation": False,
            "confirmed": None
        }
    
    # 2. Etapa de confirmación
    if stage == "await_confirm":
        if es_confirmacion_positiva(user_text):
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

            # ENRIQUECER QUERY CON CONTEXTO CONVERSACIONAL (si aplica)
            # Evaluar con LLM si es pregunta de seguimiento
            context_evaluation = should_use_conversational_mode(user_text, conversation_history)
            enriched_text = user_text  # Por defecto, usar texto original
            
            if context_evaluation["needs_context"]:
                follow_up_type = "follow_up" if context_evaluation["needs_context"] else "independent"
                print(f"💬 [Conversational Mode] Activado - Tipo: {follow_up_type}")
                print(f"   Confidence: {context_evaluation['confidence']}")
                print(f"   Reason: {context_evaluation['reason']}")
                
                # Enriquecer query con contexto previo
                enriched_text = enrich_query_with_context(user_text, conversation_history)
                
                # Re-interpretar la query enriquecida
                intent_slots = interpretar_intencion_principal(enriched_text)
                
                print(f"✨ [Enriched Intent] {intent_slots.get('intent_short', 'N/A')}")
            
            # Construir query de intención - usar intent_short en lugar de concatenar todos los slots
            intent_query = intent_slots.get("intent_short", "").strip()
            if not intent_query:
                # Fallback: construir desde slots
                intent_query_parts = [
                    intent_slots.get("accion", ""),
                    intent_slots.get("objeto", ""),
                    intent_slots.get("asignatura", ""),
                    intent_slots.get("detalle_libre", "")
                ]
                intent_query = " ".join([p for p in intent_query_parts if p]).strip()
            
            if not intent_query:
                # Si hay contexto conversacional, usar query enriquecida
                if context_evaluation["needs_context"]:
                    intent_query = enriched_text.strip()
                else:
                    intent_query = user_text.strip()

            try:
                # ===== BÚSQUEDA EN PDFs CON QUERY UNDERSTANDING INDUSTRIAL =====
                
                # ETAPA 0: ROUTING JERÁRQUICO (carpetas + títulos)
                # Esto se hace ANTES del retrieval pesado para reducir espacio de búsqueda
                hierarchical_cands = hierarchical_candidates(user_text, entities=None, queries=None)
                
                # Obtener retriever filtrado por carpetas/archivos candidatos
                retr = get_retriever(
                    files_hint=hierarchical_cands.get("files"),
                    folders_hint=hierarchical_cands.get("folders")
                )
                
                # ETAPA 1: Canonizar query
                canon_q = _canonicalize_query(intent_query)
                
                # ETAPA 2: Detectar entidades y crear plan
                entities = detect_entities(user_text) if FEATURE_FLAGS.get("entity_router") else []
                routing_info = route_by_entity(entities, canon_q) if entities else {}
                
                print(f"🎯 Entidades detectadas: {entities}")
                if routing_info.get("boosts"):
                    print(f"📈 Términos boosteados: {routing_info['boosts'][:3]}")
                print(f"📂 Routing: {hierarchical_cands.get('method')} - {len(hierarchical_cands.get('files', []))} files, {len(hierarchical_cands.get('folders', []))} folders")
                
                # ETAPA 3: Query Planner - generar subconsultas
                if FEATURE_FLAGS.get("query_planner"):
                    planned_queries = plan_queries(intent_slots, canon_q, user_text)
                    print(f"🎯 [Planner] Generadas {len(planned_queries)} subconsultas")
                else:
                    planned_queries = [canon_q]
                
                # ETAPA 4: Retrieval híbrido con RRF (PDFs)
                all_doc_lists = []
                best_ascore = None
                
                for i, pq in enumerate(planned_queries[:3], 1):  # Máximo 3 queries
                    ascore = answerability_score(pq, retr, k=12)
                    print(f"🔎 [{i}] '{pq[:60]}...' → conf: {ascore['confidence']:.3f}")
                    
                    if best_ascore is None or ascore["confidence"] > best_ascore["confidence"]:
                        best_ascore = ascore
                    
                    # Recuperar docs para cada query
                    try:
                        docs = retr.invoke(pq)
                        if docs:
                            all_doc_lists.append(docs)
                    except Exception:
                        pass
                
                # Fusionar con RRF si tenemos múltiples listas
                if FEATURE_FLAGS.get("rrf_fusion") and len(all_doc_lists) > 1:
                    fused_docs = rrf_fuse(all_doc_lists, k=12)
                    print(f"🔀 [RRF] Fusionados {len(fused_docs)} docs de {len(all_doc_lists)} listas")
                elif all_doc_lists:
                    fused_docs = all_doc_lists[0][:12]
                else:
                    fused_docs = []
                
                # ETAPA 4.5: Búsqueda en JSONs estructurados
                # Buscar en JSONs usando la query canónica y también el texto original del usuario
                json_query = f"{canon_q} {user_text}".strip()
                json_results = search_structured_info(json_query, min_score=0.3, max_results=5)
                json_docs = [format_json_item_as_document(item) for item in json_results]
                
                if json_docs:
                    print(f"📋 [JSON] Encontrados {len(json_docs)} resultados estructurados")
                    # Combinar JSONs con PDFs (priorizar PDFs, luego JSONs)
                    # Agregar JSONs al final de la lista fusionada
                    fused_docs = fused_docs + json_docs
                    # Si encontramos JSONs relevantes, aumentar ligeramente la confianza
                    if best_ascore and json_docs:
                        # Aumentar confianza si hay matches en JSONs (hasta 0.1 puntos)
                        json_boost = min(len(json_docs) * 0.02, 0.1)
                        best_ascore["confidence"] = min(best_ascore["confidence"] + json_boost, 1.0)
                        print(f"📈 [JSON Boost] Confianza ajustada: {best_ascore['confidence']:.3f} (+{json_boost:.3f})")
                
                # ETAPA 5: Intentar expansión con sinónimos si baja confianza
                if best_ascore["confidence"] < TAU_NORMA:
                    syn_variants = _expand_with_synonyms(canon_q)
                    print(f"🔎 [Synonyms] Probando {len(syn_variants)} variantes...")
                    for q in syn_variants[:3]:  # Top 3 sinónimos
                        ascore_syn = answerability_score(q, retr, k=12)
                        if ascore_syn["confidence"] > best_ascore["confidence"]:
                            best_ascore = ascore_syn
                            try:
                                docs_syn = retr.invoke(q)
                                if docs_syn and FEATURE_FLAGS.get("rrf_fusion"):
                                    all_doc_lists.append(docs_syn)
                                    fused_docs = rrf_fuse(all_doc_lists, k=12)
                                elif docs_syn:
                                    fused_docs = docs_syn[:12]
                            except Exception:
                                pass
                            print(f"  ✓ Mejor: '{q[:60]}...' → {ascore_syn['confidence']:.3f}")
                
                # ETAPA 6: Variantes sin LLM (V2) - solo si aún bajo
                if best_ascore["confidence"] < TAU_NORMA:
                    print(f"🔎 [V2-Variants] Generando reformulaciones (sin LLM)...")
                    qvars = gen_query_variants_llm(canon_q, n=3, use_llm=False)  # V2: sin LLM por defecto
                    for qv in qvars:
                        ascore_llm = answerability_score(qv, retr, k=12)
                        if ascore_llm["confidence"] > best_ascore["confidence"]:
                            best_ascore = ascore_llm
                            try:
                                docs_llm = retr.invoke(qv)
                                if docs_llm and FEATURE_FLAGS.get("rrf_fusion"):
                                    all_doc_lists.append(docs_llm)
                                    fused_docs = rrf_fuse(all_doc_lists, k=12)
                                elif docs_llm:
                                    fused_docs = docs_llm[:12]
                            except Exception:
                                pass
                            print(f"  ✓ Mejor: '{qv[:60]}...' → {ascore_llm['confidence']:.3f}")
                
                # Usar el mejor ascore y docs fusionados
                ascore = best_ascore
                intent_query_effective = canon_q  # Usar query canónica como referencia
                
                # Logging final
                print(f"📊 RESULTADO FINAL:")
                print(f"   Confidence: {ascore.get('confidence', 0):.3f}")
                print(f"   Docs recuperados: {ascore.get('non_empty_docs', 0)}")
                print(f"   Verdict: {ascore.get('verdict', 'N/A')}")
                print(f"   Docs fusionados: {len(fused_docs)}")

                # Nivel 1: Alta confianza (>= TAU_NORMA) → responder directo
                if ascore["confidence"] >= TAU_NORMA:
                    try:
                        # Usar respuesta neutral si el flag está activo
                        if FEATURE_FLAGS.get("neutral_response"):
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                        else:
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                        
                        return {
                            "category": "Reglamento",
                            "subcategory": "Consulta",
                            "confidence": ascore["confidence"],
                            "summary": result["respuesta"],
                            "source_pdfs": result.get("source_pdfs", []),
                            "campos_requeridos": [],
                            "needs_confirmation": False,
                            "confirmed": True,
                            "source_id": "pdf::combined",
                            "mode": "normativo",
                            "handoff": False,
                            "intent_slots": intent_slots,
                            "diagnostics": {"answerability": ascore, "method": "direct_high_conf", "entities": entities}
                        }
                    except Exception:
                        pass  # Intentar siguiente nivel

                # Nivel 2: Ya no es necesario - el multi-stage retrieval se hace arriba
                # Si llegamos aquí con confidence < TAU_NORMA, pasamos al Nivel 3

                # Variable de control para evitar que Nivel 3.5 se ejecute si ya se decidió handoff
                nivel3_requiere_handoff = False
                
                # Nivel 3: Baja confianza pero HAY contenido (>= TAU_MIN) → responder de todos modos
                if ascore["confidence"] >= TAU_MIN and ascore["verdict"] in ("yes", "unknown") and (ascore["non_empty_docs"] > 0 or len(fused_docs) > 0):
                    try:
                        # Usar respuesta neutral si el flag está activo
                        if FEATURE_FLAGS.get("neutral_response"):
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                        else:
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                        
                        ans = result["respuesta"]
                        
                        # Usar auto-evaluación del LLM en lugar de keywords (solución industrial)
                        has_info = result.get("has_information", True)  # Default True para retrocompatibilidad
                        llm_confidence_level = result.get("llm_confidence", "medium")
                        
                        print(f"🤖 [LLM Evaluation] has_info={has_info}, confidence={llm_confidence_level}")
                        
                        # Aceptar solo si el LLM evaluó que SÍ tiene información
                        if has_info:
                            # Usar categorías por defecto (taxonomía se obtiene en handoff si es necesario)
                            cat = "Reglamento"
                            sub = "Consulta"
                            
                            # En Nivel 3: Si hay respuesta válida del PDF, NO derivar
                            # Solo derivar si es una intención CRÍTICA que requiere validación humana
                            intent_short = intent_slots.get("intent_short", "")
                            
                            # Lista de intenciones críticas que SÍ requieren derivación aunque haya info
                            INTENCIONES_CRITICAS_OBLIGATORIAS = {
                                "cambio_de_paralelo",
                                "cambio_de_curso", 
                                "cambio_de_carrera",
                                "anulacion_matricula",
                                "homologacion",
                                "convalidacion"
                            }
                            
                            # Solo derivar si es crítica OBLIGATORIA
                            if intent_short in INTENCIONES_CRITICAS_OBLIGATORIAS:
                                print(f"⚠️ [Nivel 3] Intención crítica obligatoria: {intent_short}, marcando para derivación")
                                nivel3_requiere_handoff = True
                                # No hacer return aquí, dejar que continúe al Nivel 4
                            else:
                                # Hay información válida → responder directamente, NO derivar
                                print(f"✅ [Nivel 3] Respondiendo con info del PDF (confidence={ascore['confidence']:.3f})")
                                return {
                                    "category": cat,
                                    "subcategory": sub,
                                    "confidence": max(ascore["confidence"], 0.5),
                                    "summary": ans,
                                    "source_pdfs": result.get("source_pdfs", []),
                                    "campos_requeridos": [],
                                    "needs_confirmation": False,
                                    "confirmed": True,
                                    "source_id": "pdf::combined",
                                    "mode": "normativo",
                                    "handoff": False,
                                    "intent_slots": intent_slots,
                                    "diagnostics": {"answerability": ascore, "method": "low_conf_but_content", "entities": entities}
                                }
                    except Exception:
                        pass  # Si falla, derivar
                
                # Nivel 3.5: MUY baja confianza pero HAY documentos → último intento antes de derivar
                # Siempre intentar responder si se recuperó algún contenido, confiando en el LLM
                # PERO NO ejecutar si Nivel 3 ya decidió handoff
                if not nivel3_requiere_handoff and (ascore["non_empty_docs"] > 0 or len(fused_docs) > 0):
                    try:
                        # Usar respuesta neutral si el flag está activo
                        if FEATURE_FLAGS.get("neutral_response"):
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                        else:
                            result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                        
                        ans = result["respuesta"]
                        
                        # Usar auto-evaluación del LLM (solución industrial)
                        has_info = result.get("has_information", True)
                        llm_confidence_level = result.get("llm_confidence", "medium")
                        
                        print(f"🤖 [LLM Evaluation Nivel 3.5] has_info={has_info}, confidence={llm_confidence_level}")
                        
                        if has_info:
                            return {
                                "category": "Reglamento",
                                "subcategory": "Consulta",
                                "confidence": 0.4,  # Confianza fija baja pero aceptable
                                "summary": ans,
                                "source_pdfs": result.get("source_pdfs", []),
                                "campos_requeridos": [],
                                "needs_confirmation": False,
                                "confirmed": True,
                                "source_id": "pdf::combined",
                                "mode": "normativo",
                                "handoff": False,
                                "intent_slots": intent_slots,
                                "diagnostics": {"answerability": ascore, "method": "very_low_conf_but_has_docs", "entities": entities}
                            }
                    except Exception:
                        pass  # Si falla, derivar

                # Nivel 4: REALMENTE no hay nada (< TAU_MIN) → derivar al agente
                # Recuperar texto original de la consulta del usuario (antes de la confirmación)
                original_user_query = intent_query  # Default: usar intent_query
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        msg_text = msg.get("content") or msg.get("text", "")
                        # Ignorar confirmaciones simples
                        if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text):
                            original_user_query = msg_text
                            break
                
                print(f"📝 [Original Query] {original_user_query[:80]}...")
                
                # Evaluar handoff con lógica completa usando LLM (FUSIONADO: ahora también devuelve categoria/subcategoria)
                handoff_decision = should_handoff(
                    confidence=ascore["confidence"],
                    intent_short=intent_slots.get("intent_short", ""),
                    category=None,  # Se obtiene de la clasificación LLM fusionada
                    subcategory=None,  # Se obtiene de la clasificación LLM fusionada
                    slots=intent_slots,
                    history=conversation_history,
                    user_text=original_user_query  # Texto ORIGINAL de la consulta, no la confirmación
                )
                
                # Extraer categoria/subcategoria de la decisión de handoff (viene de classify_with_llm fusionada)
                cat = handoff_decision.get("categoria") or "Consultas varias"
                sub = handoff_decision.get("subcategoria") or "Consultas varias"
                
                # Mensaje de derivación directo y claro con información del canal LLM
                # Si no hay channel, usar departamento real por defecto
                from .handoff import get_departamento_real
                channel = handoff_decision.get("handoff_channel")
                if not channel:
                    # Obtener categoria/subcategoria de la decisión
                    categoria_fallback = handoff_decision.get("categoria") or cat or "Consultas varias"
                    subcategoria_fallback = handoff_decision.get("subcategoria") or sub or "Consultas varias"
                    department_fallback = handoff_decision.get("department", "general")
                    channel = get_departamento_real(categoria_fallback, subcategoria_fallback, department_fallback, original_user_query)
                department = handoff_decision.get("department", "general")
                llm_reasoning = handoff_decision.get("llm_reasoning", "")
                
                # Obtener primer nombre del estudiante
                primer_nombre = _obtener_primer_nombre(student_data)
                
                # Mensaje personalizado según el departamento
                emoji_dept = {
                    "académico": "🎓",
                    "financiero": "💰",
                    "bienestar": "🏥",
                    "administrativo": "📋",
                    "tic": "💻",
                    "biblioteca": "📚",
                    "general": "💁"
                }.get(department, "💁")
                
                # Construir mensaje final con saludo personalizado
                if primer_nombre:
                    mensaje_inicio = f"{primer_nombre}, "
                else:
                    mensaje_inicio = ""
                
                respuesta_final = (
                    f"{mensaje_inicio}Su solicitud se ha transferido al departamento **{channel}**. {emoji_dept}\n\n"
                    f"Un agente especializado revisará tu caso y se pondrá en contacto contigo por correo electrónico "
                    f"en las próximas 24 horas.\n\n"
                    f"📧 **Mantente atento a tu correo institucional** para recibir la respuesta del agente."
                )
                
                # Debug: verificar que el saludo esté en el mensaje
                if primer_nombre:
                    print(f"✅ [Saludo] Primer nombre '{primer_nombre}' incluido en mensaje de handoff")
                else:
                    print(f"⚠️ [Saludo] No se pudo obtener primer nombre (student_data disponible: {student_data is not None})")
                
                # Log para debugging
                print(f"🎯 [Handoff Decision]")
                print(f"   Channel: {channel}")
                print(f"   Department: {department}")
                if llm_reasoning:
                    print(f"   Reasoning: {llm_reasoning}")
                
                return {
                    "category": cat,
                    "subcategory": sub,
                    "confidence": ascore["confidence"],
                    "summary": respuesta_final,
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "confirmed": True,
                    "handoff": True,
                    "handoff_auto": True,  # Flag para indicar derivación automática (sin CTA)
                    "handoff_reason": handoff_decision.get("handoff_reason"),
                    "handoff_channel": handoff_decision.get("handoff_channel"),
                    "handoff_department": handoff_decision.get("department"),  # Departamento detectado por LLM
                    "handoff_llm_reasoning": handoff_decision.get("llm_reasoning"),  # Razonamiento LLM
                    "answer_type": handoff_decision.get("answer_type"),
                    "intent_slots": intent_slots,
                    "trace": {
                        "intent_query": intent_query,
                        "answerability": ascore,
                        "reason": "No hay contenido suficiente en PDFs para responder",
                        "handoff": handoff_decision
                    }
                }
                # ===== FIN BÚSQUEDA EN PDFs =====
            except Exception as e:
                return {
                    "category": None,
                    "subcategory": None,
                    "confidence": 0.0,
                    "summary": f"Ocurrió un error al buscar en el reglamento: {str(e)}",
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "confirmed": None
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
    else:
        # 3. stage == ready → V2: Router determinista primero (P0)
        # Intentar routing determinista (sin LLM)
        category_det, subcategory_det, confidence_det = route_by_taxonomy(user_text)
        
        # Si confianza >= 0.90, saltar confirmación y ir directo a retrieval (P0)
        if confidence_det >= TAU_SKIP_CONFIRM:
            print(f"🚀 [V2 Router] Alta confianza ({confidence_det:.2f}), saltando confirmación")
            # Construir query de intención desde routing determinista
            intent_query = user_text.strip()
            
            # Obtener carpetas candidatas desde familia detectada
            # (Necesitamos mapear categoría → familia, simplificado aquí)
            folders_hint = []
            if category_det:
                # Mapeo simplificado (en producción, usar mapeo completo)
                if "Academico" in category_det or "academico" in category_det.lower():
                    folders_hint = ["unemi_interno/estudiantes"]
                elif "Bienestar" in category_det:
                    folders_hint = ["unemi_interno/estudiantes"]
                elif "Idiomas" in category_det:
                    folders_hint = ["unemi_interno/estudiantes", "unemi_interno/tic"]
                else:
                    folders_hint = ["unemi_interno/estudiantes"]
            
            # Ir directo a retrieval (sin confirmación)
            try:
                hierarchical_cands = hierarchical_candidates(user_text, entities=None, queries=None)
                if folders_hint:
                    hierarchical_cands["folders"] = folders_hint
                
                retr = get_retriever(
                    files_hint=hierarchical_cands.get("files"),
                    folders_hint=hierarchical_cands.get("folders")
                )
                
                # Canonizar query
                canon_q = _canonicalize_query(intent_query)
                
                # Retrieval con juez híbrido (V2)
                ascore = answerability_score(canon_q, retr, k=12, use_hybrid=True)
                print(f"📊 [V2] Answerability: {ascore.get('confidence', 0):.3f} (method: {ascore.get('method', 'N/A')})")
                
                # Recuperar docs
                docs = retr.invoke(canon_q)
                fused_docs = docs[:12] if docs else []
                
                # Buscar también en JSONs estructurados
                json_query = f"{canon_q} {user_text}".strip()
                json_results = search_structured_info(json_query, min_score=0.3, max_results=5)
                json_docs = [format_json_item_as_document(item) for item in json_results]
                
                if json_docs:
                    print(f"📋 [JSON Router] Encontrados {len(json_docs)} resultados estructurados")
                    fused_docs = fused_docs + json_docs
                    # Aumentar confianza si hay matches en JSONs
                    if json_docs:
                        json_boost = min(len(json_docs) * 0.02, 0.1)
                        ascore["confidence"] = min(ascore["confidence"] + json_boost, 1.0)
                
                # Si alta confianza, responder directamente
                if ascore["confidence"] >= TAU_NORMA:
                    result = responder_desde_pdfs(canon_q, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                    respuesta_texto = result["respuesta"]
                    
                    # Agregar saludo si hay student_data
                    primer_nombre = _obtener_primer_nombre(student_data)
                    if primer_nombre and not respuesta_texto.startswith(primer_nombre):
                        respuesta_texto = f"{primer_nombre}, {respuesta_texto}"
                    
                    return {
                        "category": category_det or "Reglamento",
                        "subcategory": subcategory_det or "Consulta",
                        "confidence": ascore["confidence"],
                        "summary": respuesta_texto,
                        "source_pdfs": result.get("source_pdfs", []),
                        "campos_requeridos": [],
                        "needs_confirmation": False,
                        "confirmed": True,
                        "source_id": "pdf::deterministic_router",
                        "mode": "normativo",
                        "handoff": False,
                        "intent_slots": {"intent_short": canon_q},
                        "diagnostics": {
                            "answerability": ascore,
                            "method": "deterministic_router_high_conf",
                            "router_confidence": confidence_det
                        }
                    }
                # Si confianza media, intentar responder de todos modos
                elif ascore["confidence"] >= TAU_MIN:
                    result = responder_desde_pdfs(canon_q, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                    if result.get("has_information", True):
                        respuesta_texto = result["respuesta"]
                        
                        # Agregar saludo si hay student_data
                        primer_nombre = _obtener_primer_nombre(student_data)
                        if primer_nombre and not respuesta_texto.startswith(primer_nombre):
                            respuesta_texto = f"{primer_nombre}, {respuesta_texto}"
                        
                        return {
                            "category": category_det or "Reglamento",
                            "subcategory": subcategory_det or "Consulta",
                            "confidence": ascore["confidence"],
                            "summary": respuesta_texto,
                            "source_pdfs": result.get("source_pdfs", []),
                            "campos_requeridos": [],
                            "needs_confirmation": False,
                            "confirmed": True,
                            "source_id": "pdf::deterministic_router",
                            "mode": "normativo",
                            "handoff": False,
                            "intent_slots": {"intent_short": canon_q},
                            "diagnostics": {
                                "answerability": ascore,
                                "method": "deterministic_router_medium_conf",
                                "router_confidence": confidence_det
                            }
                        }
            except Exception as e:
                print(f"⚠️ [V2 Router] Error en retrieval directo: {e}")
                # Fallback a flujo normal
                pass
        
        # Si no se saltó confirmación, usar flujo normal (con LLM si es necesario)
        slots = interpretar_intencion_principal(user_text)
        
        # Si el router determinista encontró algo, usar esa categoría
        if category_det and confidence_det >= 0.75:
            return {
                "category": category_det,
                "subcategory": subcategory_det,
                "confidence": confidence_det,
                "summary": _confirm_text_from_slots(slots),
                "campos_requeridos": [],
                "needs_confirmation": True,
                "confirmed": None,
                "intent_slots": slots,
                "diagnostics": {"router_confidence": confidence_det, "method": "deterministic_router_with_confirm"}
            }
        
        # Flujo normal (sin match determinista claro)
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

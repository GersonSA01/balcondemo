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
from .taxonomy import map_to_taxonomy
from .answerability import answerability_score, gen_query_variants_llm
from .pdf_responder import responder_con_reglamento, responder_desde_pdfs
from .query_planner import (
    plan_queries,
    rrf_fuse,
    fuzzy_anchor_search,
    get_section_anchors,
    detect_entities,
    route_by_entity,
)
from .hierarchical_router import hierarchical_candidates
from .handoff import should_handoff, format_handoff_message
from .conversation_context import (
    enrich_query_with_context,
    should_use_conversational_mode,
    detect_follow_up_type
)


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
                follow_up_type = detect_follow_up_type(context_evaluation)
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
                
                # ETAPA 4: Retrieval híbrido con RRF
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
                
                # ETAPA 6: Variantes LLM si aún bajo
                if best_ascore["confidence"] < TAU_NORMA:
                    print(f"🔎 [LLM-Variants] Generando reformulaciones...")
                    qvars = gen_query_variants_llm(canon_q, n=3)
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
                
                # ETAPA 7: Safety net fuzzy si MUY baja confianza
                if FEATURE_FLAGS.get("fuzzy_safety_net") and best_ascore["confidence"] < TAU_MIN:
                    print(f"🆘 [Fuzzy Safety Net] Buscando anclas...")
                    section_anchors = get_section_anchors()
                    fuzzy_matches = fuzzy_anchor_search(canon_q, section_anchors, threshold=70, limit=3)
                    
                    if fuzzy_matches:
                        print(f"  ✓ Encontradas {len(fuzzy_matches)} anclas fuzzy")
                        # Buscar con las anclas encontradas
                        for anchor, score in fuzzy_matches:
                            try:
                                docs_anchor = retr.invoke(anchor)
                                if docs_anchor:
                                    if FEATURE_FLAGS.get("rrf_fusion"):
                                        all_doc_lists.append(docs_anchor)
                                        fused_docs = rrf_fuse(all_doc_lists, k=12)
                                    else:
                                        fused_docs = docs_anchor[:12]
                                    # Boost artificial al ascore
                                    best_ascore["confidence"] = max(best_ascore["confidence"], 0.4)
                                    print(f"    → '{anchor}' (fuzzy: {score})")
                                    break
                            except Exception:
                                pass
                
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
                            # Mapear a taxonomía para categoría
                            mapping = map_to_taxonomy(intent_query)
                            cat = mapping.get("categoria") or "Consultas varias"
                            sub = mapping.get("subcategoria") or "Consultas varias"
                            
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
                mapping = map_to_taxonomy(intent_query)
                cat = mapping.get("categoria") or "Consultas varias"
                sub = mapping.get("subcategoria") or "Consultas varias"
                
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
                
                # Evaluar handoff con lógica completa usando LLM
                handoff_decision = should_handoff(
                    confidence=ascore["confidence"],
                    intent_short=intent_slots.get("intent_short", ""),
                    category=cat,
                    subcategory=sub,
                    slots=intent_slots,
                    history=conversation_history,
                    user_text=original_user_query  # Texto ORIGINAL de la consulta, no la confirmación
                )
                
                # Mensaje de derivación directo y claro con información del canal LLM
                channel = handoff_decision.get("handoff_channel", "Mesa de Ayuda SGA")
                department = handoff_decision.get("department", "general")
                llm_reasoning = handoff_decision.get("llm_reasoning", "")
                
                nombre_estudiante = ""
                if student_data:
                    nombre_estudiante = student_data.get("credenciales", {}).get("nombre_completo", "").split(' ')[0]
                    saludo = f"{nombre_estudiante}, " if nombre_estudiante else ""
                else:
                    saludo = ""
                
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
                
                respuesta_final = (
                    f"{saludo}no encontré información específica sobre tu consulta en la base de conocimiento.\n\n"
                    f"✅ **He derivado tu solicitud a {channel}** {emoji_dept}\n\n"
                    f"Un agente especializado revisará tu caso y se pondrá en contacto contigo por correo electrónico "
                    f"en las próximas 24 horas.\n\n"
                    f"📧 **Mantente atento a tu correo institucional** para recibir la respuesta del agente."
                )
                
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
        # 3. stage == ready → interpretar y confirmar
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

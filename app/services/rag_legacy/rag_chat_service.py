# app/services/rag_chat_service.py
"""
Servicio RAG simplificado para chatbot.
Punto de entrada principal: classify_with_rag()
"""
from typing import Dict, List, Any
import re

# Imports de módulos internos
from ..config import TAU_NORMA, TAU_MIN, FEATURE_FLAGS, TAU_SKIP_CONFIRM
from .retriever import get_retriever
from ..intent_parser import (
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
from ..handoff import should_handoff

from .deterministic_router import route_by_taxonomy, get_folders_for_family
from .json_retriever import search_structured_info, format_json_item_as_document
from ..related_request_matcher import find_related_requests
from asgiref.sync import async_to_sync
from .unified_brain import unified_brain


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


def _execute_rag_search(
    intent_query: str,
    user_text: str,
    intent_slots: Dict[str, Any],
    conversation_history: List[Dict],
    student_data: Dict = None,
    category: str = None,
    subcategory: str = None
) -> Dict[str, Any]:
    """
    Función helper para ejecutar la búsqueda RAG.
    Extrae la lógica de búsqueda RAG para poder reutilizarla desde múltiples lugares.
    
    Args:
        intent_query: Query de intención para buscar
        user_text: Texto original del usuario
        intent_slots: Slots de intención
        conversation_history: Historial de conversación
        student_data: Datos del estudiante
        category: Categoría (opcional)
        subcategory: Subcategoría (opcional)
    
    Returns:
        Dict con la respuesta de la búsqueda RAG
    """
    try:
        # ===== BÚSQUEDA EN PDFs CON QUERY UNDERSTANDING INDUSTRIAL =====
        
        # ETAPA 0: ROUTING JERÁRQUICO (carpetas + títulos)
        # IMPORTANTE: Usar intent_query (que ya viene enriquecida con contexto si aplica) para routing
        routing_query = intent_query.strip() if intent_query and intent_query.strip() else user_text
        hierarchical_cands = hierarchical_candidates(routing_query, entities=None, queries=None)
        print(f"🔍 [Routing] Query usada para routing: '{routing_query[:100]}'")
        
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
        json_query = f"{canon_q} {user_text}".strip()
        json_results = search_structured_info(json_query, min_score=0.3, max_results=5)
        json_docs = [format_json_item_as_document(item) for item in json_results]
        
        if json_docs:
            print(f"📋 [JSON] Encontrados {len(json_docs)} resultados estructurados")
            fused_docs = fused_docs + json_docs
            if best_ascore and json_docs:
                json_boost = min(len(json_docs) * 0.02, 0.1)
                best_ascore["confidence"] = min(best_ascore["confidence"] + json_boost, 1.0)
                print(f"📈 [JSON Boost] Confianza ajustada: {best_ascore['confidence']:.3f} (+{json_boost:.3f})")
        
        # ETAPA 5: Intentar expansión con sinónimos si baja confianza
        if best_ascore["confidence"] < TAU_NORMA:
            syn_variants = _expand_with_synonyms(canon_q)
            print(f"🔎 [Synonyms] Probando {len(syn_variants)} variantes...")
            for q in syn_variants[:3]:
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
        
        # ETAPA 6: Variantes sin LLM (V2)
        if best_ascore["confidence"] < TAU_NORMA:
            print(f"🔎 [V2-Variants] Generando reformulaciones (sin LLM)...")
            qvars = gen_query_variants_llm(canon_q, n=3, use_llm=False)
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
        intent_query_effective = canon_q
        
        # Logging final
        print(f"📊 RESULTADO FINAL:")
        print(f"   Confidence: {ascore.get('confidence', 0):.3f}")
        print(f"   Docs recuperados: {ascore.get('non_empty_docs', 0)}")
        print(f"   Verdict: {ascore.get('verdict', 'N/A')}")
        print(f"   Docs fusionados: {len(fused_docs)}")

        # Nivel 1: Alta confianza (>= TAU_NORMA) → responder directo
        if ascore["confidence"] >= TAU_NORMA:
            try:
                if FEATURE_FLAGS.get("neutral_response"):
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                else:
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                
                return {
                    "category": category or "Reglamento",
                    "subcategory": subcategory or "Consulta",
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
                pass

        # Nivel 3: Baja confianza pero HAY contenido
        nivel3_requiere_handoff = False
        if ascore["confidence"] >= TAU_MIN and ascore["verdict"] in ("yes", "unknown") and (ascore["non_empty_docs"] > 0 or len(fused_docs) > 0):
            try:
                if FEATURE_FLAGS.get("neutral_response"):
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                else:
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                
                ans = result["respuesta"]
                has_info = result.get("has_information", True)
                llm_confidence_level = result.get("llm_confidence", "medium")
                
                print(f"🤖 [LLM Evaluation] has_info={has_info}, confidence={llm_confidence_level}")
                
                if has_info:
                    cat = category or "Reglamento"
                    sub = subcategory or "Consulta"
                    intent_short = intent_slots.get("intent_short", "")
                    
                    INTENCIONES_CRITICAS_OBLIGATORIAS = {
                        "cambio_de_paralelo",
                        "cambio_de_curso", 
                        "cambio_de_carrera",
                        "anulacion_matricula",
                        "homologacion",
                        "convalidacion"
                    }
                    
                    if intent_short in INTENCIONES_CRITICAS_OBLIGATORIAS:
                        print(f"⚠️ [Nivel 3] Intención crítica obligatoria: {intent_short}, marcando para derivación")
                        nivel3_requiere_handoff = True
                    else:
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
                pass
        
        # Nivel 3.5: MUY baja confianza pero HAY documentos
        if not nivel3_requiere_handoff and (ascore["non_empty_docs"] > 0 or len(fused_docs) > 0):
            try:
                if FEATURE_FLAGS.get("neutral_response"):
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=False, docs_override=fused_docs if fused_docs else None)
                else:
                    result = responder_desde_pdfs(intent_query_effective, incluir_fuente=True, docs_override=fused_docs if fused_docs else None)
                
                ans = result["respuesta"]
                has_info = result.get("has_information", True)
                
                print(f"🤖 [LLM Evaluation Nivel 3.5] has_info={has_info}")
                
                if has_info:
                    return {
                        "category": category or "Reglamento",
                        "subcategory": subcategory or "Consulta",
                        "confidence": 0.4,
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
                pass

        # Nivel 4: REALMENTE no hay nada → derivar al agente
        original_user_query = intent_query
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("user", "student", "estudiante"):
                msg_text = msg.get("content") or msg.get("text", "")
                if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text):
                    original_user_query = msg_text
                    break
        
        print(f"📝 [Original Query] {original_user_query[:80]}...")
        
        handoff_decision = should_handoff(
            confidence=ascore["confidence"],
            intent_short=intent_slots.get("intent_short", ""),
            category=None,
            subcategory=None,
            slots=intent_slots,
            history=conversation_history,
            user_text=original_user_query
        )
        
        cat = handoff_decision.get("categoria") or category or "Consultas varias"
        sub = handoff_decision.get("subcategoria") or subcategory or "Consultas varias"
        
        from .handoff import get_departamento_real
        channel = handoff_decision.get("handoff_channel")
        if not channel:
            categoria_fallback = handoff_decision.get("categoria") or cat or "Consultas varias"
            subcategoria_fallback = handoff_decision.get("subcategoria") or sub or "Consultas varias"
            department_fallback = handoff_decision.get("department", "general")
            channel = get_departamento_real(categoria_fallback, subcategoria_fallback, department_fallback, original_user_query)
        department = handoff_decision.get("department", "general")
        llm_reasoning = handoff_decision.get("llm_reasoning", "")
        
        primer_nombre = _obtener_primer_nombre(student_data)
        
        emoji_dept = {
            "académico": "🎓",
            "financiero": "💰",
            "bienestar": "🏥",
            "administrativo": "📋",
            "tic": "💻",
            "biblioteca": "📚",
            "general": "💁"
        }.get(department, "💁")
        
        if primer_nombre:
            mensaje_inicio = f"{primer_nombre}, "
        else:
            mensaje_inicio = ""
        
        # En lugar de transferir automáticamente, pedir más detalles al usuario
        # SIEMPRE pedir detalles + archivo
        respuesta_final = (
            f"{mensaje_inicio}No tengo respuesta para ello. 😔\n\n"
            f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{channel}**? {emoji_dept}\n\n"
            f"Para enviar tu solicitud, necesito que:\n"
            f"1. Describes nuevamente tu solicitud con todos los detalles\n"
            f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
        )
        
        if primer_nombre:
            print(f"✅ [Saludo] Primer nombre '{primer_nombre}' incluido en mensaje de handoff")
        else:
            print(f"⚠️ [Saludo] No se pudo obtener primer nombre (student_data disponible: {student_data is not None})")
        
        print(f"🎯 [Handoff Decision] - Pidiendo más detalles + archivo")
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
            "handoff_auto": False,  # Cambiar a False para no enviar automáticamente
            "needs_handoff_details": True,  # Nuevo flag para pedir más detalles
            "needs_handoff_file": True,  # ✅ SIEMPRE requerir archivo cuando se piden más detalles
            "handoff_file_max_size_mb": 4,   # ✅ Máximo 4MB
            "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],  # ✅ Tipos permitidos
            "handoff_reason": handoff_decision.get("handoff_reason"),
            "handoff_channel": channel,  # Guardar el canal para usarlo después
            "handoff_department": handoff_decision.get("department"),
            "handoff_llm_reasoning": handoff_decision.get("llm_reasoning"),
            "answer_type": handoff_decision.get("answer_type"),
            "intent_slots": intent_slots,
            "trace": {
                "intent_query": intent_query,
                "answerability": ascore,
                "reason": "No hay contenido suficiente en PDFs para responder",
                "handoff": handoff_decision
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "category": None,
            "subcategory": None,
            "confidence": 0.0,
            "summary": f"Ocurrió un error al buscar en el reglamento: {str(e)}",
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": None
        }


def classify_with_rag(
    user_text: str, 
    conversation_history: List[Dict] = None,
    category: str = None,
    subcategory: str = None,
    student_data: Dict = None,
    uploaded_file: Any = None  # Archivo subido (opcional)
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
    stage = "ready"  # ready, await_confirm, await_related_request, await_more_details, await_handoff_details
    pending_slots = None
    related_request_rejected = False  # Flag para indicar si el usuario rechazó una solicitud relacionada
    handoff_channel = None  # Canal de handoff guardado

    # Buscar en el historial el último estado
    for i, msg in enumerate(reversed(conversation_history)):
        role = msg.get("role") or msg.get("who")
        if role not in ("bot", "assistant"):
            continue

        # Verificar si el último mensaje del bot necesitaba confirmación
        needs_confirm = msg.get("needs_confirmation", False)
        confirmed_status = msg.get("confirmed")
        slot_payload = msg.get("intent_slots")
        needs_related_selection = msg.get("needs_related_request_selection", False)
        needs_more_details = msg.get("needs_more_details", False)
        needs_handoff_details = msg.get("needs_handoff_details", False)
        
        # Buscar también en meta (el frontend guarda data completa ahí)
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
            if not needs_more_details:
                needs_more_details = meta.get("needs_more_details", False)
            if not needs_handoff_details:
                needs_handoff_details = meta.get("needs_handoff_details", False)
            # Obtener el canal de handoff del mensaje anterior
            if not handoff_channel:
                handoff_channel = meta.get("handoff_channel")

        # --- RESET EXPLÍCITO SI YA SE ENVIÓ EL HANDOFF ---
        handoff_sent_flag = msg.get("handoff_sent")
        if not handoff_sent_flag and isinstance(meta, dict):
            handoff_sent_flag = meta.get("handoff_sent")

        # Si el último mensaje del bot confirmó envío, resetea a ready
        if handoff_sent_flag:
            stage = "ready"
            pending_slots = None
            handoff_channel = None
            break

        # Verificar si el bot pidió detalles de handoff
        if needs_handoff_details:
            stage = "await_handoff_details"
            if slot_payload:
                pending_slots = slot_payload
            if handoff_channel:
                break
            # Si no se encontró el canal en meta, buscar en el mensaje
            if not handoff_channel:
                handoff_channel = msg.get("handoff_channel")
            break

        # Verificar si el bot pidió más detalles (después de rechazar solicitud relacionada)
        if needs_more_details:
            related_request_rejected = True
            stage = "await_more_details"
            if slot_payload:
                pending_slots = slot_payload
            break

        # Si el usuario negó explícitamente (confirmed=False), resetear estado
        if confirmed_status is False:
            stage = "ready"
            pending_slots = None
            break

        # Detectar estado de solicitud relacionada (sin confirmación)
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

            # Cerebro unificado: una sola llamada LLM para intención+contexto+taxonomía (y modo de resolución)
            print("🧠 [Unified Brain] Invocando orquestador...")
            # ✅ Intenta async; si el loop cae, fallback a sync (REST)
            try:
                brain = async_to_sync(unified_brain)(
                    user_text=user_text,
                    history=conversation_history,
                    student_profile=student_data or {}
                )
            except RuntimeError as e:
                if "Event loop is closed" in str(e):
                    from .unified_brain import unified_brain_sync
                    print("⚠️ Loop cerrado en gRPC aio; usando unified_brain_sync (REST).")
                    brain = unified_brain_sync(
                        user_text=user_text,
                        history=conversation_history,
                        student_profile=student_data or {}
                    )
                else:
                    raise
            enriched_text = brain.enriched_query or user_text
            
            # Log del contexto detectado
            if brain.needs_context:
                print(f"🔗 [Context] Query enriquecida detectada:")
                print(f"   Original: {user_text}")
                print(f"   Enriquecida: {enriched_text}")
            else:
                print(f"🔵 [Context] Query independiente, sin enriquecimiento necesario")

            # ========== BLOQUE DURO: RESPETO A LA DECISIÓN DEL CEREBRO ==========
            print(f"🧩 [Brain Decision] Mode={brain.resolution_mode}, Score={brain.operationality_score}")
            if getattr(brain, "resolution_mode", "informativa") == "operativa" or getattr(brain, "operationality_score", 0.0) >= 0.60:
                perfil = student_data or {}
                student_name = (
                    perfil.get("credenciales", {}).get("nombre_completo")
                    if perfil.get("credenciales") else None
                )
                if not student_name:
                    student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
                student_id = (
                    perfil.get("informacion_academica", {}).get("matricula")
                    if perfil.get("informacion_academica") else None
                )
                if not student_id:
                    student_id = perfil.get("matricula") or perfil.get("id") or "—"
                depto = getattr(brain, "handoff_depto", None) or "Servicios de Secretaría"

                print("⚡ [SHORT-CIRCUIT] Operativa — pedir detalles para enviar al agente")
                saludo = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
                ask_msg = (
                    f"{saludo}No tengo respuesta para ello. 😔\n\n"
                    f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{depto}**? 💁\n\n"
                    f"Para enviar tu solicitud, necesito que:\n"
                    f"1. Describes nuevamente tu solicitud con todos los detalles\n"
                    f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
                )
                return {
                    "ok": True,
                    "mode": "operativa",
                    "handoff": True,
                    "department": depto,
                    "ticket_title": getattr(brain, "ticket_title", None) or getattr(brain, "intent_short", ""),
                    "taxonomy": getattr(brain, "taxonomy", {}) or {},
                    "summary": ask_msg,
                    "handoff_sent": False,
                    "handoff_channel": depto,
                    "needs_handoff_details": True,
                    "needs_handoff_file": True,      # ✅ Requiere archivo
                    "handoff_file_max_size_mb": 4,   # ✅ Máximo 4MB
                    "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],  # ✅ Tipos permitidos
                    "handoff_auto": False,
                    "as_chat_message": True,
                    "allow_new_query": False,     # 🔒 aún no; falta enviar
                    "reset_context": False,       # 🔒 aún no; falta enviar
                    "llm_decision": {
                        "resolution_mode": getattr(brain, "resolution_mode", "informativa"),
                        "operationality_score": getattr(brain, "operationality_score", 0.0),
                        "reasons": getattr(brain, "decision_reasons", [])
                    }
                }
            # ==========================================================
            
            # PRIORIDAD 1: Si el cerebro detectó contexto y generó enriched_query, USARLA SIEMPRE
            # (es la mejor porque combina pregunta actual + contexto conversacional)
            if brain.needs_context and enriched_text and enriched_text.strip() != user_text.strip():
                intent_query = enriched_text.strip()
                print(f"✅ [Context] Usando query enriquecida del cerebro (con contexto): {intent_query}")
            else:
                # PRIORIDAD 2: Usar query_rag del cerebro (debe estar enriquecida si hay contexto)
                brain_query_rag = getattr(brain, "query_rag", None)
                if brain_query_rag and brain_query_rag.strip():
                    # Si hay contexto pero query_rag no está enriquecida, preferir enriched_query
                    if brain.needs_context and enriched_text and enriched_text.strip() != user_text.strip():
                        intent_query = enriched_text.strip()
                        print(f"✅ [Context Override] Usando enriched_query en lugar de query_rag (tiene contexto)")
                    else:
                        intent_query = brain_query_rag.strip()
                        print(f"✅ [Brain] Usando query_rag del cerebro: {intent_query}")
                else:
                    # PRIORIDAD 3: Si hay contexto, usar enriched_query incluso si query_rag está vacía
                    if brain.needs_context and enriched_text and enriched_text.strip() != user_text.strip():
                        intent_query = enriched_text.strip()
                        print(f"✅ [Context Fallback] Usando enriched_query (query_rag vacía): {intent_query}")
                    else:
                        # PRIORIDAD 4: Construir desde intent_slots
                        intent_query = intent_slots.get("intent_short", "").strip()
                        if not intent_query:
                            intent_query_parts = [
                                intent_slots.get("accion", ""),
                                intent_slots.get("objeto", ""),
                                intent_slots.get("asignatura", ""),
                                intent_slots.get("detalle_libre", "")
                            ]
                            intent_query = " ".join([p for p in intent_query_parts if p]).strip()
                        
                        # PRIORIDAD 5: Fallback a texto original
                        if not intent_query:
                            intent_query = user_text.strip()
                        print(f"✅ [Fallback] Usando query construida: {intent_query}")

            # Adoptar taxonomía del cerebro si no viene de fuera
            try:
                brain_cat = None
                brain_sub = None
                if getattr(brain, "taxonomy", None) and isinstance(brain.taxonomy, dict):
                    brain_cat = brain.taxonomy.get("category")
                    brain_sub = brain.taxonomy.get("subcategory")
                if not category and brain_cat:
                    category = brain_cat
                if not subcategory and brain_sub:
                    subcategory = brain_sub
            except Exception:
                pass

            # ===== VERIFICAR SI NECESITA CONFIRMACIÓN (usar confirm_text del cerebro si tiene contexto) =====
            # Si el cerebro detectó que necesita confirmación Y tiene confirm_text, usarlo
            # (especialmente importante cuando hay contexto conversacional)
            if brain.needs_confirmation and brain.confirm_text:
                # El cerebro ya generó confirm_text con contexto, usarlo directamente
                print(f"✅ [Confirmation] Usando confirm_text del cerebro (con contexto): {brain.confirm_text}")
                return {
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": brain.confidence,
                    "summary": brain.confirm_text,  # Usar confirm_text del cerebro que ya tiene contexto
                    "campos_requeridos": [],
                    "needs_confirmation": True,
                    "confirmed": None,
                    "intent_slots": intent_slots,
                    "reasoning": f"Confirmación generada con contexto conversacional"
                }

            # ===== BUSCAR SOLICITUDES RELACIONADAS =====
            # Obtener el texto original de la solicitud del usuario
            original_user_request = user_text
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("user", "student", "estudiante"):
                    msg_text = msg.get("content") or msg.get("text", "")
                    # Ignorar confirmaciones simples
                    if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text):
                        original_user_request = msg_text
                        break

            print(f"🔍 [Related Requests] Buscando solicitudes relacionadas...")
            print(f"   User request: {original_user_request[:100]}")
            print(f"   Student data disponible: {student_data is not None}")
            if student_data:
                from .related_request_matcher import load_student_requests
                solicitudes = load_student_requests(student_data)
                print(f"   Solicitudes encontradas: {len(solicitudes)}")
            
            # Buscar solicitudes relacionadas
            related_requests_result = find_related_requests(
                user_request=original_user_request,
                intent_slots=intent_slots,
                student_data=student_data,
                max_results=3
            )
            
            print(f"🔍 [Related Requests] Resultado: {len(related_requests_result.get('related_requests', []))} solicitudes relacionadas")
            print(f"   No related: {related_requests_result.get('no_related', False)}")
            print(f"   Reasoning: {related_requests_result.get('reasoning', 'N/A')[:100]}")
            
            # Si hay solicitudes relacionadas, retornarlas para que el usuario seleccione
            if related_requests_result.get("related_requests") and not related_requests_result.get("no_related"):
                related_requests = related_requests_result.get("related_requests", [])
                reasoning = related_requests_result.get("reasoning", "")
                
                # Construir mensaje para mostrar las solicitudes relacionadas
                primer_nombre = _obtener_primer_nombre(student_data)
                mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                
                mensaje = f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:\n\n"
                
                for i, req in enumerate(related_requests, 1):
                    mensaje += f"{i}. {req.get('display', req.get('id', 'Solicitud'))}\n"
                
                mensaje += "\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar."
                
                return {
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": 0.85,
                    "summary": mensaje,
                    "campos_requeridos": [],
                    "needs_confirmation": False,
                    "needs_related_request_selection": True,
                    "related_requests": related_requests,
                    "no_related_request_option": True,
                    "confirmed": True,
                    "intent_slots": intent_slots,
                    "reasoning": reasoning
                }

            # Si no hay solicitudes relacionadas, ejecutar búsqueda RAG directamente
            return _execute_rag_search(
                intent_query=intent_query,
                user_text=original_user_request,
                intent_slots=intent_slots,
                conversation_history=conversation_history,
                student_data=student_data,
                category=category,
                subcategory=subcategory
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
    
    # 3. Etapa de selección de solicitud relacionada
    elif stage == "await_related_request":
        # El usuario puede seleccionar una solicitud o decir "no hay solicitud relacionada"
        # Detectar si el usuario seleccionó una solicitud (por ID o índice)
        selected_request_id = None
        
        print(f"🔍 [Await Related Request] Procesando selección...")
        print(f"   User text: '{user_text}'")
        print(f"   User text type: {type(user_text)}")
        
        # Convertir user_text a string si es necesario
        user_text_str = str(user_text) if user_text is not None else ""
        user_text_lower = user_text_str.lower().strip()
        
        print(f"   User text (processed): '{user_text_str}'")
        print(f"   User text lower: '{user_text_lower}'")
        
        # Buscar en el historial las solicitudes relacionadas mostradas
        related_requests_shown = []
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("bot", "assistant"):
                meta = msg.get("meta") or {}
                if isinstance(meta, dict) and meta.get("related_requests"):
                    related_requests_shown = meta.get("related_requests", [])
                    print(f"   Solicitudes relacionadas encontradas en historial: {len(related_requests_shown)}")
                    for i, req in enumerate(related_requests_shown, 1):
                        print(f"     {i}. ID: {req.get('id')}, Display: {req.get('display', 'N/A')[:50]}")
                    break
        
        if not related_requests_shown:
            print(f"   ⚠️ No se encontraron solicitudes relacionadas en el historial")
        
        # Detectar si el usuario escribió "no" o "no hay" o similar
        no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", "sin relacionar", "no hay solicitud relacionada"]
        
        # Verificar si el usuario dice "no hay" (pero no solo "no" que podría ser una confirmación)
        user_said_no_related = any(keyword in user_text_lower for keyword in no_related_keywords)
        
        if user_said_no_related:
            # Usuario eligió continuar sin relacionar
            # Continuar con el flujo normal de RAG ejecutando la búsqueda directamente
            # Recuperar intent_slots
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
            
            # Obtener el texto original de la solicitud
            original_user_request = user_text
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("user", "student", "estudiante"):
                    msg_text = msg.get("content") or msg.get("text", "")
                    # Buscar la solicitud original del usuario (antes de las confirmaciones)
                    if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text) and not any(kw in msg_text.lower() for kw in no_related_keywords):
                        original_user_request = msg_text
                        break
            
            # Construir query de intención
            intent_query = intent_slots.get("intent_short", "").strip()
            if not intent_query:
                intent_query_parts = [
                    intent_slots.get("accion", ""),
                    intent_slots.get("objeto", ""),
                    intent_slots.get("asignatura", ""),
                    intent_slots.get("detalle_libre", "")
                ]
                intent_query = " ".join([p for p in intent_query_parts if p]).strip()
            
            if not intent_query:
                intent_query = original_user_request.strip()
            
            # Ejecutar búsqueda RAG sin solicitud relacionada
            return _execute_rag_search(
                intent_query=intent_query,
                user_text=original_user_request,
                intent_slots=intent_slots,
                conversation_history=conversation_history,
                student_data=student_data,
                category=category,
                subcategory=subcategory
            )
        
        # Intentar detectar si el usuario seleccionó una solicitud por ID o número
        # Primero, verificar si el texto es directamente un ID numérico
        try:
            # Si el texto es solo un número, podría ser el ID directo o el índice
            if user_text_str.isdigit():
                numeric_value = int(user_text_str)
                print(f"   Texto es numérico: {numeric_value}")
                
                # Verificar si es un ID de solicitud (comparar con los IDs de las solicitudes mostradas)
                for req in related_requests_shown:
                    req_id = req.get("id")
                    # Comparar tanto como string como número
                    if req_id is not None:
                        req_id_str = str(req_id)
                        req_id_num = None
                        try:
                            req_id_num = int(req_id) if isinstance(req_id, (int, str)) and str(req_id).isdigit() else None
                        except (ValueError, TypeError):
                            pass
                        
                        if req_id_str == user_text_str or req_id_num == numeric_value:
                            selected_request_id = req_id
                            print(f"   ✅ Encontrado por ID directo: {selected_request_id}")
                            break
                
                # Si no se encontró por ID, intentar como índice (1-based)
                if not selected_request_id and 1 <= numeric_value <= len(related_requests_shown):
                    index = numeric_value - 1
                    selected_request_id = related_requests_shown[index].get("id")
                    print(f"   ✅ Encontrado por índice: {selected_request_id} (índice {index})")
        except (ValueError, TypeError) as e:
            print(f"   ⚠️ Error al procesar texto numérico: {e}")
        
        # Si aún no se encontró, buscar ID de solicitud en el texto (como substring)
        if not selected_request_id:
            for req in related_requests_shown:
                req_id = req.get("id")
                if req_id is not None:
                    req_id_str = str(req_id)
                    # Buscar el ID como substring en el texto
                    if req_id_str in user_text_str or req_id_str.lower() in user_text_lower:
                        selected_request_id = req_id
                        print(f"   ✅ Encontrado por substring: {selected_request_id}")
                        break
        
        # Si no se encontró por ID, intentar por número (1, 2, 3, etc.) en el texto
        if not selected_request_id:
            import re
            number_match = re.search(r'\b([1-9])\b', user_text_str)
            if number_match:
                index = int(number_match.group(1)) - 1
                if 0 <= index < len(related_requests_shown):
                    selected_request_id = related_requests_shown[index].get("id")
                    print(f"   ✅ Encontrado por regex número: {selected_request_id} (índice {index})")
        
        print(f"   Selected request ID: {selected_request_id}")
        
        if selected_request_id:
            # Usuario seleccionó una solicitud relacionada
            # Ejecutar RAG directamente con el contexto de la solicitud relacionada (sin confirmación)
            # Buscar la solicitud completa
            selected_request = None
            for req in related_requests_shown:
                if req.get("id") == selected_request_id:
                    selected_request = req
                    break
            
            if selected_request:
                # Recuperar intent_slots
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
                
                # Obtener el texto original de la solicitud
                original_user_request = user_text_str
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        msg_text = msg.get("content") or msg.get("text", "")
                        if msg_text and not es_confirmacion_positiva(msg_text) and not es_confirmacion_negativa(msg_text) and not any(kw in str(msg_text).lower() for kw in no_related_keywords):
                            original_user_request = str(msg_text)
                            break
                
                # Enriquecer la query con información de la solicitud relacionada
                relacionada_display = selected_request.get("display", selected_request.get("id", "Solicitud"))
                relacionada_descripcion = selected_request.get("descripcion", "")
                relacionada_tipo = selected_request.get("tipo", "")
                relacionada_estado = selected_request.get("estado", "")
                
                # Construir query enriquecida con contexto de la solicitud relacionada
                intent_query_original = intent_slots.get("intent_short", "").strip()
                if not intent_query_original:
                    intent_query_parts = [
                        intent_slots.get("accion", ""),
                        intent_slots.get("objeto", ""),
                        intent_slots.get("asignatura", ""),
                        intent_slots.get("detalle_libre", "")
                    ]
                    intent_query_original = " ".join([p for p in intent_query_parts if p]).strip()
                
                if not intent_query_original:
                    intent_query_original = original_user_request
                
                # Enriquecer con información de la solicitud relacionada
                relacionada_context_parts = []
                if relacionada_tipo:
                    relacionada_context_parts.append(f"tipo: {relacionada_tipo}")
                if relacionada_estado:
                    relacionada_context_parts.append(f"estado: {relacionada_estado}")
                if relacionada_descripcion:
                    relacionada_context_parts.append(f"descripción: {relacionada_descripcion[:150]}")
                
                relacionada_context = " ".join(relacionada_context_parts)
                intent_query_enriched = f"{intent_query_original} relacionado con solicitud {relacionada_context}".strip()
                enriched_user_text = f"{original_user_request} (contexto: solicitud relacionada {relacionada_display})"
                
                print(f"🔗 [Related Request Selected] Ejecutando RAG con solicitud relacionada")
                print(f"   Solicitud relacionada: {relacionada_display}")
                print(f"   Query enriquecida: {intent_query_enriched[:150]}")
                
                # Ejecutar búsqueda RAG con contexto enriquecido
                return _execute_rag_search(
                    intent_query=intent_query_enriched,
                    user_text=enriched_user_text,
                    intent_slots=intent_slots,
                    conversation_history=conversation_history,
                    student_data=student_data,
                    category=category,
                    subcategory=subcategory
                )
        
        # Si no se detectó selección clara, pedir aclaración
        # Pero solo si no se seleccionó ninguna y no se dijo "no hay"
        if not selected_request_id and not user_said_no_related:
            # Verificar si el usuario escribió un número que no está en el rango
            import re
            number_match = re.search(r'\b([1-9])\b', user_text)
            if number_match:
                index = int(number_match.group(1)) - 1
                if index < 0 or index >= len(related_requests_shown):
                    return {
                        "category": category,
                        "subcategory": subcategory,
                        "confidence": 0.7,
                        "summary": f"No pude entender tu selección. Por favor, indica un número entre 1 y {len(related_requests_shown)} o escribe 'no hay solicitud relacionada' para continuar.",
                        "campos_requeridos": [],
                        "needs_confirmation": False,
                        "needs_related_request_selection": True,
                        "related_requests": related_requests_shown,
                        "no_related_request_option": True,
                        "confirmed": True,
                        "intent_slots": pending_slots
                    }
            
            return {
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.7,
                "summary": "No pude entender tu selección. Por favor, indica el número de la solicitud relacionada o escribe 'no hay solicitud relacionada' para continuar.",
                "campos_requeridos": [],
                "needs_confirmation": False,
                "needs_related_request_selection": True,
                "related_requests": related_requests_shown,
                "no_related_request_option": True,
                "confirmed": True,
                "intent_slots": pending_slots
            }
    
    # 4. Etapa de más detalles después de rechazar solicitud relacionada
    elif stage == "await_more_details":
        # El usuario rechazó una solicitud relacionada y ahora está proporcionando más detalles
        # Ejecutar búsqueda RAG directamente con los detalles proporcionados
        # Recuperar intent_slots original
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
        
        # Obtener el texto original de la solicitud (antes de confirmaciones y selecciones)
        original_user_request = None
        no_related_keywords = ["no hay solicitud relacionada", "no hay", "ninguna", "ninguna solicitud", "no tiene"]
        confirmacion_keywords = ["si", "sí", "correcto", "exacto", "sip", "claro", "no", "incorrecto", "mal", "nop"]
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("user", "student", "estudiante"):
                msg_text = msg.get("content") or msg.get("text", "")
                if not msg_text:
                    continue
                msg_text_lower = msg_text.lower().strip()
                
                # Saltar confirmaciones (positivas y negativas)
                if es_confirmacion_positiva(msg_text) or es_confirmacion_negativa(msg_text):
                    continue
                
                # Saltar selecciones de "no hay solicitud relacionada"
                if any(kw in msg_text_lower for kw in no_related_keywords):
                    continue
                
                # Saltar selecciones de solicitudes relacionadas (formato: "SOL-2025-XXX" o solo números)
                # Las selecciones suelen ser muy cortas o contienen IDs específicos
                if len(msg_text.strip()) < 20 and ("sol-" in msg_text_lower or msg_text_lower.strip().isdigit()):
                    continue
                
                # Si el mensaje es muy corto y solo contiene confirmaciones, saltarlo
                if len(msg_text.strip()) <= 3 and any(kw in msg_text_lower for kw in confirmacion_keywords):
                    continue
                
                # Este debería ser el mensaje original de la solicitud
                original_user_request = msg_text
                break
        
        # Si no se encontró la solicitud original, usar el texto actual del usuario
        if not original_user_request:
            original_user_request = user_text
        
        # Combinar la solicitud original con los detalles adicionales
        enriched_user_text = f"{original_user_request} {user_text}".strip() if original_user_request != user_text else user_text
        
        # Re-interpretar con el texto enriquecido para actualizar los slots
        if intent_slots:
            # Enriquecer los slots con los detalles adicionales
            enriched_slots = interpretar_intencion_principal(enriched_user_text)
            # Preservar campos importantes de los slots originales si están presentes
            if not enriched_slots.get("intent_short") and intent_slots.get("intent_short"):
                enriched_slots["intent_short"] = intent_slots.get("intent_short")
            intent_slots = enriched_slots
        else:
            # Si no se encontraron slots, interpretar el texto enriquecido
            intent_slots = interpretar_intencion_principal(enriched_user_text)
        
        # Construir query de intención
        intent_query = intent_slots.get("intent_short", "").strip()
        if not intent_query:
            intent_query_parts = [
                intent_slots.get("accion", ""),
                intent_slots.get("objeto", ""),
                intent_slots.get("asignatura", ""),
                intent_slots.get("detalle_libre", "")
            ]
            intent_query = " ".join([p for p in intent_query_parts if p]).strip()
        
        if not intent_query:
            intent_query = enriched_user_text.strip()
        
        # Ejecutar búsqueda RAG con los detalles adicionales
        return _execute_rag_search(
            intent_query=intent_query,
            user_text=enriched_user_text,
            intent_slots=intent_slots,
            conversation_history=conversation_history,
            student_data=student_data,
            category=category,
            subcategory=subcategory
        )
    
    # 5. Etapa de detalles de handoff (usuario proporciona más detalles para enviar al departamento)
    elif stage == "await_handoff_details":
        # Obtener canal de handoff
        if not handoff_channel:
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    meta = msg.get("meta") or {}
                    if isinstance(meta, dict) and meta.get("handoff_channel"):
                        handoff_channel = meta.get("handoff_channel")
                        break
        if not handoff_channel:
            handoff_channel = "Departamento de Atención al Estudiante"
        
        # Verificar si el usuario ya proporcionó detalles (cualquier texto que no sea solo confirmación)
        details_text = (user_text or "").strip()
        is_confirmation_only = es_confirmacion_positiva(details_text) or es_confirmacion_negativa(details_text)
        
        # REGLA SIMPLE: Cuando se piden más detalles, SIEMPRE se requiere archivo
        # Aceptar solo si tiene detalles Y archivo subido
        has_substantial_details = len(details_text) > 0 and not is_confirmation_only
        has_file = uploaded_file is not None
        
        if has_substantial_details and has_file:
            # Usuario proporcionó detalles → confirmar envío y resetear para nueva consulta
            primer_nombre = _obtener_primer_nombre(student_data)
            mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
            
            confirm_msg = (
                f"{mensaje_inicio}✅ Tu solicitud fue enviada exitosamente al departamento **{handoff_channel}**. "
                "Un agente se pondrá en contacto contigo pronto."
            )
            
            # Log en backend
            print(f"\n{'='*60}")
            print(f"📤 SOLICITUD ENVIADA A LA GENTE")
            print(f"{'='*60}")
            if student_data:
                nombre = student_data.get("credenciales", {}).get("nombre_completo", "Usuario")
                matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A")
                print(f"👤 Estudiante: {nombre} ({matricula})")
            print(f"🏢 Departamento: {handoff_channel}")
            print(f"📝 Detalles de la solicitud: {details_text[:200]}")
            if uploaded_file:
                file_name = getattr(uploaded_file, "name", "archivo") if hasattr(uploaded_file, "name") else str(uploaded_file)
                print(f"📎 Archivo adjunto: {file_name}")
            print(f"{'='*60}\n")
            
            return {
                "category": category or "Consultas varias",
                "subcategory": subcategory or "Consultas varias",
                "confidence": 1.0,
                "summary": confirm_msg,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": True,
                "handoff": True,
                "handoff_sent": True,              # ✅ clave para el reset
                "handoff_channel": handoff_channel,
                "handoff_details": details_text,
                "handoff_file": uploaded_file,     # ✅ Archivo subido (si existe)
                "as_chat_message": True,
                "needs_handoff_details": False,    # ✅ ya no pedimos más detalles
                "needs_handoff_file": False,       # ✅ ya no requiere archivo
                "handoff_auto": False,
                "reset_context": True,             # ✅ ayuda al frontend a limpiar
                "allow_new_query": True,           # ✅ hint UX
                "intent_slots": pending_slots or {}
            }
        else:
            # Aún no proporcionó detalles sustanciales o falta archivo → seguir pidiendo
            # SIEMPRE pedir ambos: detalles + archivo
            missing_items = []
            if not has_substantial_details:
                missing_items.append("describas nuevamente tu solicitud con todos los detalles")
            if not has_file:
                missing_items.append("subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud")
            
            # Construir mensaje con lo que falta
            if missing_items:
                items_list = "\n".join([f"{i+1}. {item}" for i, item in enumerate(missing_items)])
                ask_msg = (
                    f"No tengo respuesta para ello. 😔\n\n"
                    f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{handoff_channel}**? 💁\n\n"
                    f"Para enviar tu solicitud, necesito que:\n{items_list}"
                )
            else:
                # Fallback: pedir ambos siempre
                ask_msg = (
                    f"No tengo respuesta para ello. 😔\n\n"
                    f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{handoff_channel}**? 💁\n\n"
                    f"Para enviar tu solicitud, necesito que:\n"
                    f"1. Describes nuevamente tu solicitud con todos los detalles\n"
                    f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
                )
            
            # SIEMPRE establecer needs_handoff_file=True cuando se piden más detalles
            return {
                "category": category or "Consultas varias",
                "subcategory": subcategory or "Consultas varias",
                "confidence": 1.0,
                "summary": ask_msg,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": True,
                "handoff": True,
                "handoff_sent": False,
                "handoff_channel": handoff_channel,
                "as_chat_message": True,
                "needs_handoff_details": True,
                "needs_handoff_file": True,  # ✅ SIEMPRE requerir archivo cuando se piden más detalles
                "handoff_file_max_size_mb": 4,   # ✅ Máximo 4MB
                "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],  # ✅ Tipos permitidos
                "handoff_auto": False,
                "intent_slots": pending_slots or {}
            }
    
    # 6. Flujo normal (stage == "ready")
    if stage == "ready":
        # ===== INVOCAR CEREBRO UNIFICADO PRIMERO (para detectar contexto conversacional) =====
        print("🧠 [Unified Brain - Ready] Invocando orquestador para detectar contexto...")
        try:
            brain = async_to_sync(unified_brain)(
                user_text=user_text,
                history=conversation_history,
                student_profile=student_data or {}
            )
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                from .unified_brain import unified_brain_sync
                print("⚠️ Loop cerrado en gRPC aio; usando unified_brain_sync (REST).")
                brain = unified_brain_sync(
                    user_text=user_text,
                    history=conversation_history,
                    student_profile=student_data or {}
                )
            else:
                raise
        
        enriched_text = brain.enriched_query or user_text
        
        # Log del contexto detectado
        if brain.needs_context:
            print(f"🔗 [Context - Ready] Query enriquecida detectada:")
            print(f"   Original: {user_text}")
            print(f"   Enriquecida: {enriched_text}")
        else:
            print(f"🔵 [Context - Ready] Query independiente, sin enriquecimiento necesario")
        
        # ===== VERIFICAR SI NECESITA CONFIRMACIÓN (usar confirm_text del cerebro si tiene contexto) =====
        # Si el cerebro detectó que necesita confirmación Y tiene confirm_text, usarlo
        if brain.needs_confirmation and brain.confirm_text:
            # El cerebro ya generó confirm_text con contexto, usarlo directamente
            print(f"✅ [Confirmation - Ready] Usando confirm_text del cerebro (con contexto): {brain.confirm_text}")
            # Adoptar taxonomía del cerebro
            brain_cat = brain.taxonomy.get("category") if brain.taxonomy else None
            brain_sub = brain.taxonomy.get("subcategory") if brain.taxonomy else None
            return {
                "category": brain_cat or category,
                "subcategory": brain_sub or subcategory,
                "confidence": brain.confidence,
                "summary": brain.confirm_text,  # Usar confirm_text del cerebro que ya tiene contexto
                "campos_requeridos": [],
                "needs_confirmation": True,
                "confirmed": None,
                "intent_slots": {"intent_short": brain.intent_short} if brain.intent_short else {},
                "reasoning": f"Confirmación generada con contexto conversacional"
            }
        
        # ===== RESPETO A LA DECISIÓN DEL CEREBRO (operativa vs informativa) =====
        if getattr(brain, "resolution_mode", "informativa") == "operativa" or getattr(brain, "operationality_score", 0.0) >= 0.60:
            perfil = student_data or {}
            student_name = (
                perfil.get("credenciales", {}).get("nombre_completo")
                if perfil.get("credenciales") else None
            )
            if not student_name:
                student_name = f"{perfil.get('apellidos', '')} {perfil.get('nombres', '')}".strip() or "—"
            depto = getattr(brain, "handoff_depto", None) or "Servicios de Secretaría"
            
            print("⚡ [SHORT-CIRCUIT - Ready] Operativa — pedir detalles para enviar al agente")
            saludo = f"{student_name.split()[0]}, " if student_name and student_name != '—' else ""
            ask_msg = (
                f"{saludo}No tengo respuesta para ello. 😔\n\n"
                f"¿Qué tal si te reviso con mis compañeros humanos del departamento **{depto}**? 💁\n\n"
                f"Para enviar tu solicitud, necesito que:\n"
                f"1. Describes nuevamente tu solicitud con todos los detalles\n"
                f"2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
            )
            return {
                "ok": True,
                "mode": "operativa",
                "handoff": True,
                "department": depto,
                "ticket_title": getattr(brain, "ticket_title", None) or getattr(brain, "intent_short", ""),
                "taxonomy": getattr(brain, "taxonomy", {}) or {},
                "summary": ask_msg,
                "handoff_sent": False,
                "handoff_channel": depto,
                "needs_handoff_details": True,
                "needs_handoff_file": True,
                "handoff_file_max_size_mb": 4,
                "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],
                "handoff_auto": False,
                "as_chat_message": True,
                "allow_new_query": False,
                "reset_context": False,
                "llm_decision": {
                    "resolution_mode": getattr(brain, "resolution_mode", "informativa"),
                    "operationality_score": getattr(brain, "operationality_score", 0.0),
                    "reasons": getattr(brain, "decision_reasons", [])
                }
            }
        
        # ===== USAR QUERY ENRIQUECIDA DEL CEREBRO =====
        # Si el cerebro detectó contexto, usar enriched_query
        if brain.needs_context and enriched_text and enriched_text.strip() != user_text.strip():
            intent_query_ready = enriched_text.strip()
            print(f"✅ [Context - Ready] Usando query enriquecida: {intent_query_ready}")
        else:
            # Usar query_rag del cerebro o texto original
            if getattr(brain, "query_rag", None) and brain.query_rag.strip():
                intent_query_ready = brain.query_rag.strip()
            else:
                intent_query_ready = user_text.strip()
            print(f"✅ [Ready] Usando query: {intent_query_ready}")
        
        # Adoptar taxonomía del cerebro
        brain_cat = brain.taxonomy.get("category") if brain.taxonomy else None
        brain_sub = brain.taxonomy.get("subcategory") if brain.taxonomy else None
        if brain_cat:
            category = brain_cat
        if brain_sub:
            subcategory = brain_sub
        
        # 3. stage == ready → V2: Router determinista primero (P0)
        # Intentar routing determinista (sin LLM) - pero usar query enriquecida
        category_det, subcategory_det, confidence_det = route_by_taxonomy(intent_query_ready)  # Usar query enriquecida
        
        # Si confianza >= 0.90, saltar confirmación y ir directo a retrieval (P0)
        if confidence_det >= TAU_SKIP_CONFIRM:
            print(f"🚀 [V2 Router] Alta confianza ({confidence_det:.2f}), saltando confirmación")
            # Usar query enriquecida del cerebro (tiene contexto si aplica)
            intent_query = intent_query_ready
            
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
            
            # Ir directo a retrieval (sin confirmación) - usar query enriquecida
            try:
                hierarchical_cands = hierarchical_candidates(intent_query, entities=None, queries=None)  # Usar query enriquecida
                if folders_hint:
                    hierarchical_cands["folders"] = folders_hint
                
                retr = get_retriever(
                    files_hint=hierarchical_cands.get("files"),
                    folders_hint=hierarchical_cands.get("folders")
                )
                
                # Canonizar query (ya viene enriquecida del cerebro)
                canon_q = _canonicalize_query(intent_query)  # intent_query ya tiene contexto si aplica
                
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
                
                # Si alta confianza, buscar solicitudes relacionadas ANTES de responder
                if ascore["confidence"] >= TAU_NORMA:
                    # Buscar solicitudes relacionadas
                    intent_slots = {"intent_short": canon_q, "accion": "", "objeto": "", "asignatura": "", "detalle_libre": intent_query}
                    
                    print(f"🔍 [Related Requests - High Conf] Buscando solicitudes relacionadas...")
                    print(f"   User request: {intent_query[:100]}")  # Usar query enriquecida
                    print(f"   Student data disponible: {student_data is not None}")
                    if student_data:
                        from .related_request_matcher import load_student_requests
                        solicitudes = load_student_requests(student_data)
                        print(f"   Solicitudes encontradas: {len(solicitudes)}")
                    
                    related_requests_result = find_related_requests(
                        user_request=intent_query,  # Usar query enriquecida con contexto
                        intent_slots=intent_slots,
                        student_data=student_data,
                        max_results=3
                    )
                    
                    print(f"🔍 [Related Requests - High Conf] Resultado: {len(related_requests_result.get('related_requests', []))} solicitudes relacionadas")
                    print(f"   No related: {related_requests_result.get('no_related', False)}")
                    
                    # Si hay solicitudes relacionadas, retornarlas para que el usuario seleccione
                    if related_requests_result.get("related_requests") and not related_requests_result.get("no_related"):
                        related_requests = related_requests_result.get("related_requests", [])
                        reasoning = related_requests_result.get("reasoning", "")
                        
                        primer_nombre = _obtener_primer_nombre(student_data)
                        mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                        
                        mensaje = f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:\n\n"
                        
                        for i, req in enumerate(related_requests, 1):
                            mensaje += f"{i}. {req.get('display', req.get('id', 'Solicitud'))}\n"
                        
                        mensaje += "\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar."
                        
                        return {
                            "category": category_det or category or "Consultas varias",
                            "subcategory": subcategory_det or subcategory or "Consultas varias",
                            "confidence": 0.85,
                            "summary": mensaje,
                            "campos_requeridos": [],
                            "needs_confirmation": False,
                            "needs_related_request_selection": True,
                            "related_requests": related_requests,
                            "no_related_request_option": True,
                            "confirmed": True,
                            "intent_slots": intent_slots,
                            "reasoning": reasoning
                        }
                    
                    # Si no hay solicitudes relacionadas, responder directamente
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
                # Si confianza media, buscar solicitudes relacionadas ANTES de responder
                elif ascore["confidence"] >= TAU_MIN:
                    # Buscar solicitudes relacionadas
                    intent_slots = {"intent_short": canon_q, "accion": "", "objeto": "", "asignatura": "", "detalle_libre": intent_query_ready}
                    
                    print(f"🔍 [Related Requests - Medium Conf] Buscando solicitudes relacionadas...")
                    print(f"   User request: {intent_query_ready[:100]}")  # Usar query enriquecida
                    print(f"   Student data disponible: {student_data is not None}")
                    if student_data:
                        from .related_request_matcher import load_student_requests
                        solicitudes = load_student_requests(student_data)
                        print(f"   Solicitudes encontradas: {len(solicitudes)}")
                    
                    related_requests_result = find_related_requests(
                        user_request=intent_query_ready,  # Usar query enriquecida con contexto
                        intent_slots=intent_slots,
                        student_data=student_data,
                        max_results=3
                    )
                    
                    print(f"🔍 [Related Requests - Medium Conf] Resultado: {len(related_requests_result.get('related_requests', []))} solicitudes relacionadas")
                    print(f"   No related: {related_requests_result.get('no_related', False)}")
                    
                    # Si hay solicitudes relacionadas, retornarlas para que el usuario seleccione
                    if related_requests_result.get("related_requests") and not related_requests_result.get("no_related"):
                        related_requests = related_requests_result.get("related_requests", [])
                        reasoning = related_requests_result.get("reasoning", "")
                        
                        primer_nombre = _obtener_primer_nombre(student_data)
                        mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                        
                        mensaje = f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:\n\n"
                        
                        for i, req in enumerate(related_requests, 1):
                            mensaje += f"{i}. {req.get('display', req.get('id', 'Solicitud'))}\n"
                        
                        mensaje += "\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar."
                        
                        return {
                            "category": category_det or category or "Consultas varias",
                            "subcategory": subcategory_det or subcategory or "Consultas varias",
                            "confidence": 0.85,
                            "summary": mensaje,
                            "campos_requeridos": [],
                            "needs_confirmation": False,
                            "needs_related_request_selection": True,
                            "related_requests": related_requests,
                            "no_related_request_option": True,
                            "confirmed": True,
                            "intent_slots": intent_slots,
                            "reasoning": reasoning
                        }
                    
                    # Si no hay solicitudes relacionadas, responder directamente
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
        # IMPORTANTE: Usar query enriquecida del cerebro (tiene contexto si aplica)
        slots = interpretar_intencion_principal(intent_query_ready)  # Usar query enriquecida
        
        # Si el router determinista encontró algo, usar esa categoría
        if category_det and confidence_det >= 0.75:
            # Si el cerebro tiene confirm_text con contexto, usarlo
            if brain.needs_confirmation and brain.confirm_text:
                confirm_text_to_use = brain.confirm_text
                print(f"✅ [Confirmation - Low Conf] Usando confirm_text del cerebro (con contexto): {confirm_text_to_use}")
            else:
                # Fallback a confirmación desde slots (sin contexto)
                confirm_text_to_use = _confirm_text_from_slots(slots)
                print(f"⚠️ [Confirmation - Low Conf] Usando confirmación desde slots (sin contexto): {confirm_text_to_use}")
            
            return {
                "category": category_det or brain_cat or category,
                "subcategory": subcategory_det or brain_sub or subcategory,
                "confidence": confidence_det,
                "summary": confirm_text_to_use,  # Usar confirm_text del cerebro si tiene contexto
                "campos_requeridos": [],
                "needs_confirmation": True,
                "confirmed": None,
                "intent_slots": slots,
                "diagnostics": {"router_confidence": confidence_det, "method": "deterministic_router_with_confirm"}
            }
        
        # Flujo normal (sin match determinista claro) - usar confirm_text del cerebro si tiene contexto
        if brain.needs_confirmation and brain.confirm_text:
            confirm_text_to_use = brain.confirm_text
            print(f"✅ [Confirmation - No Match] Usando confirm_text del cerebro (con contexto): {confirm_text_to_use}")
        else:
            confirm_text_to_use = _confirm_text_from_slots(slots)
            print(f"⚠️ [Confirmation - No Match] Usando confirmación desde slots (sin contexto): {confirm_text_to_use}")
        
        return {
            "category": brain_cat or category,
            "subcategory": brain_sub or subcategory,
            "confidence": 0.85,
            "summary": confirm_text_to_use,  # Usar confirm_text del cerebro si tiene contexto
            "campos_requeridos": [],
            "needs_confirmation": True,
            "confirmed": None,
            "intent_slots": slots
        }

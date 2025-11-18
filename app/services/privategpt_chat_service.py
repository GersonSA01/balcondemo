# app/services/privategpt_chat_service.py
"""
Servicio de chat usando PrivateGPT API - Orquestador principal.
Flujo: Saludo → Cerebro Híbrido (FAQ/Clasificación) → Confirmar → PrivateGPT API

Este archivo actúa como orquestador de alto nivel.
ACTUALIZADO: Ahora utiliza brain_service para clasificación híbrida.
"""
from typing import Dict, List, Any, Optional
import re
import os
import tempfile
from .privategpt_client import get_privategpt_client
from .handoff import _classify_answer_type_fallback, classify_with_heuristics
from .intent_parser import (
    es_greeting,
    interpretar_intencion_principal,
    _confirm_text_from_slots,
    es_confirmacion_positiva,
    es_confirmacion_negativa,
    obtener_primer_nombre
)
from .related_request_matcher import find_related_requests, load_student_requests
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus
from .chat_domain import ChatContext
from .solicitud_service import crear_solicitud, obtener_solicitudes_usuario
from .handoff import get_departamento_real
from datetime import datetime, date
from .response_builder import (
    build_frontend_response,
    build_informative_answer_response,
    build_need_confirm_response,
    build_error_response
)
from .student_data_service import maybe_answer_with_student_data, get_student_name
from .privategpt_service import call_privategpt_api
from .requirements_service import (
    get_requirements_from_history,
    propagate_requirements_to_response,
    finish_requirement_and_maybe_next
)
from .handoff_service import (
    determinar_departamento_handoff,
    build_handoff_response,
    process_handoff_details
)
from .cronograma_service import evaluar_cronograma_retiro
from .intent_classifier_trained import classify_user_intent_hybrid


def _ensure_slot_has_classification(slot: dict | None, user_text: str):
    """
    Inyecta la inteligencia del modelo híbrido en los slots.
    Si hay un FAQ Match, lo guarda en los slots para uso inmediato.
    """
    if not slot or not user_text:
        return

    try:
        brain_result = classify_user_intent_hybrid(user_text)
    except Exception as e:
        print(f"⚠️ [Brain] Error obteniendo clasificación híbrida: {e}")
        return

    if not brain_result:
        return

    slot["classification_from_logs"] = {
        "category": brain_result.get("category"),
        "subcategory": brain_result.get("subcategory"),
        "department": brain_result.get("department"),
        "confidence": brain_result.get("confidence"),
        "is_confident": brain_result.get("is_confident"),
    }
    # Usar confianzas separadas si están disponibles, sino usar la confianza principal
    main_confidence = brain_result.get("confidence") or 0.0
    slot["classification_from_logs_conf"] = {
        "cat": brain_result.get("cat_conf", main_confidence),
        "sub": brain_result.get("sub_conf", main_confidence),
        "dep": brain_result.get("dep_conf", main_confidence),
    }
    slot["department_from_logs"] = brain_result.get("department")
    slot["subcategory_from_logs"] = brain_result.get("subcategory")

    print(f"\n{'='*80}")
    print(f"🔍 [PrivateGPTChat] PROCESANDO RESULTADOS DE BRAIN")
    print(f"{'='*80}")
    print(f"   brain_result.category: '{brain_result.get('category')}'")
    print(f"   brain_result.subcategory: '{brain_result.get('subcategory')}'")
    print(f"   brain_result.department: '{brain_result.get('department')}'")
    print(f"   brain_result.is_confident: {brain_result.get('is_confident')}")
    print(f"   brain_result.confidence: {brain_result.get('confidence')}")
    print(f"   slot actual category: '{slot.get('category')}'")
    print(f"   slot actual subcategory: '{slot.get('subcategory')}'")

    # Obtener valores predichos (incluso si no superan threshold)
    predicted_category = brain_result.get("category")
    predicted_subcategory = brain_result.get("subcategory")
    predicted_department = brain_result.get("department")
    
    # Usar valores predichos si NO son "OTROS", incluso si is_confident es False
    # Esto permite usar las clasificaciones aunque no superen el threshold estricto
    use_predicted_values = (
        (predicted_category and predicted_category != "OTROS") or
        (predicted_subcategory and predicted_subcategory != "OTROS") or
        (predicted_department and predicted_department != "OTROS")
    )
    
    if brain_result.get("is_confident"):
        print(f"   ✅ Brain result es confident (conf={brain_result.get('confidence', 0.0):.3f} >= threshold), actualizando slots...")
        if not slot.get("category") or slot.get("category") == "OTROS":
            slot["category"] = predicted_category
            print(f"      → slot['category'] actualizado a: '{slot.get('category')}'")
        else:
            print(f"      → slot['category'] ya tiene valor: '{slot.get('category')}', NO se actualiza")
        if not slot.get("subcategory") or slot.get("subcategory") == "OTROS":
            slot["subcategory"] = predicted_subcategory
            print(f"      → slot['subcategory'] actualizado a: '{slot.get('subcategory')}'")
        else:
            print(f"      → slot['subcategory'] ya tiene valor: '{slot.get('subcategory')}', NO se actualiza")
    elif use_predicted_values:
        print(f"   ⚠️ Brain result NO es confident (conf={brain_result.get('confidence', 0.0):.3f} < threshold)")
        print(f"   ✅ PERO hay valores predichos válidos (no 'OTROS'), usando valores predichos de todas formas...")
        if not slot.get("category") or slot.get("category") == "OTROS":
            if predicted_category and predicted_category != "OTROS":
                slot["category"] = predicted_category
                print(f"      → slot['category'] actualizado a: '{slot.get('category')}' (predicho aunque confianza baja)")
            else:
                print(f"      → predicted_category es 'OTROS' o None, manteniendo valor actual")
        else:
            print(f"      → slot['category'] ya tiene valor: '{slot.get('category')}', NO se actualiza")
        if not slot.get("subcategory") or slot.get("subcategory") == "OTROS":
            if predicted_subcategory and predicted_subcategory != "OTROS":
                slot["subcategory"] = predicted_subcategory
                print(f"      → slot['subcategory'] actualizado a: '{slot.get('subcategory')}' (predicho aunque confianza baja)")
            else:
                print(f"      → predicted_subcategory es 'OTROS' o None, manteniendo valor actual")
        else:
            print(f"      → slot['subcategory'] ya tiene valor: '{slot.get('subcategory')}', NO se actualiza")
    else:
        print(f"   ⚠️ Brain result NO es confident (conf={brain_result.get('confidence', 0.0):.3f} < threshold)")
        print(f"   ⚠️ Y no hay valores predichos válidos (todos son 'OTROS'), NO se actualizan slots")
        print(f"      → slot['category'] mantiene: '{slot.get('category', 'None')}'")
        print(f"      → slot['subcategory'] mantiene: '{slot.get('subcategory', 'None')}'")
    
    print(f"\n✅ [PrivateGPTChat] VALORES FINALES EN SLOT:")
    print(f"   slot['category']: '{slot.get('category', 'None')}'")
    print(f"   slot['subcategory']: '{slot.get('subcategory', 'None')}'")
    print(f"   slot['department_from_logs']: '{slot.get('department_from_logs', 'None')}'")
    print(f"   slot['subcategory_from_logs']: '{slot.get('subcategory_from_logs', 'None')}'")
    print(f"{'='*80}\n")

    faq_match = brain_result.get("faq_match")
    if faq_match:
        similarity = faq_match.get("similarity")
        print(f"💡 [Brain] FAQ Match encontrado (Similitud: {similarity})")
        slot["faq_answer_payload"] = faq_match


def try_quick_faq_response(intent_slots: Dict, student_data: Optional[Dict]) -> Optional[Dict[str, Any]]:
    """
    Intenta responder inmediatamente si el cerebro encontró un FAQ Match de alta confianza.
    Esto evita llamadas a PrivateGPT y esperas innecesarias.
    """
    faq_match = intent_slots.get("faq_answer_payload") if intent_slots else None
    if not faq_match:
        return None

    answer_text = faq_match.get("answer")
    similarity = faq_match.get("similarity", 0)

    if not answer_text or similarity <= 0.82:
        return None

    primer_nombre = obtener_primer_nombre(student_data)
    saludo = f"{primer_nombre}, " if primer_nombre else ""
    final_msg = f"{saludo}tengo información precisa sobre esto:\n\n{answer_text}"

    return build_frontend_response(
        stage=ConversationStage.ANSWER_READY,
        mode=ConversationMode.INFORMATIVE,
        status=ConversationStatus.ANSWER,
        message=final_msg,
        response=final_msg,
        has_information=True,
        intent_slots=intent_slots,
        extra={
            "source": "knowledge_base_memory",
            "confidence": similarity
        }
    )


# ============================================================================
# FUNCIONES AUXILIARES (helpers que aún se necesitan en este archivo)
# ============================================================================

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


def _resolve_answer_type(intent_slots: Dict, original_user_request: str) -> str:
    """
    Resuelve el answer_type desde intent_slots o usando fallback.
    
    Returns:
        "informativo" o "operativo"
    """
    answer_type = intent_slots.get("answer_type")
    if not answer_type or answer_type not in ("informativo", "operativo"):
        intent_short = intent_slots.get("intent_short", "")
        answer_type = _classify_answer_type_fallback(intent_short, intent_slots, original_user_request)
        if answer_type not in ("informativo", "operativo"):
            answer_type = "informativo"  # Fallback por defecto
    
    return answer_type


def _extraer_periodo_actual(student_data: Optional[Dict]) -> Optional[str]:
    """
    Intenta obtener el periodo académico actual del student_data.
    AJUSTA esta función a la estructura real de tu JSON.
    """
    if not student_data or not isinstance(student_data, dict):
        return None

    # 1) Intento por contexto genérico
    contexto = student_data.get("contexto") or {}
    if isinstance(contexto, dict):
        info_acad = contexto.get("informacion_academica") or {}
        if isinstance(info_acad, dict):
            periodo = info_acad.get("periodo_actual") or info_acad.get("periodo") or ""
            if isinstance(periodo, str) and periodo.strip():
                return periodo.strip()

    # 2) Intento por perfiles → inscripción → periodo
    perfiles = student_data.get("perfiles") or []
    if isinstance(perfiles, list) and perfiles:
        perfil = next((p for p in perfiles if p.get("inscripcionprincipal")), perfiles[0])
        inscripcion = perfil.get("inscripcion") or {}
        if isinstance(inscripcion, dict):
            periodo = (
                inscripcion.get("periodo") or
                inscripcion.get("periodo_academico") or
                (inscripcion.get("periodoacademico") or {}).get("nombre_corto")
            )
            if isinstance(periodo, str) and periodo.strip():
                return periodo.strip()

    return None


def _handle_retiro_asignatura_operativo(
    original_user_request: str,
    intent_slots: Dict,
    student_data: Optional[Dict],
    requirements: List[Dict],
    current_req_index: int
) -> Dict[str, Any]:
    """
    Lógica específica de negocio para 'retirar asignatura' usando cronograma JSON.
    NO llama a PrivateGPT para decidir fechas.
    """
    # 1) Obtener periodo actual del estudiante
    periodo_actual = _extraer_periodo_actual(student_data)
    hoy = date.today()
    
    print(f"📅 [Cronograma] Periodo del estudiante: {periodo_actual or 'No encontrado'}")
    print(f"📅 [Cronograma] Fecha actual: {hoy}")

    estado, info = evaluar_cronograma_retiro(
        fecha_hoy=hoy,
        periodo_actual=periodo_actual
    )
    
    print(f"📅 [Cronograma] Estado: {estado}")
    print(f"📅 [Cronograma] Info: {info}")

    # Helper para saludo
    primer_nombre = obtener_primer_nombre(student_data)
    saludo_inicio = f"{primer_nombre}, " if primer_nombre else ""

    # 2) Construir mensajes según estado
    if estado == "VENTANA_RETIRO_DEFINITIVO_ACTIVA":
        msg = (
            f"{saludo_inicio}actualmente está activo el periodo de **RETIRO DEFINITIVO** "
            f"del {info['inicio']} al {info['fin']} "
            f"para el periodo académico **{info.get('periodo_academico', '')}**.\n\n"
            "Puedo ayudarte a gestionar el retiro. Por favor:\n"
            "1. Indica la **asignatura** y el **paralelo** que deseas retirar.\n"
            "2. Confirma el **motivo** del retiro.\n\n"
            "Luego te ayudo a enviar la solicitud al departamento correspondiente. ✅"
        )

        return build_frontend_response(
            stage=ConversationStage.AWAIT_HANDOFF_DETAILS,
            mode=ConversationMode.OPERATIVE,
            status=ConversationStatus.NEED_DETAILS,
            message=msg,
            response=msg,
            has_information=True,
            intent_slots=intent_slots,
            extra={
                "cronograma_estado": estado,
                "cronograma_info": info,
                "needs_handoff_details": True,
                "needs_handoff_file": False,
                "campos_requeridos": ["asignatura", "paralelo", "motivo"],
                "requirements": requirements,
                "current_requirement_index": current_req_index,
            }
        )

    if estado == "VENTANA_RETIRO_FUERZA_MAYOR_ACTIVA":
        msg = (
            f"{saludo_inicio}en este momento solo está habilitado el **RETIRO POR CASOS FORTUITOS O DE FUERZA MAYOR** "
            f"del {info['inicio']} al {info['fin']} "
            f"para el periodo académico **{info.get('periodo_academico', '')}**.\n\n"
            "En este tipo de retiro debes adjuntar sustento del caso (documentos que justifiquen la situación).\n\n"
            "Para ayudarte con la solicitud, por favor:\n"
            "1. Indica la **asignatura** y el **paralelo**.\n"
            "2. Describe tu **caso** (qué ocurrió).\n"
            "3. Prepara un **archivo PDF o imagen** (máx. 4MB) con los documentos de respaldo para adjuntar. 📎"
        )

        return build_frontend_response(
            stage=ConversationStage.AWAIT_HANDOFF_DETAILS,
            mode=ConversationMode.OPERATIVE,
            status=ConversationStatus.NEED_DETAILS,
            message=msg,
            response=msg,
            has_information=True,
            intent_slots=intent_slots,
            extra={
                "cronograma_estado": estado,
                "cronograma_info": info,
                "needs_handoff_details": True,
                "needs_handoff_file": True,
                "handoff_file_max_size_mb": 4,
                "handoff_file_types": ["pdf", "jpg", "jpeg", "png"],
                "campos_requeridos": ["asignatura", "paralelo", "descripcion_caso", "archivo"],
                "requirements": requirements,
                "current_requirement_index": current_req_index,
            }
        )

    # Fuera de cronograma
    msg = f"{saludo_inicio}lo siento, actualmente **no está activo** el periodo de retiro de asignaturas.\n\n"
    msg += "Según el cronograma vigente"
    if info.get("periodo_academico"):
        msg += f" para el periodo **{info['periodo_academico']}**"
    msg += ":\n\n"

    tiene_fechas = False
    if info.get("retiro_def_inicio") and info.get("retiro_def_fin"):
        msg += f"• **Retiro definitivo**: del {info['retiro_def_inicio']} al {info['retiro_def_fin']}\n"
        tiene_fechas = True
    if info.get("fuerza_mayor_inicio") and info.get("fuerza_mayor_fin"):
        msg += (
            f"• **Retiro por casos fortuitos o fuerza mayor**: "
            f"del {info['fuerza_mayor_inicio']} al {info['fuerza_mayor_fin']}\n"
        )
        tiene_fechas = True
    
    if not tiene_fechas:
        msg += "⚠️ No se encontró información de cronograma disponible.\n"

    msg += (
        "\nLo siento mucho 😔 ¿Hay algo más en lo que pueda ayudarte?."
    )

    return build_frontend_response(
        stage=ConversationStage.ANSWER_READY,
        mode=ConversationMode.OPERATIVE,
        status=ConversationStatus.ANSWER,
        message=msg,
        response=msg,
        has_information=True,
        intent_slots=intent_slots,
        extra={
            "cronograma_estado": estado,
            "cronograma_info": info,
            "requirements": requirements,
            "current_requirement_index": current_req_index,
        }
    )


# ============================================================================
# FUNCIONES DE MANEJO POR ETAPA (handlers pequeños y enfocados)
# ============================================================================

def _handle_greeting(student_data: Optional[Dict]) -> Dict[str, Any]:
    """Maneja el saludo inicial."""
    nombre = obtener_primer_nombre(student_data)
    saludo = f"Hola{' ' + nombre if nombre else ''}! 👋 Soy tu asistente virtual del Balcón de Servicios UNEMI. Estoy aquí para ayudarte con tus consultas y solicitudes. ¿En qué puedo asistirte hoy?"
    
    return build_frontend_response(
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


def _process_uploaded_file(uploaded_file: Any) -> None:
    """Procesa un archivo subido, ingestionándolo en PrivateGPT."""
    try:
        client = get_privategpt_client()
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


def _handle_confirmation_informative(
    original_user_request: str,
    intent_slots: Dict,
    conversation_history: List[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    student_data: Optional[Dict],
    perfil_id: Optional[str],
    requirements: List[Dict],
    current_req_index: int
) -> Dict[str, Any]:
    """
    Maneja confirmación para intenciones informativas.
    Busca solicitudes relacionadas y luego llama a PrivateGPT.
    """
    # Intentar responder con student_data primero
    if student_data:
        data_answer = maybe_answer_with_student_data(intent_slots, student_data)
        if data_answer is not None:
            return data_answer

    # Intentar responder con FAQ híbrida de alta confianza
    faq_response = try_quick_faq_response(intent_slots, student_data)
    if faq_response:
        print("⚡ [ChatService] Respondiendo vía FAQ Memory (sin llamar a PrivateGPT)")
        return finish_requirement_and_maybe_next(faq_response, requirements, current_req_index)
    
    # Buscar solicitudes relacionadas
    related_requests_result = find_related_requests(
        user_request=original_user_request,
        intent_slots=intent_slots,
        student_data=student_data,
        max_results=3
    )
    
    related_requests = related_requests_result.get("related_requests", [])
    no_related = related_requests_result.get("no_related", False)
    
    # Si hay múltiples requerimientos Y hay solicitudes relacionadas, mostrar selección de requerimiento
    if related_requests and not no_related and requirements and len(requirements) > 1:
        primer_nombre = obtener_primer_nombre(student_data)
        mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
        
        user_message = f"{mensaje_inicio}He identificado estos {len(requirements)} temas en tu mensaje:\n\n"
        for i, req in enumerate(requirements, 1):
            req_summary = req.get("summary", f"Requerimiento {i}")
            user_message += f"{req_summary}\n"
        
        user_message += f"\n¿Con cuál quieres que empecemos?"
        
        requirement_options = []
        for i, req in enumerate(requirements, 1):
            req_summary = req.get("summary", f"Requerimiento {i}")
            button_label = req_summary[:50] + "..." if len(req_summary) > 50 else req_summary
            requirement_options.append({
                "id": f"req_{i}",
                "label": f"{i}. {button_label}",
                "requirement_index": i - 1
            })
        
        requirement_options.append({
            "id": "reformulate",
            "label": "❌ Ninguno, quiero reformular",
            "requirement_index": -1
        })
        
        response = build_frontend_response(
            stage=ConversationStage.AWAIT_INTENT,
            mode=ConversationMode.INFORMATIVE,
            status=ConversationStatus.NEED_DETAILS,
            message=user_message,
            response=user_message,
            has_information=None,
            intent_slots=intent_slots,
            extra={
                "needs_confirmation": False,
                "needs_requirement_selection": True,
                "confirmed": False,
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.85,
                "requirements": requirements,
                "current_requirement_index": current_req_index,
                "requirement_options": requirement_options,
                "is_multi_req_confirmation": True,
                "pending_related_requests": True,
                "related_requests": related_requests,
            }
        )
        
        if "meta" not in response:
            response["meta"] = {}
        response["meta"]["requirements"] = requirements
        response["meta"]["current_requirement_index"] = current_req_index
        response["meta"]["is_multi_req_confirmation"] = True
        response["meta"]["needs_requirement_selection"] = True
        response["meta"]["requirement_options"] = requirement_options
        response["requirements"] = requirements
        response["current_requirement_index"] = current_req_index
        response["requirement_options"] = requirement_options
        
        return response
    
    # Si hay solicitudes relacionadas pero NO hay múltiples requerimientos, mostrar directamente
    if related_requests and not no_related:
        primer_nombre = obtener_primer_nombre(student_data)
        mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
        
        req_text = original_user_request
        if requirements and current_req_index < len(requirements):
            current_req = requirements[current_req_index]
            req_slots = current_req.get("slots", {})
            req_text = req_slots.get("original_user_message", original_user_request)
        
        user_message = f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con el requerimiento: {req_text}\n\n"
        for i, req in enumerate(related_requests, 1):
            user_message += f"{i}. {req.get('display', req.get('id', 'Solicitud'))}\n"
        user_message += "\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar."
        
        response = build_frontend_response(
            stage=ConversationStage.AWAIT_RELATED_REQUEST,
            mode=ConversationMode.INFORMATIVE,
            status=ConversationStatus.NEED_DETAILS,
            message=user_message,
            response=user_message,
            has_information=False,
            intent_slots=intent_slots,
            extra={
                "needs_confirmation": False,
                "needs_related_request_selection": True,
                "related_requests": related_requests,
                "no_related_request_option": True,
                "confirmed": True,
                "category": category,
                "subcategory": subcategory,
                "confidence": 0.85,
                "requirements": requirements,
                "current_requirement_index": current_req_index,
            }
        )
        return response
        
    # Si no hay solicitudes relacionadas, llamar directamente a PrivateGPT
    try:
        privategpt_result = call_privategpt_api(
            user_text=original_user_request,
            conversation_history=conversation_history,
            category=None,
            subcategory=None,
            student_data=student_data,
            perfil_id=perfil_id
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
        response = build_informative_answer_response(
            resumen=response_text,
            fuentes=fuentes,
            intent_slots=intent_slots,
            category=category,
            subcategory=subcategory
        )
        
        # Incluir requirements
        if requirements:
            if "extra" not in response:
                response["extra"] = {}
            response["extra"]["requirements"] = requirements
            response["extra"]["current_requirement_index"] = current_req_index
        
        return finish_requirement_and_maybe_next(response, requirements, current_req_index)
    else:
        # No hay información, hacer handoff
        depto = determinar_departamento_handoff(
            user_text=original_user_request,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            student_data=student_data
        )
        
        student_name = get_student_name(student_data)
        saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
        ask_msg = (
            f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
            f"Para enviar tu solicitud, por favor:\n"
            f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
            f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
            f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
        )
            
        response = build_handoff_response(
            depto=depto,
            student_data=student_data,
            category=category,
            subcategory=subcategory,
                intent_slots=intent_slots,
            needs_handoff_details=True
        )
        
        # Asegurar propagación de requirements
        if requirements:
            response = propagate_requirements_to_response(response, requirements, current_req_index)
        
        return response


def _handle_confirmation_operative(
    original_user_request: str,
    intent_slots: Dict,
    conversation_history: List[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    student_data: Optional[Dict],
    requirements: List[Dict],
    current_req_index: int
) -> Dict[str, Any]:
    """
    Maneja confirmación para intenciones operativas.
    Busca solicitudes relacionadas y luego hace handoff.
    """
    # ✅ Atajo: retiro de asignatura → usar lógica de cronograma JSON
    accion = (intent_slots.get("accion") or "").lower()
    objeto = (intent_slots.get("objeto") or "").lower()
    intent_code = (intent_slots.get("intent_code") or "").lower()
    intent_short = (intent_slots.get("intent_short") or "").lower()

    es_retiro_asignatura = (
        intent_code == "retiro_asignatura"
        or "retiro de asignatura" in intent_short
        or (accion == "retirar" and objeto in ("asignatura", "asignaturas", "materia", "materias"))
    )

    if es_retiro_asignatura:
        print("🎯 [Operative] Detectado retiro de asignatura → usando lógica de cronograma JSON")
        return _handle_retiro_asignatura_operativo(
            original_user_request=original_user_request,
            intent_slots=intent_slots,
            student_data=student_data,
            requirements=requirements,
            current_req_index=current_req_index
        )
    
    # Usar classify_with_heuristics (sin LLM)
    if not category or not subcategory:
        try:
            heuristic_classification = classify_with_heuristics(intent_slots)
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
                user_message = (
                    f"{mensaje_inicio}He encontrado {len(related_requests)} solicitud(es) relacionada(s) con tu requerimiento:"
                )
                
                response = build_frontend_response(
                    stage=ConversationStage.AWAIT_RELATED_REQUEST,
                    mode=ConversationMode.OPERATIVE,
                    status=ConversationStatus.NEED_DETAILS,
                    message=user_message,
                    response=user_message,
                    has_information=False,
                    intent_slots=intent_slots,
                    extra={
                        "needs_confirmation": False,
                        "needs_related_request_selection": True,
                        "related_requests": related_requests,
                        "no_related_request_option": True,
                        "confirmed": True,
                        "category": category,
                        "subcategory": subcategory,
                        "confidence": 0.9,
                        "requirements": requirements,
                        "current_requirement_index": current_req_index,
                    }
                )
                return response
        except Exception as e:
            print(f"⚠️ [Handoff] Error al buscar solicitudes relacionadas: {e}")
            import traceback
            traceback.print_exc()
    
    depto = determinar_departamento_handoff(
        user_text=original_user_request,
                category=category,
                subcategory=subcategory,
        intent_slots=intent_slots,
                student_data=student_data
            )
            
    response = build_handoff_response(
        depto=depto,
        student_data=student_data,
        category=category,
        subcategory=subcategory,
        intent_slots=intent_slots
    )
    
    # Asegurar propagación de requirements
    if requirements:
        response = propagate_requirements_to_response(response, requirements, current_req_index)
    
    return response


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
    
    # Recuperar requirements desde el historial si no se pasaron
    if requirements is None:
        requirements, current_req_index = get_requirements_from_history(conversation_history)
    
    if not intent_slots:
        return build_error_response(
            "⚠️ No puedo procesar tu solicitud en este momento. Por favor, intenta nuevamente o ingresa tu solicitud manualmente a través del formulario del Balcón de Servicios."
        )
    
    # Si hay múltiples requerimientos, usar el original_user_message del requerimiento actual
    # PERO solo si el requerimiento no está 'done'
    original_user_request = None
    if requirements and current_req_index < len(requirements):
        current_req = requirements[current_req_index]
        # Verificar que el requerimiento actual no esté 'done'
        if current_req.get("status") != "done":
            req_slots = current_req.get("slots", {})
            req_original = req_slots.get("original_user_message", "")
            if req_original and req_original.strip():
                original_user_request = req_original
                intent_slots["original_user_message"] = req_original
                print(f"✅ [Confirmation] Usando original_user_message del requerimiento actual: '{original_user_request[:100]}'")
        else:
            print(f"⚠️ [Confirmation] Requerimiento actual está 'done', no se usará su original_user_message")
    
    # Si no se encontró en el requerimiento actual, usar la función helper
    # PERO solo si hay requirements pendientes, si no hay requirements usar el user_text actual
    if not original_user_request:
        # Verificar si hay requirements pendientes
        has_pending_requirements = requirements and any(req.get("status") != "done" for req in requirements)
        
        if not has_pending_requirements:
            # No hay requirements pendientes, usar el user_text actual directamente
            original_user_request = user_text
            print(f"✅ [Confirmation] No hay requirements pendientes, usando user_text actual: '{original_user_request[:100]}'")
        else:
            # Hay requirements pendientes, buscar en historial normalmente
            print(f"🔍 [Confirmation] No se encontró original_user_request en el requerimiento actual, buscando en el historial...")
            original_user_request = _recover_original_user_request(intent_slots, conversation_history, user_text)
            print(f"✅ [Confirmation] original_user_request recuperado desde historial: '{original_user_request[:100]}'")
        # Si aún así se recupera el mensaje completo y hay múltiples requerimientos, usar el intent_short
        if requirements and len(requirements) > 1:
            if original_user_request and len(original_user_request.split()) > 10:
                current_req = requirements[current_req_index] if current_req_index < len(requirements) else None
                if current_req:
                    intent_short = current_req.get("summary") or current_req.get("slots", {}).get("intent_short", "")
                    if intent_short:
                        original_user_request = intent_short
                        intent_slots["original_user_message"] = intent_short
                        print(f"✅ [Confirmation] Corrigiendo a intent_short del requerimiento actual: '{original_user_request[:100]}'")
    
    # Resolver answer_type
    answer_type = _resolve_answer_type(intent_slots, original_user_request)
    intent_slots["answer_type"] = answer_type
    if category:
        intent_slots["category"] = category
    if subcategory:
        intent_slots["subcategory"] = subcategory
    
    print(f"🔍 [Análisis] Intención confirmada: '{intent_slots.get('intent_short', '')[:80]}'")
    print(f"   Tipo de respuesta: {answer_type} (guardado en intent_slots)")
    
    # Delegar según tipo
    if answer_type == "operativo":
        return _handle_confirmation_operative(
            original_user_request, intent_slots, conversation_history,
            category, subcategory, student_data, requirements, current_req_index
        )
    else:
        return _handle_confirmation_informative(
            original_user_request, intent_slots, conversation_history,
            category, subcategory, student_data, perfil_id, requirements, current_req_index
        )


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
    print(f"   Control action: {control_action}")
    
    conversation_history = conversation_history or []
    
    # Recuperar requirements desde el historial al inicio para tenerlos disponibles en todo el flujo
    requirements, current_req_index = get_requirements_from_history(
        conversation_history,
        prefer_multi_req_confirmation=True
    )
    print(f"📋 [classify_with_privategpt] Requirements recuperados al inicio: {len(requirements)} requerimientos, índice: {current_req_index}")
    
    # 0.5. Verificar si el usuario está seleccionando un requerimiento (número 1, 2, etc.) desde un mensaje con is_multi_req_confirmation
    # Esto debe verificarse ANTES de cualquier otro procesamiento
    # Usar la función centralizada para recuperar requirements, pero buscar específicamente mensajes con is_multi_req_confirmation
    requirements_for_selection = []
    is_multi_req_selection = False
    
    # Buscar mensaje con is_multi_req_confirmation en el historial (buscar en múltiples lugares)
    for msg in reversed(conversation_history):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            meta = msg.get("meta") or {}
            extra_from_meta = meta.get("extra") or {}
            extra_from_msg = msg.get("extra") or {}
            
            # Buscar is_multi_req_confirmation en múltiples lugares
            has_multi_req = False
            reqs_candidate = []
            
            # 1. Buscar en meta.extra
            if isinstance(extra_from_meta, dict) and extra_from_meta.get("is_multi_req_confirmation"):
                has_multi_req = True
                reqs_candidate = extra_from_meta.get("requirements", [])
            # 2. Buscar en extra directo del mensaje
            elif isinstance(extra_from_msg, dict) and extra_from_msg.get("is_multi_req_confirmation"):
                has_multi_req = True
                reqs_candidate = extra_from_msg.get("requirements", [])
            # 3. Buscar en meta directamente (para compatibilidad)
            elif isinstance(meta, dict) and meta.get("is_multi_req_confirmation"):
                has_multi_req = True
                reqs_candidate = meta.get("requirements", [])
            # 4. Buscar requirements en meta directamente si hay needs_requirement_selection
            elif meta.get("needs_requirement_selection") and meta.get("requirements"):
                has_multi_req = True
                reqs_candidate = meta.get("requirements", [])
            
            if has_multi_req and reqs_candidate:
                requirements_for_selection = reqs_candidate
                is_multi_req_selection = True
                print(f"🔍 [Multi-Req Selection] Detectado mensaje con is_multi_req_confirmation, {len(requirements_for_selection)} requerimientos disponibles")
                break
    
    # Si encontramos un mensaje con is_multi_req_confirmation y el usuario envió un número, procesar la selección
    if is_multi_req_selection and requirements_for_selection:
        user_text_str = str(user_text).strip().lower()
        
        # Detectar si el usuario seleccionó un número (1, 2, etc.) o "reformulate"
        selected_index = None
        
        # Buscar número en el texto (1, 2, 3, etc.)
        import re
        number_match = re.search(r'\b([1-9])\b', user_text_str)
        if number_match:
            selected_num = int(number_match.group(1))
            if 1 <= selected_num <= len(requirements_for_selection):
                selected_index = selected_num - 1  # Convertir a índice base 0
                print(f"✅ [Multi-Req Selection] Usuario seleccionó requerimiento #{selected_num} (índice {selected_index})")
        
        # Detectar si el usuario quiere reformular
        reformulate_keywords = ["reformular", "ninguno", "ninguna", "reformulate", "ninguno quiero reformular"]
        wants_reformulate = any(keyword in user_text_str for keyword in reformulate_keywords)
        
        if wants_reformulate:
            # Usuario quiere reformular → pedir que vuelva a escribir
            return build_frontend_response(
                stage=ConversationStage.AWAIT_INTENT,
                mode=ConversationMode.INFORMATIVE,
                status=ConversationStatus.ANSWER,
                message="Perfecto. Por favor, cuéntame nuevamente tu requerimiento de manera más clara y específica.",
                has_information=False,
                extra={
                    "has_more_requirements": False,
                    "clear_requirements": True
                }
            )
        elif selected_index is not None and selected_index < len(requirements_for_selection):
            # Usuario seleccionó un requerimiento válido
            selected_req = requirements_for_selection[selected_index]
            selected_req_slots = selected_req.get("slots", {})
            
            # Obtener el mensaje original del requerimiento seleccionado
            original_user_message_selected = selected_req_slots.get("original_user_message", "")
            if not original_user_message_selected:
                original_user_message_selected = selected_req.get("summary", "")
            
            print(f"✅ [Multi-Req Selection] Procesando requerimiento seleccionado: '{original_user_message_selected[:100]}'")
            
            # Actualizar current_req_index y requirements
            current_req_index = selected_index
            requirements = requirements_for_selection
            
            # Actualizar user_text con el mensaje original del requerimiento seleccionado para continuar el flujo
            user_text = original_user_message_selected
            print(f"🔄 [Multi-Req Selection] Reemplazando user_text con mensaje original: '{user_text[:100]}'")
            
            # Continuar con el flujo normal usando el mensaje original del requerimiento
            # Esto permitirá que se busquen solicitudes relacionadas y se procese correctamente
    
    # 0. Manejar control_action (acciones sin LLM)
    # Si hay control_action, ignorar el user_text si es un carácter especial
    if control_action:
        if user_text in ("⎈", "\u2388"):  # Carácter especial usado por el frontend
            print(f"📋 [Control Action] Ignorando mensaje especial '{user_text}', usando solo control_action: {control_action}")
            user_text = ""  # Limpiar el texto para evitar procesarlo
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
            return build_frontend_response(
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
            return build_frontend_response(
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
            # IMPORTANTE: Si hay un menú de multi-requirement activo, el requerimiento actual es el que generó el menú
            # Necesitamos encontrar el requerimiento que está marcado como "done" más recientemente
            # y usar el siguiente requerimiento pendiente como el "actual"
            
            # Buscar el último mensaje con has_more_requirements para obtener el índice correcto
            last_menu_index = None
            for msg in reversed(conversation_history):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    meta = msg.get("meta") or {}
                    extra = meta.get("extra") or {}
                    if isinstance(extra, dict) and extra.get("has_more_requirements"):
                        # Este es el mensaje que mostró el menú
                        last_menu_index = extra.get("current_requirement_index")
                        print(f"🔍 [Multi-Req] continue_current: Encontrado menú con current_requirement_index={last_menu_index}")
                        break
            
            # Si encontramos un índice del menú, verificar si hay un requerimiento pendiente después de ese
            if last_menu_index is not None and requirements:
                # El requerimiento en last_menu_index ya está "done", buscar el siguiente pendiente
                remaining_indices = [i for i, r in enumerate(requirements) if r.get("status") == "pending"]
                if remaining_indices:
                    # Usar el primer requerimiento pendiente como el actual
                    current_req_index = remaining_indices[0]
                    print(f"✅ [Multi-Req] continue_current: Actualizando current_req_index a {current_req_index} (primer requerimiento pendiente)")
            
            # Verificar si estamos en stage de solicitudes relacionadas
            ctx = ChatContext.from_history(conversation_history)
            stage_temp = ctx.stage.value
            pending_slots_temp = ctx.pending_slots
            
            if stage_temp == ConversationStage.AWAIT_RELATED_REQUEST.value:
                # Si estamos en stage de solicitudes relacionadas, tratar como si el usuario rechazó
                # las solicitudes relacionadas y continuar sin relacionar
                print(f"🔄 [Multi-Req] continue_current detectado en stage AWAIT_RELATED_REQUEST - tratando como rechazo de solicitudes relacionadas")
                
            if requirements and current_req_index < len(requirements):
                current_req = requirements[current_req_index]
                intent_slots = current_req.get("slots", {})
                original_user_request = intent_slots.get("original_user_message", "")
                
                if not original_user_request:
                    original_user_request = current_req.get("summary", "")
                
                print(f"✅ [Multi-Req] continue_current: Procesando requerimiento índice {current_req_index}: '{current_req.get('summary', 'N/A')}'")
                
                # Recuperar answer_type
                answer_type = intent_slots.get("answer_type", "informativo")
                
                # Si es informativo, llamar directamente a PrivateGPT sin relacionar
                if answer_type == "informativo":
                    print(f"✅ [Multi-Req] Intención informativa - llamando a PrivateGPT sin relacionar solicitudes")
                    try:
                        privategpt_result = call_privategpt_api(
                            user_text=original_user_request,
                            conversation_history=conversation_history,
                            category=None,
                            subcategory=None,
                            student_data=student_data,
                            perfil_id=perfil_id
                        )
                        
                        has_information = privategpt_result.get("has_information", False)
                        response_text = privategpt_result.get("response", "")
                        fuentes = privategpt_result.get("fuentes", [])
                        
                        if has_information:
                            response = build_informative_answer_response(
                                resumen=response_text,
                                fuentes=fuentes,
                                intent_slots=intent_slots,
                                category=category,
                                subcategory=subcategory
                            )
                            
                            # Incluir requirements
                            if "extra" not in response:
                                response["extra"] = {}
                            response["extra"]["requirements"] = requirements
                            response["extra"]["current_requirement_index"] = current_req_index
                            
                            return finish_requirement_and_maybe_next(response, requirements, current_req_index)
                        else:
                            # No hay información, hacer handoff
                            depto = determinar_departamento_handoff(
                                user_text=original_user_request,
                                category=category,
                                subcategory=subcategory,
                                intent_slots=intent_slots,
                                student_data=student_data
                            )
                            
                            student_name = get_student_name(student_data)
                            saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
                            ask_msg = (
                                f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
                                f"Para enviar tu solicitud, por favor:\n"
                                f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
                                f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
                                f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
                            )
                            
                            response = build_handoff_response(
                                resumen=ask_msg,
                                depto_real=depto,
                                intent_slots=intent_slots,
                                needs_handoff_details=True,
                                category=category,
                                subcategory=subcategory,
                                student_data=student_data
                            )
                    except Exception as e:
                        print(f"❌ [PrivateGPT] Error: {type(e).__name__}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        raise
                else:
                    # Si es operativo, ir directamente al handoff
                    print(f"✅ [Multi-Req] Intención operativa - yendo directamente al handoff")
                    depto = determinar_departamento_handoff(
                        user_text=original_user_request,
                        category=category,
                        subcategory=subcategory,
                        intent_slots=intent_slots,
                        student_data=student_data
                    )
                    response = build_handoff_response(depto, student_data, category, subcategory, intent_slots)
                    return finish_requirement_and_maybe_next(response, requirements, current_req_index)
            
            # Si no estamos en stage de solicitudes relacionadas, continuar con el flujo normal
            # Pero primero asegurarnos de que estamos usando el requerimiento correcto
            if requirements and current_req_index < len(requirements):
                current_req = requirements[current_req_index]
                
                # Verificar que el requerimiento actual no esté "done"
                if current_req.get("status") == "done":
                    # Si está "done", buscar el siguiente pendiente
                    remaining_indices = [i for i, r in enumerate(requirements) if r.get("status") == "pending"]
                    if remaining_indices:
                        current_req_index = remaining_indices[0]
                        current_req = requirements[current_req_index]
                        print(f"✅ [Multi-Req] continue_current: Corrigiendo índice a {current_req_index} (requerimiento anterior estaba 'done')")
                
                intent_slots = current_req.get("slots", {})
                original_user_request = intent_slots.get("original_user_message", "")
                if not original_user_request:
                    original_user_request = current_req.get("summary", "")
                
                # Actualizar user_text con el mensaje original del requerimiento actual
                user_text = original_user_request
                print(f"🔄 [Multi-Req] Continuando con el requerimiento actual (índice {current_req_index}): '{current_req.get('summary', 'N/A')}'")
                print(f"   user_text actualizado a: '{user_text[:100]}'")
                # Continuar con el flujo normal pero usando los slots del requerimiento actual
                # El user_text ya está actualizado con el mensaje original
            else:
                # No hay requerimiento actual válido, continuar flujo normal
                print(f"⚠️ [Multi-Req] continue_current: No hay requerimiento válido en índice {current_req_index}")
                pass
        elif control_action == "new_requirement":
            # Limpiar cola y resetear para nuevo requerimiento
            print(f"🔄 [Multi-Req] Usuario quiere empezar un requerimiento nuevo, limpiando cola...")
            requirements = []
            current_req_index = 0
            # Continuar como mensaje nuevo normal (el user_text se procesará normalmente)
            # NO retornar aquí, continuar con el flujo normal
        # Si control_action fue manejado y retornó, no llegamos aquí
        # Si control_action no retornó (continue_current o new_requirement), continuar con el flujo normal
    
    # Solo recuperar requirements desde el historial si NO se manejó control_action o si control_action no retornó
    # (ya se recuperaron al inicio si había control_action)
    if not control_action:
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
                
                # Verificar si todos los requerimientos están 'done'
                # Si todos están 'done', limpiar requirements para tratar como nueva interacción
                if requirements:
                    all_done = all(req.get("status") == "done" for req in requirements)
                    if all_done:
                        print(f"🔄 [Requirements] Todos los requerimientos están 'done', limpiando para nueva interacción")
                        requirements = []
                        current_req_index = 0
                    else:
                        # Verificar que el requerimiento actual no esté 'done'
                        if current_req_index < len(requirements):
                            current_req = requirements[current_req_index]
                            if current_req.get("status") == "done":
                                # Buscar el siguiente requerimiento pendiente
                                remaining_indices = [i for i, r in enumerate(requirements) if r.get("status") == "pending"]
                                if remaining_indices:
                                    current_req_index = remaining_indices[0]
                                    print(f"🔄 [Requirements] Requerimiento actual estaba 'done', actualizando a índice {current_req_index}")
                                else:
                                    # No hay requerimientos pendientes, limpiar
                                    print(f"🔄 [Requirements] Requerimiento actual está 'done' y no hay más pendientes, limpiando")
                                    requirements = []
                                    current_req_index = 0
                break
    
    # 1. Procesar archivo subido si existe (usar función centralizada)
    if uploaded_file:
        _process_uploaded_file(uploaded_file)
    
    # 2. Verificar primero si el mensaje es una confirmación (antes de detectar stage)
    # Esto es importante porque "si" puede ser malinterpretado como nueva intención
    # PERO primero verificar si estamos en stage de selección de solicitudes relacionadas
    # porque "no hay solicitud relacionada" NO es una confirmación negativa
    
    # Detectar stage primero para evitar falsos positivos
    ctx_temp = ChatContext.from_history(conversation_history)
    stage_temp = ctx_temp.stage.value
    
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
                        
                        response = build_need_confirm_response(
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
                        response = build_need_confirm_response(
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
                        # Verificar si hay pending_related_requests (confirmación de procesar en orden)
                        pending_related = False
                        related_requests_pending = []
                        requirements_confirm = []
                        current_req_index_confirm = 0
                        for msg_req in reversed(conversation_history):
                            role_req = msg_req.get("role") or msg_req.get("who")
                            if role_req in ("bot", "assistant"):
                                meta_req = msg_req.get("meta") or {}
                                extra_req = meta_req.get("extra") or {}
                                if isinstance(extra_req, dict):
                                    if extra_req.get("pending_related_requests"):
                                        pending_related = True
                                        # Buscar related_requests en extra primero, luego en el nivel raíz
                                        related_requests_pending = extra_req.get("related_requests") or msg_req.get("related_requests") or []
                                        if extra_req.get("requirements"):
                                            requirements_confirm = extra_req.get("requirements", [])
                                            current_req_index_confirm = extra_req.get("current_requirement_index", 0)
                                        if pending_related:
                                            break
                        
                        # Si hay pending_related_requests, mostrar las solicitudes relacionadas
                        if pending_related and related_requests_pending:
                            primer_nombre = obtener_primer_nombre(student_data)
                            mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
                            
                            # Obtener el texto del requerimiento actual desde los requirements
                            req_text = ""
                            if requirements_confirm and current_req_index_confirm < len(requirements_confirm):
                                current_req = requirements_confirm[current_req_index_confirm]
                                req_slots = current_req.get("slots", {})
                                req_text = req_slots.get("original_user_message", "")
                            
                            # Si no se encontró en requirements, intentar desde pending_slots
                            if not req_text and pending_slots:
                                req_text = pending_slots.get("original_user_message", "")
                            
                            # Si aún no se encontró, usar el user_text actual
                            if not req_text:
                                req_text = user_text if user_text and not es_confirmacion_positiva(user_text) and not es_confirmacion_negativa(user_text) else "tu requerimiento"
                            
                            user_message = f"{mensaje_inicio}He encontrado {len(related_requests_pending)} solicitud(es) relacionada(s) con el requerimiento: {req_text}\n\n"
                            for i, req in enumerate(related_requests_pending, 1):
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
                                "related_requests": related_requests_pending,
                                "no_related_request_option": True,
                                "confirmed": True,
                                "intent_slots": pending_slots or {},
                                "reasoning": "",
                                "extra": {
                                    "requirements": requirements_confirm,
                                    "current_requirement_index": current_req_index_confirm
                                }
                            }
                            return response
                        
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
                                response = build_need_confirm_response(
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
                        
                        return build_frontend_response(
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
        ctx = ChatContext.from_history(conversation_history)
        stage = stage_temp  # Mantener el stage detectado arriba
        pending_slots = ctx.pending_slots
        handoff_channel = ctx.handoff_channel
    else:
        ctx = ChatContext.from_history(conversation_history)
        stage = ctx.stage.value
        pending_slots = ctx.pending_slots
        handoff_channel = ctx.handoff_channel
    
    print(f"📊 [Stage Detection] Stage final detectado: {stage}")
    
    # 6. Etapa de detalles de handoff (usuario proporciona detalles y archivo para enviar al departamento)
    # Verificar PRIMERO si estamos en AWAIT_HANDOFF_DETAILS para procesar directamente
    if stage == ConversationStage.AWAIT_HANDOFF_DETAILS.value:
        print(f"🔍 [Handoff Details] Procesando stage await_handoff_details")
        print(f"   user_text: '{user_text[:100]}'")
        print(f"   uploaded_file: {uploaded_file.name if uploaded_file else 'None'}")
        print(f"   handoff_channel: {handoff_channel}")
        
        print(f"\n{'='*80}")
        print(f"🔍 [PrivateGPTChat] RECUPERANDO CATEGORY/SUBCATEGORY PARA HANDOFF")
        print(f"{'='*80}")
        print(f"   category inicial: '{category}'")
        print(f"   subcategory inicial: '{subcategory}'")
        print(f"   pending_slots category: '{pending_slots.get('category') if pending_slots else None}'")
        print(f"   pending_slots subcategory: '{pending_slots.get('subcategory') if pending_slots else None}'")
        
        # Recuperar category y subcategory desde el historial si no están disponibles
        if not category or not subcategory:
            print(f"   ⚠️ Category o subcategory no están disponibles, buscando en historial...")
            for i, msg in enumerate(reversed(conversation_history)):
                role = msg.get("role") or msg.get("who")
                if role in ("bot", "assistant"):
                    msg_category = msg.get("category") or (msg.get("meta") or {}).get("category")
                    msg_subcategory = msg.get("subcategory") or (msg.get("meta") or {}).get("subcategory")
                    print(f"      Mensaje {i+1} (bot): category='{msg_category}', subcategory='{msg_subcategory}'")
                    if msg_category and msg_subcategory:
                        if not category:
                            category = msg_category
                            print(f"         → category actualizado a: '{category}'")
                        if not subcategory:
                            subcategory = msg_subcategory
                            print(f"         → subcategory actualizado a: '{subcategory}'")
                        break
                    # También buscar en intent_slots si está disponible
                    intent_slots_msg = msg.get("intent_slots") or (msg.get("meta") or {}).get("intent_slots")
                    if intent_slots_msg and isinstance(intent_slots_msg, dict):
                        print(f"         Intentando obtener desde intent_slots...")
                        # Intentar obtener desde slots si hay información de categoría
                        if not category and intent_slots_msg.get("category"):
                            category = intent_slots_msg.get("category")
                            print(f"            → category desde intent_slots: '{category}'")
                        if not subcategory and intent_slots_msg.get("subcategory"):
                            subcategory = intent_slots_msg.get("subcategory")
                            print(f"            → subcategory desde intent_slots: '{subcategory}'")
        
        # También intentar obtener desde pending_slots si están disponibles
        if pending_slots:
            if not category and pending_slots.get("category"):
                category = pending_slots.get("category")
                print(f"   → category desde pending_slots: '{category}'")
            if not subcategory and pending_slots.get("subcategory"):
                subcategory = pending_slots.get("subcategory")
                print(f"   → subcategory desde pending_slots: '{subcategory}'")
        
        print(f"\n✅ [PrivateGPTChat] VALORES FINALES RECUPERADOS:")
        print(f"   category final: '{category}'")
        print(f"   subcategory final: '{subcategory}'")
        print(f"{'='*80}\n")
        
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
            student_name = get_student_name(student_data)
            
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
                f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo. ¿Hay algo mas en que te pueda ayudar?"
            )
            
            print(f"🔀 [Handoff] Solicitud enviada a: {handoff_channel}")
            
            # Recuperar requirements desde el historial usando función centralizada
            requirements_final, current_req_index_final = get_requirements_from_history(
                conversation_history,
                prefer_multi_req_confirmation=True
            )
            
            print(f"📋 [Handoff] Requirements recuperados: {len(requirements_final)} requerimientos, índice actual: {current_req_index_final}")
            if requirements_final:
                for i, req in enumerate(requirements_final):
                    print(f"   {i+1}. {req.get('summary', 'N/A')} (status: {req.get('status', 'N/A')})")
            
            # Construir respuesta usando _build_frontend_response para asegurar stage correcto
            response = build_frontend_response(
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
            print(f"\n{'='*80}")
            print(f"🔍 [PrivateGPTChat] ASIGNANDO VALORES A RESPUESTA FINAL (handoff)")
            print(f"{'='*80}")
            print(f"   category variable: '{category}'")
            print(f"   subcategory variable: '{subcategory}'")
            print(f"   handoff_channel: '{handoff_channel}'")
            print(f"   department_from_logs en slots: '{pending_slots.get('department_from_logs') if pending_slots else None}'")
            print(f"   subcategory_from_logs en slots: '{pending_slots.get('subcategory_from_logs') if pending_slots else None}'")
            print(f"   Valor final response['category']: '{category}'")
            print(f"   Valor final response['subcategory']: '{subcategory}'")
            print(f"{'='*80}\n")
            
            response["category"] = category
            response["subcategory"] = subcategory
            response["thinking_status"] = thinking_status_handoff  # Asegurar que esté en nivel superior
            response["handoff_sent"] = True  # Asegurar que esté en nivel superior para que finish_requirement_and_maybe_next lo detecte
            
            # Asegurar propagación de requirements antes de finalizar
            response = propagate_requirements_to_response(response, requirements_final, current_req_index_final)
            
            # Llamar a finish_requirement_and_maybe_next para mantener consistencia y mostrar el menú si hay más requerimientos
            # Esta función maneja correctamente el menú como mensaje separado
            return finish_requirement_and_maybe_next(response, requirements_final, current_req_index_final)
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
        
        return build_frontend_response(
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
            # Manejar selección de requerimiento (números o reformulate)
            user_text_str = str(user_text).strip().lower()
            
            # Detectar si el usuario seleccionó un número (1, 2, etc.) o "reformulate"
            selected_index = None
            
            # Buscar número en el texto (1, 2, 3, etc.)
            import re
            number_match = re.search(r'\b([1-9])\b', user_text_str)
            if number_match:
                selected_num = int(number_match.group(1))
                if 1 <= selected_num <= len(requirements):
                    selected_index = selected_num - 1  # Convertir a índice base 0
                    print(f"✅ [Multi-Req] Usuario seleccionó requerimiento #{selected_num} (índice {selected_index})")
            
            # Detectar si el usuario quiere reformular
            reformulate_keywords = ["reformular", "ninguno", "ninguna", "reformulate", "ninguno quiero reformular"]
            wants_reformulate = any(keyword in user_text_str for keyword in reformulate_keywords)
            
            if wants_reformulate:
                # Usuario quiere reformular → pedir que vuelva a escribir
                return build_frontend_response(
                    stage=ConversationStage.AWAIT_INTENT,
                    mode=ConversationMode.INFORMATIVE,
                    status=ConversationStatus.ANSWER,
                    message="Perfecto. Por favor, cuéntame nuevamente tu requerimiento de manera más clara y específica.",
                    has_information=False,
                    extra={
                        "has_more_requirements": False,
                        "clear_requirements": True
                    }
                )
            elif selected_index is not None and selected_index < len(requirements):
                # Usuario seleccionó un requerimiento válido
                selected_req = requirements[selected_index]
                selected_req_slots = selected_req.get("slots", {})
                
                # Actualizar current_req_index
                current_req_index = selected_index
                
                # Verificar si necesita confirmación
                needs_confirmation_req = selected_req_slots.get("needs_confirmation", True)
                
                if needs_confirmation_req:
                    # Mostrar confirmación del requerimiento seleccionado
                    confirm_text_req = selected_req_slots.get("confirm_text", "").strip()
                    if not confirm_text_req:
                        confirm_text_req = _confirm_text_from_slots(selected_req_slots)
                    
                    response = build_need_confirm_response(
                        confirm_text=confirm_text_req,
                        intent_slots=selected_req_slots,
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
                    # No necesita confirmación, proceder directamente
                    return _handle_confirmation_stage(
                        user_text="",  # No hay texto nuevo, solo usar los slots
                        pending_slots=selected_req_slots,
                        conversation_history=conversation_history,
                        category=category,
                        subcategory=subcategory,
                        student_data=student_data,
                        perfil_id=perfil_id,
                        requirements=requirements,
                        current_req_index=current_req_index
                    )
            else:
                # No se detectó una selección válida, pedir que seleccione
                return build_frontend_response(
                    stage=ConversationStage.AWAIT_INTENT,
                    mode=ConversationMode.INFORMATIVE,
                    status=ConversationStatus.NEED_DETAILS,
                    message="Por favor, selecciona una opción válida (1, 2, etc.) o indica si quieres reformular tu requerimiento.",
                    has_information=False,
                    extra={
                        "needs_requirement_selection": True,
                        "requirements": requirements,
                        "current_requirement_index": current_req_index
                    }
                )
        
        # Confirmación normal (no múltiples requerimientos)
        # Solo procesar como confirmación si hay requirements pendientes
        if es_confirmacion_positiva(user_text):
            # Verificar si hay requirements pendientes
            has_pending_requirements = requirements and any(req.get("status") != "done" for req in requirements)
            
            if has_pending_requirements:
                # Hay requirements pendientes, procesar confirmación normalmente
                return _handle_confirmation_stage(
                    user_text, pending_slots, conversation_history,
                    category, subcategory, student_data, perfil_id,
                    requirements, current_req_index
                )
            else:
                # No hay requirements pendientes, tratar como nueva interacción
                print(f"🔄 [Confirmation] Confirmación detectada pero no hay requirements pendientes, tratando como nueva interacción")
                requirements = []
                current_req_index = 0
                # Continuar con el flujo normal (reinterpretar)
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
                return build_need_confirm_response(confirm_text, slots, category, subcategory)
            else:
                # Si no necesita confirmación, proceder directamente
                return _handle_confirmation_stage(
                    user_text, slots, conversation_history,
                    category, subcategory, student_data, perfil_id
                )
    
    # 5. Etapa de selección de solicitud relacionada
    if stage == ConversationStage.AWAIT_RELATED_REQUEST.value:
        # Verificar primero si el usuario dice "no hay solicitud relacionada"
        user_text_lower_check = str(user_text).lower().strip()
        no_related_keywords_check = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                                   "sin relacionar", "no hay solicitud relacionada", "ninguna es", "ninguna solicitud"]
        user_said_no_related_check = any(keyword in user_text_lower_check for keyword in no_related_keywords_check)
        
        if user_said_no_related_check:
            # El usuario está respondiendo a la pregunta de solicitudes relacionadas
            # NO tratar como nuevo intento, continuar con el flujo de related requests
            print(f"🔄 [Stage Detection] Usuario dijo 'no hay solicitud relacionada, continuando con flujo")
        else:
            # Si llegamos aquí y no es confirmación ni handoff, es nuevo intento
            print(f"🔄 [Stage Detection] Detectado nuevo intento, tratando como nuevo intento")
            # Tratar como nuevo intento - continuar con el flujo normal
            stage = ConversationStage.AWAIT_INTENT.value
    
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
                depto = determinar_departamento_handoff(
                    user_text=original_user_request,
                    category=category,
                    subcategory=subcategory,
                    intent_slots=intent_slots,
                    student_data=student_data
                )
                response = build_handoff_response(depto, student_data, category, subcategory, intent_slots)
                # Finalizar requerimiento y ofrecer siguiente si hay más
                return finish_requirement_and_maybe_next(response, requirements, current_req_index)
        
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
            privategpt_result = call_privategpt_api(
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
            requirements_resp, current_req_index_resp = get_requirements_from_history(
                conversation_history,
                prefer_multi_req_confirmation=True
            )
            
            # Fallback: usar los requirements que ya se recuperaron al inicio de classify_with_privategpt
            if not requirements_resp and requirements:
                requirements_resp = requirements
                current_req_index_resp = current_req_index
                print(f"📋 [Multi-Req] Usando requirements desde contexto actual: {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
            
            response = build_informative_answer_response(
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
                response = propagate_requirements_to_response(response, requirements_resp, current_req_index_resp)
                
                print(f"📋 [Multi-Req] Llamando a finish_requirement_and_maybe_next con {len(requirements_resp)} requerimientos, índice actual: {current_req_index_resp}")
                return finish_requirement_and_maybe_next(response, requirements_resp, current_req_index_resp)
            else:
                print(f"⚠️ [Multi-Req] No hay requirements disponibles, retornando respuesta sin menú")
                return response
        
        # Si NO tiene información, determinar departamento y hacer handoff
        print(f"⚠️ [PrivateGPT] No se encontró información, derivando a agente humano")
        
        depto = determinar_departamento_handoff(
            user_text=original_user_request,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            student_data=student_data
        )
        
        print(f"🔀 [Handoff] Derivando a: {depto}")
        
        response = build_handoff_response(
            depto=depto,
            student_data=student_data,
            category=category,
            subcategory=subcategory,
            intent_slots=intent_slots,
            needs_handoff_details=True
        )
        
        # Asegurar que se usen los requirements correctos (todos los originales, no solo el actual)
        requirements_resp = requirements if requirements else []
        current_req_index_resp = current_req_index
        
        # Si no hay requirements en contexto, buscar en el historial (especialmente el mensaje con is_multi_req_confirmation)
        if not requirements_resp:
            print(f"⚠️ [Handoff] No hay requirements en contexto actual, buscando en historial...")
            requirements_resp, current_req_index_resp = get_requirements_from_history(
                conversation_history,
                prefer_multi_req_confirmation=True
            )
            print(f"📋 [Handoff] Requirements recuperados desde historial: {len(requirements_resp)} requerimientos")
        
        # Asegurar propagación de requirements antes de retornar
        if requirements_resp:
            response = propagate_requirements_to_response(response, requirements_resp, current_req_index_resp)
            print(f"📋 [Handoff] Requirements propagados: {len(requirements_resp)} requerimientos, índice: {current_req_index_resp}")
        else:
            print(f"⚠️ [Handoff] No hay requirements disponibles para propagar")
        
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
        
        _ensure_slot_has_classification(intent_slots_original, user_text)
        
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
                
                slot_original_message = slot_with_original.get("original_user_message") or user_text
                _ensure_slot_has_classification(slot_with_original, slot_original_message)

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
                    
                    slot_original_message = slot_with_original.get("original_user_message") or user_text
                    _ensure_slot_has_classification(slot_with_original, slot_original_message)

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
            slot_message = intent_slots.get("original_user_message") or intent_slots_original.get("original_user_message") or user_text
            _ensure_slot_has_classification(intent_slots, slot_message)
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
        
        # Si hay múltiples requerimientos, mostrar selección de requerimiento
        if multi_intent and len(requirements) > 1:
            print(f"📋 [Multi-Intent] Detectados {len(requirements)} requerimientos:")
            for i, req in enumerate(requirements):
                print(f"   {i+1}. {req.get('summary', 'N/A')} (status: {req.get('status')})")
            
            # Construir mensaje con los requerimientos como opciones numeradas
            primer_nombre = obtener_primer_nombre(student_data)
            mensaje_inicio = f"{primer_nombre}, " if primer_nombre else ""
            
            user_message = f"{mensaje_inicio}He identificado estos {len(requirements)} temas en tu mensaje:\n\n"
            for i, req in enumerate(requirements, 1):
                req_summary = req.get("summary", f"Requerimiento {i}")
                user_message += f"{req_summary}\n"
            
            user_message += f"\n¿Con cuál quieres que empecemos?"
            
            # Construir opciones para botones
            requirement_options = []
            for i, req in enumerate(requirements, 1):
                req_summary = req.get("summary", f"Requerimiento {i}")
                # Acortar el texto para el botón (máximo 50 caracteres)
                button_label = req_summary[:50] + "..." if len(req_summary) > 50 else req_summary
                requirement_options.append({
                    "id": f"req_{i}",
                    "label": f"{i}. {button_label}",
                    "requirement_index": i - 1  # Índice base 0
                })
            
            # Agregar opción para reformular
            requirement_options.append({
                "id": "reformulate",
                "label": "❌ Ninguno, quiero reformular",
                "requirement_index": -1
            })
            
            response = build_frontend_response(
                stage=ConversationStage.AWAIT_INTENT,
                mode=ConversationMode.INFORMATIVE,
                status=ConversationStatus.NEED_DETAILS,
                message=user_message,
                response=user_message,
                has_information=None,
                intent_slots=intent_slots_original,
                extra={
                    "needs_confirmation": False,
                    "needs_requirement_selection": True,  # Nuevo flag para selección de requerimiento
                    "confirmed": False,
                    "category": category,
                    "subcategory": subcategory,
                    "confidence": 0.85,
                    "requirements": requirements,
                    "current_requirement_index": current_req_index,
                    "requirement_options": requirement_options,  # Opciones para botones
                    "is_multi_req_confirmation": True  # Flag para identificar este tipo de mensaje
                }
            )
            
            # Asegurar que requirements y flags estén también en meta directamente
            if "meta" not in response:
                response["meta"] = {}
            response["meta"]["requirements"] = requirements
            response["meta"]["current_requirement_index"] = current_req_index
            response["meta"]["is_multi_req_confirmation"] = True
            response["meta"]["needs_requirement_selection"] = True
            response["meta"]["requirement_options"] = requirement_options
            # También en nivel superior
            response["requirements"] = requirements
            response["current_requirement_index"] = current_req_index
            response["requirement_options"] = requirement_options
            
            return response
        
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
        response = build_need_confirm_response(
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

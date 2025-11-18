# app/services/response_builder.py
"""
Construcción de respuestas para el frontend.
Centraliza la creación de respuestas con el contrato estándar.
"""
from typing import Dict, List, Any, Optional
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus


def build_frontend_response(
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
    
    # Propagar datos de clasificación del modelo entrenado hacia el nivel superior
    classification_data = None
    classification_conf = None
    if intent_slots:
        classification_data = intent_slots.get("classification_from_logs")
        classification_conf = intent_slots.get("classification_from_logs_conf")
    if extra:
        classification_data = extra.get("classification_from_logs", classification_data)
        classification_conf = extra.get("classification_from_logs_conf", classification_conf)

    if classification_data and "classification_from_logs" not in base:
        base["classification_from_logs"] = classification_data
    if classification_conf and "classification_from_logs_conf" not in base:
        base["classification_from_logs_conf"] = classification_conf

    # Asegurar que meta existe si hay campos que deben ir ahí
    if "meta" not in base:
        base["meta"] = {}
    
    # Si hay extra en la respuesta, también asegurar que esté en meta.extra
    if "extra" in base and isinstance(base["extra"], dict):
        if "extra" not in base["meta"]:
            base["meta"]["extra"] = {}
        # Copiar campos importantes de extra a meta.extra para persistencia
        important_fields = ["requirements", "current_requirement_index", "is_multi_req_confirmation", "requirement_options"]
        for field in important_fields:
            if field in base["extra"]:
                base["meta"]["extra"][field] = base["extra"][field]
        
        # También copiar requirement_options al nivel superior para fácil acceso
        if "requirement_options" in base["extra"]:
            base["requirement_options"] = base["extra"]["requirement_options"]
            base["meta"]["requirement_options"] = base["extra"]["requirement_options"]
    
    return base


def build_informative_answer_response(
    resumen: str,
    fuentes: list,
    intent_slots: dict,
    category: str | None = None,
    subcategory: str | None = None
) -> dict:
    """Construye respuesta para consulta informativa con información encontrada."""
    source_pdfs = sorted({f.get("archivo", "") for f in fuentes if f.get("archivo")})
    return build_frontend_response(
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


def build_need_confirm_response(
    confirm_text: str,
    intent_slots: dict,
    category: str | None = None,
    subcategory: str | None = None
) -> dict:
    """Construye respuesta cuando se necesita confirmación del usuario."""
    answer_type = intent_slots.get("answer_type", "informativo")
    mode = ConversationMode.INFORMATIVE if answer_type == "informativo" else ConversationMode.OPERATIVE
    
    return build_frontend_response(
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


def build_handoff_response_new(
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
    
    return build_frontend_response(
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


def build_error_response(msg: str) -> dict:
    """Construye respuesta de error técnico."""
    return build_frontend_response(
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


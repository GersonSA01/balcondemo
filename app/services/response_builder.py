# app/services/response_builder.py
"""
Construcción de respuestas para el frontend.
Centraliza la creación de respuestas con el contrato estándar.

TODOS los mensajes, botones y UI elements se generan desde el backend
y se envían al frontend como estructuras estructuradas.
El frontend solo renderiza lo que recibe.
"""
from typing import Dict, List, Any, Optional
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus


def build_message_object(
    who: str,
    text: str,
    type: str = "text",
    buttons: List[Dict[str, Any]] | None = None,
    meta: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """
    Construye un objeto de mensaje estructurado para el frontend.
    
    Args:
        who: "bot" o "user"
        text: Texto del mensaje
        type: Tipo de mensaje ("text", "greeting", "faq", "answer", "confirmation", "error", etc.)
        buttons: Lista de botones estructurados (opcional)
        meta: Metadata adicional del mensaje (opcional)
    
    Returns:
        Dict con estructura de mensaje
    """
    msg = {
        "who": who,
        "text": text,
        "type": type
    }
    
    if buttons:
        msg["buttons"] = buttons
    
    if meta:
        msg["meta"] = meta
    
    return msg


def build_button_object(
    id: str,
    label: str,
    action: str,
    style: str = "default"
) -> Dict[str, Any]:
    """
    Construye un objeto de botón estructurado para el frontend.
    
    Args:
        id: Identificador único del botón
        label: Texto que se muestra en el botón
        action: Acción a ejecutar cuando se hace click ("confirm", "cancel", "handoff", "close", etc.)
        style: Estilo del botón ("default", "primary", "secondary", "yes", "no", etc.)
    
    Returns:
        Dict con estructura de botón
    """
    return {
        "id": id,
        "label": label,
        "action": action,
        "style": style
    }


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
    messages: List[Dict[str, Any]] | None = None,  # ✅ NUEVO: Array de mensajes estructurados
    thinking_status: str | None = None,  # ✅ Mensaje de estado desde el backend ("Pensando", "Buscando documentos", etc.)
    thinking_status_alternate: List[str] | None = None,  # ✅ Array de mensajes para alternar (solo para PrivateGPT)
) -> dict:
    """
    Construye la respuesta estándar hacia el frontend.
    
    Centraliza la construcción de respuestas con el nuevo contrato:
    - stage: estado de la conversación
    - mode: modo de operación (informativo/operativo/handoff)
    - status: estado de la respuesta (answer/need_details/handoff/error)
    - messages: Array de mensajes estructurados (todos generados desde el backend)
    
    Si no se proporciona `messages`, se crea uno automáticamente con el mensaje principal.
    Mantiene campos legacy para compatibilidad durante la transición.
    """
    # Si no se proporciona messages, crear uno automáticamente con el mensaje principal
    if messages is None:
        messages = [build_message_object(who="bot", text=response or message, type="text")]
    
    base = {
        "stage": stage.value,
        "mode": mode.value,
        "status": status.value,
        "message": message,  # Mantener para compatibilidad
        "response": response or message,  # Mantener para compatibilidad
        "messages": messages,  # ✅ NUEVO: Array de mensajes estructurados
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
    base.setdefault("needs_faq_feedback", False)
    base.setdefault("faq_feedback_options", None)
    base.setdefault("category", None)
    base.setdefault("subcategory", None)
    base.setdefault("confidence", 0.9)
    base.setdefault("campos_requeridos", [])
    
    if extra:
        base.update(extra)
    
    # ✅ Agregar thinking_status al nivel superior para que el frontend lo pueda usar
    if thinking_status:
        base["thinking_status"] = thinking_status
    
    # ✅ Si hay thinking_status_alternate, usar ese (el frontend alternará entre los mensajes)
    if thinking_status_alternate:
        base["thinking_status_alternate"] = thinking_status_alternate
        # También establecer el primero como thinking_status inicial
        if thinking_status_alternate and len(thinking_status_alternate) > 0:
            base["thinking_status"] = thinking_status_alternate[0]
    
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
        # También copiarlos al nivel superior para fácil acceso del frontend
        important_fields = [
            "requirements", "current_requirement_index", "is_multi_req_confirmation", 
            "requirement_options", "needs_faq_feedback", "faq_feedback_options"
        ]
        for field in important_fields:
            if field in base["extra"]:
                # Copiar a meta.extra para persistencia
                base["meta"]["extra"][field] = base["extra"][field]
                # También copiar al nivel superior para fácil acceso del frontend
                base[field] = base["extra"][field]
                base["meta"][field] = base["extra"][field]
    
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
    subcategory: str | None = None,
    custom_buttons: List[Dict[str, Any]] | None = None,
    thinking_status: str | None = None  # ✅ Mensaje de estado desde el backend
) -> dict:
    """
    Construye respuesta cuando se necesita confirmación del usuario.
    Incluye mensaje estructurado con botones desde el backend.
    """
    answer_type = intent_slots.get("answer_type", "informativo")
    mode = ConversationMode.INFORMATIVE if answer_type == "informativo" else ConversationMode.OPERATIVE
    
    # Botones por defecto si no se proporcionan personalizados
    if custom_buttons is None:
        buttons = [
            build_button_object(id="confirm_yes", label="Sí", action="confirm", style="yes"),
            build_button_object(id="confirm_no", label="No", action="cancel", style="no")
        ]
    else:
        buttons = custom_buttons
    
    # Crear mensaje estructurado con botones
    confirm_message = build_message_object(
        who="bot",
        text=confirm_text,
        type="confirmation",
        buttons=buttons,
        meta={
            "needs_confirmation": True,
            "category": category,
            "subcategory": subcategory
        }
    )
    
    return build_frontend_response(
        stage=ConversationStage.AWAIT_CONFIRM,
        mode=mode,
        status=ConversationStatus.NEED_DETAILS,
        message=confirm_text,
        response=confirm_text,
        has_information=None,
        intent_slots=intent_slots,
        messages=[confirm_message],  # ✅ Mensaje estructurado con botones
        thinking_status=thinking_status,  # ✅ Mensaje de estado desde el backend
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


def build_seguimiento_response(
    solicitud: Dict[str, Any],
    historial_data: Dict[str, Any],
    student_name: str = "",
    intent_slots: Optional[Dict] = None
) -> dict:
    """
    Construye respuesta de seguimiento de solicitud.
    Muestra resumen de la solicitud, estado actual y acciones disponibles.
    
    Args:
        solicitud: Dict con datos de la solicitud
        historial_data: Dict con historial completo (eBalconyRequest, eBalconyRequestHistories)
        student_name: Nombre del estudiante para personalización
        intent_slots: Slots de intención para mantener contexto
    
    Returns:
        Dict con respuesta estructurada para frontend
    """
    from datetime import datetime
    
    codigo = solicitud.get("codigo") or solicitud.get("codigo_generado", "N/A")
    descripcion = solicitud.get("descripcion", "Sin descripción")
    estado_display = solicitud.get("estado_display", "DESCONOCIDO")
    fecha_creacion_v2 = solicitud.get("fecha_creacion_v2", "")
    nombre_servicio = solicitud.get("nombre_servicio", "Solicitud General")
    
    # Obtener último historial para información adicional
    historiales = historial_data.get("eBalconyRequestHistories", [])
    ultimo_historial = historiales[-1] if historiales else None
    
    # Construir mensaje principal con resumen
    saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
    
    mensaje_texto = (
        f"{saludo_nombre}estoy tomando como referencia tu solicitud **{codigo}** – {nombre_servicio}.\n\n"
        f"📅 **Fecha de creación**: {fecha_creacion_v2}\n"
        f"🏛️ **Departamento**: {ultimo_historial.get('departamento', 'En revisión') if ultimo_historial else 'En revisión'}\n"
        f"📌 **Estado actual**: **{estado_display}**"
    )
    
    # Agregar información del último historial si está disponible
    if ultimo_historial:
        observacion = ultimo_historial.get("observacion", "")
        if observacion:
            mensaje_texto += f"\n\n💬 **Última actualización**: {observacion[:200]}"
    
    # Mensaje principal
    mensaje_principal = build_message_object(
        who="bot",
        text=mensaje_texto,
        type="info",
        meta={
            "solicitud_id": solicitud.get("id"),
            "codigo_solicitud": codigo,
            "estado": solicitud.get("estado"),
            "estado_display": estado_display,
        }
    )
    
    # Botones de acción
    botones = []
    
    # Botón "Ver historial completo"
    boton_historial = build_button_object(
        id="ver_historial_solicitud",
        label="Ver historial completo",
        action="ver_historial",
        style="primary"
    )
    botones.append(boton_historial)
    
    # Botón "¿Qué significa este estado?"
    boton_explicar_estado = build_button_object(
        id="explicar_estado_solicitud",
        label="¿Qué significa este estado?",
        action="explicar_estado",
        style="secondary"
    )
    botones.append(boton_explicar_estado)
    
    # Botón "¿Qué debo hacer ahora?" (solo si está en CORRECCIÓN o necesita acción)
    if solicitud.get("estado") == 6:  # ESTADO_CORRECCION
        boton_que_hacer = build_button_object(
            id="que_hacer_solicitud",
            label="¿Qué debo hacer ahora?",
            action="que_hacer",
            style="warning"
        )
        botones.append(boton_que_hacer)
    
    # Botón "Explicar el trámite relacionado" (para contexto RAG)
    boton_explicar_tramite = build_button_object(
        id="explicar_tramite_relacionado",
        label="Explicarme el trámite relacionado",
        action="explicar_tramite",
        style="info"
    )
    botones.append(boton_explicar_tramite)
    
    # Agregar botones al mensaje principal
    mensaje_principal["buttons"] = botones
    
    # Construir respuesta
    return build_frontend_response(
        stage=ConversationStage.ANSWER_READY,
        mode=ConversationMode.INFORMATIVE,
        status=ConversationStatus.ANSWER,
        message=mensaje_texto,
        response=mensaje_texto,
        has_information=True,
        intent_slots=intent_slots or {},
        messages=[mensaje_principal],
        extra={
            "solicitud_seguimiento": solicitud,
            "historial_solicitud": historial_data,
            "related_request_id": solicitud.get("id"),
            "related_request_codigo": codigo,
            "confidence": 1.0,
        },
    )


def build_error_response(msg: str) -> dict:
    """
    Construye respuesta de error técnico.
    Incluye mensaje estructurado de error desde el backend.
    """
    error_message = build_message_object(
        who="bot",
        text=msg,
        type="error",
        meta={
            "is_error": True
        }
    )
    
    return build_frontend_response(
        stage=ConversationStage.AWAIT_INTENT,
        mode=ConversationMode.INFORMATIVE,
        status=ConversationStatus.ERROR,
        message=msg,
        response=msg,
        has_information=False,
        messages=[error_message],  # ✅ Mensaje estructurado de error
        extra={
            "confidence": 0.0,
        }
    )


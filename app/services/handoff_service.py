# app/services/handoff_service.py
"""
Servicio para manejo de handoff (derivación a humano).
Maneja la determinación de departamentos, construcción de respuestas de handoff
y procesamiento de detalles de handoff (archivos y descripciones).
"""
from typing import Dict, List, Any, Optional
from .handoff import get_departamento_real, classify_with_heuristics
from .response_builder import build_frontend_response, build_handoff_response_new
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus
from .solicitud_service import crear_solicitud
from .student_data_service import get_student_name
from .requirements_service import get_requirements_from_history, propagate_requirements_to_response, finish_requirement_and_maybe_next


def determinar_departamento_handoff(
    user_text: str,
    category: str = None,
    subcategory: str = None,
    intent_slots: Dict = None,
    student_data: Dict = None
) -> str:
    """
    Determina el departamento al que se debe derivar la solicitud.
    
    Prioridad:
    1. department_from_logs (modelo entrenado en logs históricos)
    2. Desde categoría/subcategoría
    3. Heurísticas
    4. Por defecto
    
    Returns:
        Nombre del departamento
    """
    # Prioridad 1: Usar departamento aprendido de logs históricos (más confiable)
    if intent_slots:
        dept_from_logs = intent_slots.get("department_from_logs")
        conf_dep = intent_slots.get("classification_from_logs_conf", {}).get("dep", 0.0)
        if dept_from_logs and conf_dep >= 0.7:
            print(f"🏢 [Handoff] Departamento desde modelo entrenado (logs): {dept_from_logs} (conf={conf_dep:.2f})")
            return dept_from_logs
    
    # Prioridad 2: Intentar obtener departamento desde categoría/subcategoría
    if category and subcategory:
        depto = get_departamento_real(category, subcategory)
        if depto:
            print(f"🏢 [Handoff] Departamento desde categoría: {depto}")
            return depto
    
    # Prioridad 3: Si hay intent_slots, usar classify_with_heuristics (sin LLM)
    if intent_slots:
        try:
            heuristic_classification = classify_with_heuristics(intent_slots)
            depto_heur = heuristic_classification.get("channel")
            if depto_heur:
                print(f"🏢 [Handoff] Departamento desde heurísticas: {depto_heur}")
                return depto_heur
        except Exception as e:
            print(f"⚠️ [Handoff] Error al usar heurísticas para determinar departamento: {e}")
    
    # Prioridad 4: Departamento por defecto
    default_depto = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
    print(f"🏢 [Handoff] Usando departamento por defecto: {default_depto}")
    return default_depto


def build_handoff_response(
    depto: str,
    student_data: Optional[Dict],
    category: Optional[str],
    subcategory: Optional[str],
    intent_slots: Optional[Dict],
    needs_handoff_details: bool = True,
    reason: str = "Solicitud operativa que requiere intervención humana"
) -> Dict[str, Any]:
    """
    Construye respuesta de handoff unificada.
    Usa build_handoff_response_new internamente para consistencia.
    """
    student_name = get_student_name(student_data)
    saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
    
    if needs_handoff_details:
        ask_msg = (
            f"{saludo_nombre}este caso necesita ser revisado por mis compañeros humanos del departamento **{depto}**. 💁\n\n"
            f"Para enviar tu solicitud, por favor:\n"
            f"1. Describe nuevamente tu requerimiento con todos los detalles.\n"
            f"2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\n"
            f"Con esta información podré derivarlo al equipo correspondiente. ✔️"
        )
    else:
        ask_msg = (
            f"{saludo_nombre}Tu solicitud ha sido enviada exitosamente al departamento **{depto}**. \n\n"
            f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo. ¿Hay algo mas en que te pueda ayudar?"
        )
    
    return build_handoff_response_new(
        resumen=ask_msg,
        depto_real=depto,
        intent_slots=intent_slots,
        needs_handoff_details=needs_handoff_details,
        category=category,
        subcategory=subcategory,
        student_data=student_data
    )


def process_handoff_details(
    user_text: str,
    uploaded_file: Any,
    conversation_history: List[Dict],
    handoff_channel: str,
    category: Optional[str],
    subcategory: Optional[str],
    student_data: Optional[Dict],
    pending_slots: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Procesa los detalles de handoff cuando el usuario proporciona descripción y archivo.
    
    Args:
        user_text: Descripción del usuario
        uploaded_file: Archivo subido
        conversation_history: Historial de conversación
        handoff_channel: Canal/departamento de handoff
        category: Categoría de la solicitud
        subcategory: Subcategoría de la solicitud
        student_data: Datos del estudiante
        pending_slots: Slots pendientes (opcional)
    
    Returns:
        Respuesta con confirmación de solicitud enviada
    """
    # Recuperar category y subcategory desde el historial si no están disponibles
    if not category or not subcategory:
        for msg in reversed(conversation_history):
            role = msg.get("role") or msg.get("who")
            if role in ("bot", "assistant"):
                msg_category = msg.get("category") or (msg.get("meta") or {}).get("category")
                msg_subcategory = msg.get("subcategory") or (msg.get("meta") or {}).get("subcategory")
                if msg_category and msg_subcategory:
                    if not category:
                        category = msg_category
                    if not subcategory:
                        subcategory = msg_subcategory
                    break
                # También buscar en intent_slots si está disponible
                intent_slots_msg = msg.get("intent_slots") or (msg.get("meta") or {}).get("intent_slots")
                if intent_slots_msg and isinstance(intent_slots_msg, dict):
                    if not category and intent_slots_msg.get("category"):
                        category = intent_slots_msg.get("category")
                    if not subcategory and intent_slots_msg.get("subcategory"):
                        subcategory = intent_slots_msg.get("subcategory")
    
    details_text = (user_text or "").strip()
    has_file = uploaded_file is not None
    
    if not has_file:
        # Falta archivo
        print(f"⚠️ [Handoff Details] Usuario no ha subido archivo")
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
    
    # Usuario proporcionó detalles Y archivo → Enviar handoff y crear solicitud
    print(f"✅ [Handoff] Usuario proporcionó detalles y archivo, enviando solicitud")
    print(f"   Detalles: '{details_text[:100]}'")
    print(f"   Archivo: {uploaded_file.name if uploaded_file else 'N/A'}")
    
    # ✅ Mensaje de estado desde el backend
    thinking_status_handoff = "Enviando solicitud a mis compañeros humanos"
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
        
        # Obtener perfil activo
        perfiles = student_data.get("perfiles", [])
        if perfiles:
            perfil_principal = next((p for p in perfiles if p.get("inscripcionprincipal")), perfiles[0])
            perfil_id = perfil_principal.get("id")
            
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
    
    saludo_nombre = f"{student_name.split()[0]}, " if student_name else ""
    
    # Mensaje final de confirmación
    final_message = (
        f"{saludo_nombre} Tu solicitud ha sido enviada exitosamente al departamento **{handoff_channel or 'correspondiente'}**. \n\n"
        f"Un agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo. ¿Hay algo mas en que te pueda ayudar?"
    )
    
    # Recuperar requirements desde el historial
    requirements_final, current_req_index_final = get_requirements_from_history(
        conversation_history,
        prefer_multi_req_confirmation=True
    )
    
    # Construir respuesta
    response = build_frontend_response(
        stage=ConversationStage.ANSWER_READY,
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
            "close_chat": False,
            "confirmed": True,
            "handoff": True,
            "handoff_channel": handoff_channel,
            "source_pdfs": [],
            "fuentes": [],
            "thinking_status": thinking_status_handoff,
        }
    )
    
    response["category"] = category
    response["subcategory"] = subcategory
    response["thinking_status"] = thinking_status_handoff
    response["handoff_sent"] = True
    
    # Asegurar propagación de requirements antes de finalizar
    response = propagate_requirements_to_response(response, requirements_final, current_req_index_final)
    
    # Finalizar requerimiento y ofrecer siguiente si hay más
    return finish_requirement_and_maybe_next(response, requirements_final, current_req_index_final)


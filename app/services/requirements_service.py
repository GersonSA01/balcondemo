# app/services/requirements_service.py
"""
Servicio para gestión de requirements (requerimientos multi-intento).
Maneja la recuperación, propagación y finalización de requirements.
"""
from typing import Dict, List, Any, Optional, Tuple
from .chat_domain import Requirement
from .response_builder import build_message_object, build_button_object
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus


def get_requirements_from_history(
    conversation_history: List[Dict],
    prefer_multi_req_confirmation: bool = False
) -> Tuple[List[Dict], int]:
    """
    Recupera requirements y current_requirement_index desde el historial de conversación.
    
    Args:
        conversation_history: Lista de mensajes del historial
        prefer_multi_req_confirmation: Si True, prioriza mensajes con is_multi_req_confirmation
    
    Returns:
        Tupla (requirements, current_requirement_index)
    """
    requirements = []
    current_req_index = 0
    
    print(f"🔍 [Requirements] Buscando en historial de {len(conversation_history)} mensajes...")
    
    for i, msg in enumerate(reversed(conversation_history)):
        role = msg.get("role") or msg.get("who")
        if role in ("bot", "assistant"):
            # Buscar en múltiples lugares
            meta = msg.get("meta") or {}
            extra_from_meta = meta.get("extra") or {}
            extra_from_msg = msg.get("extra") or {}
            
            # Priorizar meta.extra sobre extra directo
            extra = extra_from_meta if extra_from_meta else extra_from_msg
            
            # También buscar directamente en el nivel superior del mensaje y en meta directamente
            reqs_from_top = msg.get("requirements")
            reqs_from_meta = meta.get("requirements") if isinstance(meta, dict) else None
            
            # Priorizar: 1) meta.extra, 2) meta directamente, 3) extra del mensaje, 4) nivel superior
            reqs = None
            idx = 0
            has_multi_req_flag = False
            
            # 1. Buscar en meta.extra primero
            if isinstance(extra, dict) and extra.get("requirements"):
                reqs = extra.get("requirements", [])
                idx = extra.get("current_requirement_index", 0)
                has_multi_req_flag = extra.get("is_multi_req_confirmation", False)
            # 2. Buscar en meta directamente
            elif reqs_from_meta and isinstance(reqs_from_meta, list):
                reqs = reqs_from_meta
                idx = meta.get("current_requirement_index", 0)
                has_multi_req_flag = meta.get("is_multi_req_confirmation", False) or meta.get("needs_requirement_selection", False)
            # 3. Buscar en extra del mensaje
            elif isinstance(extra_from_msg, dict) and extra_from_msg.get("requirements"):
                reqs = extra_from_msg.get("requirements", [])
                idx = extra_from_msg.get("current_requirement_index", 0)
                has_multi_req_flag = extra_from_msg.get("is_multi_req_confirmation", False)
            # 4. Fallback: buscar en el nivel superior del mensaje
            elif reqs_from_top and isinstance(reqs_from_top, list):
                reqs = reqs_from_top
                idx = msg.get("current_requirement_index", 0)
            
            if reqs:
                # Si preferimos multi_req_confirmation y este mensaje lo tiene, usarlo
                if prefer_multi_req_confirmation and has_multi_req_flag:
                    requirements = reqs
                    current_req_index = idx
                    print(f"✅ [Requirements] Recuperados desde mensaje con is_multi_req_confirmation: {len(requirements)} requerimientos, índice: {current_req_index}")
                    break
                # Si no hay preferencia o no encontramos uno con multi_req_confirmation, usar el primero encontrado
                elif not prefer_multi_req_confirmation or not requirements:
                    requirements = reqs
                    current_req_index = idx
                    if not prefer_multi_req_confirmation:
                        print(f"✅ [Requirements] Recuperados desde historial: {len(requirements)} requerimientos, índice: {current_req_index}")
                    break
    
    if not requirements:
        print(f"⚠️ [Requirements] No se encontraron requirements en el historial")
    else:
        # ✅ Verificar si todos los requerimientos están 'done'
        # Si todos están 'done', limpiar requirements para tratar como nueva interacción
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
    
    return requirements, current_req_index


def propagate_requirements_to_response(
    response: dict,
    requirements: list[dict],
    current_req_index: int
) -> dict:
    """
    Propaga requirements y current_requirement_index a una respuesta.
    Asegura que estén tanto en extra como en meta.extra.
    
    Args:
        response: Diccionario de respuesta
        requirements: Lista de requerimientos
        current_req_index: Índice del requerimiento actual
    
    Returns:
        Respuesta modificada con requirements propagados
    """
    if not response:
        response = {}
    
    # Asegurar que extra existe
    if "extra" not in response:
        response["extra"] = {}
    
    response["extra"]["requirements"] = requirements
    response["extra"]["current_requirement_index"] = current_req_index
    
    # También guardar en meta para persistencia en historial
    if "meta" not in response:
        response["meta"] = {}
    if "extra" not in response["meta"]:
        response["meta"]["extra"] = {}
    
    response["meta"]["extra"]["requirements"] = requirements
    response["meta"]["extra"]["current_requirement_index"] = current_req_index
    
    return response


def finish_requirement_and_maybe_next(
    base_response: dict,
    requirements: list[dict],
    current_index: int
) -> dict:
    """
    Marca un requerimiento como terminado y ofrece opciones si hay más pendientes.
    
    Args:
        base_response: Respuesta base que ya se construyó
        requirements: Lista de requerimientos con status
        current_index: Índice del requerimiento actual
    
    Returns:
        Respuesta modificada con opciones de siguiente requerimiento
    """
    print(f"📋 [Finish Requirement] Iniciando con {len(requirements) if requirements else 0} requirements, índice: {current_index}")
    
    if not requirements or current_index >= len(requirements):
        print(f"⚠️ [Finish Requirement] No hay requirements válidos o índice fuera de rango")
        return base_response
    
    # 1) Marcar como terminado
    requirements[current_index]["status"] = "done"
    print(f"✅ [Finish Requirement] Requerimiento {current_index} marcado como 'done': {requirements[current_index].get('summary', 'N/A')}")
    
    remaining = [r for r in requirements if r["status"] == "pending"]
    print(f"📋 [Finish Requirement] Requerimientos pendientes: {len(remaining)}")
    
    # Asegurar que extra existe
    if "extra" not in base_response:
        base_response["extra"] = {}
    
    base_response["extra"]["requirements"] = requirements
    base_response["extra"]["current_requirement_index"] = current_index
    
    # También guardar en meta para que el frontend pueda encontrarlo en el historial
    if "meta" not in base_response:
        base_response["meta"] = {}
    if "extra" not in base_response["meta"]:
        base_response["meta"]["extra"] = {}
    base_response["meta"]["extra"]["requirements"] = requirements
    base_response["meta"]["extra"]["current_requirement_index"] = current_index
    
    if not remaining:
        # No hay más requerimientos pendientes → limpiar estados y cerrar
        print(f"📋 [Finish Requirement] No hay más requerimientos pendientes, limpiando estados")
        base_response["extra"]["has_more_requirements"] = False
        base_response["meta"]["extra"]["has_more_requirements"] = False
        base_response["extra"]["clear_requirements"] = True
        base_response["meta"]["extra"]["clear_requirements"] = True
        base_response["extra"]["needs_requirement_selection"] = False
        base_response["meta"]["extra"]["needs_requirement_selection"] = False
        base_response["close_chat"] = False
        return base_response
    
    # ✅ NUEVO: Si solo queda 1 requerimiento pendiente, mostrar mini menú de "¿continuamos con el otro tema?"
    if len(remaining) == 1:
        next_req = remaining[0]
        next_summary = next_req.get("summary", next_req.get("intent_short", "otro requerimiento"))
        next_req_id = next_req.get("id")
        current_summary = requirements[current_index].get("summary", requirements[current_index].get("intent_short", "el tema actual"))
        
        # Encontrar el índice del siguiente requerimiento
        next_index_candidates = [i for i, r in enumerate(requirements) if r.get("id") == next_req_id]
        next_index = next_index_candidates[0] if next_index_candidates else None
        
        if next_index is None:
            # Fallback: buscar por índice en remaining
            remaining_indices = [i for i, r in enumerate(requirements) if r["status"] == "pending"]
            next_index = remaining_indices[0] if remaining_indices else current_index
        
        print(f"✅ [Finish Requirement] Solo queda 1 requerimiento pendiente, mostrando mini menú para avanzar al índice {next_index}: '{next_summary}'")
        print(f"   → NO se mostrará menú grande de '2 temas', sino mini menú de '¿continuamos con el otro tema?'")
        
        # Actualizar current_requirement_index al siguiente requerimiento (pero aún no lo activamos hasta que el usuario confirme)
        base_response["extra"]["current_requirement_index"] = current_index  # Mantener el actual hasta confirmación
        base_response["meta"]["extra"]["current_requirement_index"] = current_index
        base_response["extra"]["requirements"] = requirements
        base_response["meta"]["extra"]["requirements"] = requirements
        base_response["extra"]["next_requirement_index"] = next_index  # Guardar el siguiente para cuando confirme
        
        # ✅ IMPORTANTE: NO poner needs_requirement_selection=True (no es menú grande de selección de temas)
        base_response["extra"]["has_more_requirements"] = True
        base_response["meta"]["extra"]["has_more_requirements"] = True
        base_response["extra"]["needs_requirement_selection"] = False  # ✅ NO mostrar menú grande
        base_response["meta"]["extra"]["needs_requirement_selection"] = False
        base_response["meta"]["is_multi_req_confirmation"] = False  # ✅ NO es confirmación multi-requirement grande
        base_response["meta"]["extra"]["is_multi_req_confirmation"] = False
        base_response["needs_requirement_selection"] = False  # ✅ También en nivel superior para compatibilidad
        base_response["meta"]["needs_requirement_selection"] = False
        
        # ✅ Limpiar requirement_options para asegurar que el frontend no muestre el menú grande
        base_response["extra"]["requirement_options"] = []
        base_response["meta"]["extra"]["requirement_options"] = []
        base_response["meta"]["requirement_options"] = []
        base_response["requirement_options"] = []
        
        # ✅ Construir mensaje estructurado con mini menú para continuar con el siguiente tema
        texto_mini_menu = (
            f"\n\nYa te ayudé con **{current_summary}** ✅\n\n"
            f"También tengo identificado este otro tema pendiente:\n"
            f"• **{next_summary}**\n\n"
            f"¿Quieres que lo veamos ahora?"
        )
        
        # Botones para el mini menú
        boton_continuar = build_button_object(
            id="go_next_requirement",
            label="Sí, continuar con este tema",
            action="go_next_requirement",
            style="primary"
        )
        
        boton_terminar = build_button_object(
            id="discard_remaining_requirements",
            label="No, ya terminé por ahora",
            action="discard_remaining_requirements",
            style="secondary"
        )
        
        mini_menu_msg = build_message_object(
            who="bot",
            text=texto_mini_menu,
            type="info",
            buttons=[boton_continuar, boton_terminar],
            meta={
                "is_next_requirement_prompt": True,
                "next_requirement_index": next_index,
                "next_requirement_id": next_req_id,
            }
        )
        
        # Agregar el mensaje estructurado a los mensajes existentes
        if "messages" not in base_response:
            base_response["messages"] = []
        if not isinstance(base_response["messages"], list):
            # Si messages es un string o dict, convertirlo a lista
            base_response["messages"] = [base_response["messages"]]
        
        base_response["messages"].append(mini_menu_msg)
        
        # Asegurar que stage y status permitan esperar la respuesta del usuario
        base_response["stage"] = ConversationStage.AWAIT_INTENT.value
        base_response["status"] = ConversationStatus.NEED_DETAILS.value
        
        return base_response
    
    # ✅ Solo si hay 2+ requerimientos pendientes → mostrar menú de selección completo
    print(f"📋 [Finish Requirement] Hay {len(remaining)} requerimientos pendientes, preparando menú de selección")
    next_req = remaining[0]
    next_summary = next_req.get("summary", next_req.get("intent_short", "otro requerimiento"))
    next_req_id = next_req.get("id", "N/A")
    current_summary = requirements[current_index].get("summary", requirements[current_index].get("intent_short", "el tema actual"))
    
    # Verificar que el siguiente requerimiento NO sea el que acabamos de procesar
    if next_req_id == requirements[current_index].get("id"):
        if len(remaining) > 1:
            next_req = remaining[1]
            next_summary = next_req.get("summary", next_req.get("intent_short", "otro requerimiento"))
            next_req_id = next_req.get("id", "N/A")
            print(f"✅ [Finish Requirement] Corrigiendo: usando el siguiente requerimiento pendiente: {next_summary}")
    
    # Construir texto del menú
    texto_menu = (
        f"\n\nYa terminé con **{current_summary}** ✅\n\n"
        f"Tengo {len(remaining)} tema(s) pendiente(s). ¿Qué quieres hacer ahora?"
    )
    
    # Construir botones para el menú
    botones_menu = []
    
    # Botón "Seguir con este mismo tema"
    boton_continuar_actual = build_button_object(
        id="continue_current",
        label="Seguir con este mismo tema",
        action="continue_current",
        style="secondary"
    )
    botones_menu.append(boton_continuar_actual)
    
    # Botón "Pasar al siguiente requerimiento"
    # Acortar el texto si es muy largo
    label_siguiente = next_summary[:50] + "..." if len(next_summary) > 50 else next_summary
    boton_siguiente = build_button_object(
        id="go_next_requirement",
        label=f"Pasar al siguiente: {label_siguiente}",
        action="go_next_requirement",
        style="primary"
    )
    botones_menu.append(boton_siguiente)
    
    # Botón "Cerrar"
    boton_cerrar = build_button_object(
        id="close_all",
        label="No hacer nada más, cerrar",
        action="close_all",
        style="secondary"
    )
    botones_menu.append(boton_cerrar)
    
    # Crear mensaje estructurado con el menú
    menu_msg = build_message_object(
        who="bot",
        text=texto_menu,
        type="info",
        buttons=botones_menu,
        meta={
            "is_multi_req_menu": True,
            "remaining_count": len(remaining),
        }
    )
    
    # Agregar el mensaje estructurado a los mensajes existentes
    if "messages" not in base_response:
        base_response["messages"] = []
    if not isinstance(base_response["messages"], list):
        base_response["messages"] = [base_response["messages"]]
    
    base_response["messages"].append(menu_msg)
    
    # Establecer flags y opciones en extra (para compatibilidad con código existente)
    base_response["extra"]["has_more_requirements"] = True
    base_response["extra"]["next_requirement_id"] = next_req["id"]
    next_index_candidates = [i for i, r in enumerate(requirements) if r.get("id") == next_req.get("id")]
    base_response["extra"]["next_requirement_index"] = next_index_candidates[0] if next_index_candidates else None
    base_response["extra"]["ui_next_step"] = "multi_requirement_menu"
    base_response["extra"]["multi_requirement_options"] = [
        {
            "id": "continue_current",
            "label": "Seguir con este mismo tema"
        },
        {
            "id": "go_next_requirement",
            "label": f"Pasar al siguiente requerimiento: {next_summary}"
        },
        {
            "id": "close_all",
            "label": "No hacer nada más, cerrar"
        }
    ]
    
    # ✅ Cuando hay 2+ requerimientos pendientes, SÍ poner needs_requirement_selection=True
    base_response["extra"]["needs_requirement_selection"] = True
    base_response["meta"]["extra"]["needs_requirement_selection"] = True
    base_response["meta"]["is_multi_req_confirmation"] = True
    base_response["meta"]["extra"]["is_multi_req_confirmation"] = True
    
    # También guardar en meta
    base_response["meta"]["extra"]["has_more_requirements"] = True
    base_response["meta"]["extra"]["next_requirement_id"] = next_req["id"]
    base_response["meta"]["extra"]["next_requirement_index"] = base_response["extra"]["next_requirement_index"]
    base_response["meta"]["extra"]["ui_next_step"] = "multi_requirement_menu"
    base_response["meta"]["extra"]["multi_requirement_options"] = base_response["extra"]["multi_requirement_options"]
    
    # Asegurar que stage y status permitan esperar la respuesta del usuario
    base_response["stage"] = ConversationStage.AWAIT_INTENT.value
    base_response["status"] = ConversationStatus.NEED_DETAILS.value
    
    # Asegurar que response y summary NO incluyan el texto del menú
    if base_response.get("message"):
        base_response["response"] = base_response["message"]
        base_response["summary"] = base_response["message"]
    
    return base_response


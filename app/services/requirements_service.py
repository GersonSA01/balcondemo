# app/services/requirements_service.py
"""
Servicio para gestión de requirements (requerimientos multi-intento).
Maneja la recuperación, propagación y finalización de requirements.
"""
from typing import Dict, List, Any, Optional, Tuple
from .chat_domain import Requirement


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
        base_response["close_chat"] = False
        return base_response
    
    # Hay más requerimientos pendientes → mostrar menú
    print(f"📋 [Finish Requirement] Hay {len(remaining)} requerimientos pendientes, preparando menú")
    next_req = remaining[0]
    next_summary = next_req.get("summary", "otro requerimiento")
    next_req_id = next_req.get("id", "N/A")
    
    # Verificar que el siguiente requerimiento NO sea el que acabamos de procesar
    if next_req_id == requirements[current_index].get("id"):
        if len(remaining) > 1:
            next_req = remaining[1]
            next_summary = next_req.get("summary", "otro requerimiento")
            next_req_id = next_req.get("id", "N/A")
            print(f"✅ [Finish Requirement] Corrigiendo: usando el siguiente requerimiento pendiente: {next_summary}")
    
    base_response["extra"]["has_more_requirements"] = True
    base_response["extra"]["next_requirement_id"] = next_req["id"]
    next_index_candidates = [i for i, r in enumerate(requirements) if r["id"] == next_req["id"]]
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
    
    # También guardar en meta
    base_response["meta"]["extra"]["has_more_requirements"] = True
    base_response["meta"]["extra"]["next_requirement_id"] = next_req["id"]
    base_response["meta"]["extra"]["next_requirement_index"] = base_response["extra"]["next_requirement_index"]
    base_response["meta"]["extra"]["ui_next_step"] = "multi_requirement_menu"
    base_response["meta"]["extra"]["multi_requirement_options"] = base_response["extra"]["multi_requirement_options"]
    
    # Asegurar que response y summary NO incluyan el texto del menú
    if base_response.get("message"):
        base_response["response"] = base_response["message"]
        base_response["summary"] = base_response["message"]
    
    return base_response


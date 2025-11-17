# app/services/chat_domain.py
"""
Dominio y contexto del chat.
Define las estructuras de datos centrales y la lógica de recuperación de contexto desde el historial.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .conversation_types import ConversationStage, ConversationMode, ConversationStatus
from .intent_parser import es_confirmacion_positiva, es_confirmacion_negativa


@dataclass
class Requirement:
    """Representa un requerimiento individual en una conversación multi-intento."""
    id: str
    summary: str
    slots: Dict[str, Any]
    answer_type: str = "informativo"  # "informativo" | "operativo"
    status: str = "pending"  # "pending" | "done"


@dataclass
class ChatContext:
    """
    Contexto completo de la conversación extraído del historial.
    Centraliza la recuperación de estado para evitar múltiples recorridos del historial.
    """
    stage: ConversationStage
    pending_slots: Optional[Dict[str, Any]]
    handoff_channel: Optional[str]
    requirements: List[Requirement] = field(default_factory=list)
    current_requirement_index: int = 0
    multi_req_active: bool = False
    
    @classmethod
    def from_history(cls, history: List[Dict]) -> "ChatContext":
        """
        Construye el contexto desde el historial de conversación.
        Hace UNA sola pasada por el historial para extraer todo.
        
        Args:
            history: Lista de mensajes del historial
            
        Returns:
            ChatContext con toda la información extraída
        """
        stage = ConversationStage.AWAIT_INTENT
        pending_slots = None
        handoff_channel = None
        requirements = []
        current_req_index = 0
        multi_req_active = False
        
        # Recorrer el historial de atrás hacia adelante (más reciente primero)
        for msg in reversed(history):
            role = msg.get("role") or msg.get("who")
            if role not in ("bot", "assistant"):
                continue
            
            # Extraer información del mensaje
            meta = msg.get("meta") or {}
            extra_from_meta = meta.get("extra") or {}
            extra_from_msg = msg.get("extra") or {}
            extra = extra_from_meta if extra_from_meta else extra_from_msg
            
            # Detectar stage
            needs_confirm = msg.get("needs_confirmation", False) or meta.get("needs_confirmation", False)
            confirmed_status = msg.get("confirmed") or meta.get("confirmed")
            slot_payload = msg.get("intent_slots") or meta.get("intent_slots")
            needs_related_selection = msg.get("needs_related_request_selection", False) or meta.get("needs_related_request_selection", False)
            needs_handoff_details = msg.get("needs_handoff_details", False) or meta.get("needs_handoff_details", False)
            handoff_sent_flag = msg.get("handoff_sent") or meta.get("handoff_sent")
            
            # Determinar stage basado en flags
            if handoff_sent_flag:
                stage = ConversationStage.AWAIT_INTENT
                pending_slots = None
                handoff_channel = None
                break
            
            if needs_handoff_details:
                stage = ConversationStage.AWAIT_HANDOFF_DETAILS
                if slot_payload:
                    pending_slots = slot_payload
                if not handoff_channel:
                    handoff_channel = msg.get("handoff_channel") or meta.get("handoff_channel")
                break
            
            if confirmed_status is False:
                stage = ConversationStage.AWAIT_INTENT
                pending_slots = None
                break
            
            if needs_related_selection:
                stage = ConversationStage.AWAIT_RELATED_REQUEST
                if slot_payload:
                    pending_slots = slot_payload
                break
            
            if slot_payload:
                pending_slots = slot_payload
                if needs_confirm:
                    stage = ConversationStage.AWAIT_CONFIRM
                break
            
            if needs_confirm:
                stage = ConversationStage.AWAIT_CONFIRM
                # Intentar recuperar slots desde mensaje anterior del usuario
                history_list = list(history)
                msg_index = len(history_list) - list(reversed(history)).index(msg) - 1
                if msg_index > 0:
                    prev_msg = history_list[msg_index - 1]
                    prev_text = prev_msg.get("content") or prev_msg.get("text", "")
                    if prev_text:
                        from .intent_parser import interpretar_intencion_principal
                        pending_slots = interpretar_intencion_principal(prev_text)
                break
            
            # Recuperar requirements
            if isinstance(extra, dict) and extra.get("requirements"):
                reqs = extra.get("requirements", [])
                if reqs and not requirements:  # Solo tomar el primero encontrado
                    requirements = [
                        Requirement(
                            id=r.get("id", f"req_{i}"),
                            summary=r.get("summary", ""),
                            slots=r.get("slots", {}),
                            answer_type=r.get("answer_type", "informativo"),
                            status=r.get("status", "pending")
                        )
                        for i, r in enumerate(reqs)
                    ]
                    current_req_index = extra.get("current_requirement_index", 0)
                    multi_req_active = extra.get("is_multi_req_confirmation", False) or len(requirements) > 1
                    break
        
        return cls(
            stage=stage,
            pending_slots=pending_slots,
            handoff_channel=handoff_channel,
            requirements=requirements,
            current_requirement_index=current_req_index,
            multi_req_active=multi_req_active
        )
    
    def is_new_intent(self, user_text: str) -> bool:
        """
        Determina si el mensaje del usuario es un nuevo intento.
        
        Args:
            user_text: Mensaje del usuario
            
        Returns:
            True si es un nuevo intento, False si es continuación del flujo actual
        """
        user_text_str = str(user_text) if user_text is not None else ""
        user_text_lower = user_text_str.lower().strip()
        
        # Verificar si el requerimiento anterior está completo
        if not self.is_requirement_complete():
            # Si hay un requerimiento activo, verificar si el mensaje es una continuación
            if es_confirmacion_positiva(user_text) or es_confirmacion_negativa(user_text):
                return False
            
            # No es nuevo si es respuesta a solicitudes relacionadas
            no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                                   "sin relacionar", "no hay solicitud relacionada"]
            if any(keyword in user_text_lower for keyword in no_related_keywords):
                return False
            
            # No es nuevo si contiene números (selección de solicitud relacionada)
            if any(str(i) in user_text_str for i in range(1, 10)):
                return False
            
            # Si el mensaje es muy largo (>50 caracteres) y el requerimiento anterior está completo,
            # probablemente es un nuevo intento
            if len(user_text_str) > 50:
                # Verificar si el último mensaje del bot fue una respuesta completa
                for req in self.requirements:
                    if req.status == "done":
                        return True
            
            return False
        
        # Si el requerimiento anterior está completo, este es un nuevo intento
        # (a menos que sea una confirmación o respuesta específica)
        if es_confirmacion_positiva(user_text) or es_confirmacion_negativa(user_text):
            return False
        
        no_related_keywords = ["no hay", "ninguna", "ninguna es relevante", "continuar sin relacionar", 
                               "sin relacionar", "no hay solicitud relacionada"]
        if any(keyword in user_text_lower for keyword in no_related_keywords):
            return False
        
        return True
    
    def is_requirement_complete(self) -> bool:
        """
        Determina si el requerimiento actual está completo.
        
        Returns:
            True si el requerimiento está completo, False si está en progreso
        """
        if not self.requirements:
            return True
        
        if self.current_requirement_index < len(self.requirements):
            current_req = self.requirements[self.current_requirement_index]
            return current_req.status == "done"
        
        return True
    
    def should_reset_context(self) -> bool:
        """
        Determina si debemos resetear el contexto de conversación.
        
        Returns:
            True si debemos resetear el contexto, False si debemos mantenerlo
        """
        if not self.is_requirement_complete():
            return False
        
        # Verificar si hay requerimientos pendientes
        pending = [r for r in self.requirements if r.status == "pending"]
        if pending:
            return False
        
        return True


# app/services/conversation_types.py
"""
Tipos y enums para el sistema de conversación.
Define los estados, modos y estados de la conversación de manera centralizada.
"""
from enum import Enum


class ConversationStage(str, Enum):
    """Estados posibles de la conversación."""
    GREETING = "greeting"
    AWAIT_INTENT = "await_intent"
    AWAIT_CONFIRM = "await_confirm"
    AWAIT_RELATED_REQUEST = "await_related_request"
    AWAIT_HANDOFF_DETAILS = "await_handoff_details"
    ANSWER_READY = "answer_ready"


class ConversationMode(str, Enum):
    """Modos de operación de la conversación."""
    INFORMATIVE = "informativo"
    OPERATIVE = "operativo"
    HANDOFF = "handoff"


class ConversationStatus(str, Enum):
    """Estados de la respuesta."""
    ANSWER = "answer"              # Ya tengo una respuesta lista para mostrar
    NEED_DETAILS = "need_details"  # Necesito que el usuario confirme, elija algo, etc.
    HANDOFF = "handoff"            # Derivación a humano
    ERROR = "error"                # Error técnico


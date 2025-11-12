# app/services/privategpt_client.py
"""
Cliente para comunicarse con PrivateGPT API.
PrivateGPT se ejecuta como servicio separado (Docker) y expone una API REST.
"""
import os
import requests
from typing import Dict, List, Any, Optional
from pathlib import Path
import json


def _load_privategpt_url() -> str:
    """Carga la URL de PrivateGPT desde variables de entorno o configuración."""
    url = os.getenv("PRIVATEGPT_API_URL")
    if not url:
        try:
            from django.conf import settings
            url = getattr(settings, "PRIVATEGPT_API_URL", None)
        except Exception:
            pass
    if not url:
        # URL por defecto (cuando se ejecuta con Docker)
        url = "http://localhost:8001"
    return url.rstrip("/")


# URL base de PrivateGPT API
PRIVATEGPT_API_URL = _load_privategpt_url()

# Timeout para requests (segundos)
REQUEST_TIMEOUT = 30


class PrivateGPTClient:
    """Cliente para interactuar con PrivateGPT API."""
    
    def __init__(self, base_url: str = None, timeout: int = None):
        """
        Inicializa el cliente.
        
        Args:
            base_url: URL base de PrivateGPT API (por defecto usa PRIVATEGPT_API_URL)
            timeout: Timeout para requests en segundos (por defecto REQUEST_TIMEOUT)
        """
        self.base_url = base_url or PRIVATEGPT_API_URL
        self.timeout = timeout or REQUEST_TIMEOUT
        self.session = requests.Session()
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica que la API de PrivateGPT esté funcionando.
        
        Returns:
            Dict con status de la API
        """
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "available": False
            }
    
    def is_available(self) -> bool:
        """Verifica si PrivateGPT está disponible."""
        health = self.health_check()
        return health.get("status") == "ok" or health.get("available", False)
    
    def ingest_file(self, file_path: str) -> Dict[str, Any]:
        """
        Ingestiona un archivo en PrivateGPT.
        
        Args:
            file_path: Ruta al archivo a ingestionar
        
        Returns:
            Dict con información del documento ingestionado
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f)}
                response = self.session.post(
                    f"{self.base_url}/v1/ingest/file",
                    files=files,
                    timeout=self.timeout * 2  # Más tiempo para archivos grandes
                )
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "success": False
            }
    
    def ingest_text(self, file_name: str, text: str) -> Dict[str, Any]:
        """
        Ingestiona texto directo en PrivateGPT.
        
        Args:
            file_name: Nombre del documento
            text: Contenido del documento
        
        Returns:
            Dict con información del documento ingestionado
        """
        try:
            data = {
                "file_name": file_name,
                "text": text
            }
            response = self.session.post(
                f"{self.base_url}/v1/ingest/text",
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "success": False
            }
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        use_context: bool = True,
        include_sources: bool = True,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Envía un mensaje al chat de PrivateGPT con contexto de documentos.
        
        Args:
            messages: Lista de mensajes en formato [{"role": "user", "content": "..."}]
            use_context: Si True, usa el contexto de documentos ingestionados
            include_sources: Si True, incluye fuentes en la respuesta
            stream: Si True, devuelve streaming (no implementado aún)
        
        Returns:
            Dict con la respuesta del chat
        """
        try:
            # Validar formato de mensajes
            if not messages:
                return {
                    "error": "La lista de mensajes está vacía",
                    "success": False
                }
            
            # Filtrar mensajes del sistema (PrivateGPT puede no soportarlos en algunos casos)
            filtered_messages = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                # Si es mensaje de sistema, convertirlo a user con contexto
                if role == "system":
                    # Agregar el contexto del sistema al primer mensaje del usuario
                    if filtered_messages and filtered_messages[0].get("role") == "user":
                        filtered_messages[0]["content"] = f"[Contexto: {content}] {filtered_messages[0]['content']}"
                    else:
                        # Si no hay mensaje de usuario aún, crear uno
                        filtered_messages.append({
                            "role": "user",
                            "content": content
                        })
                elif role in ("user", "assistant") and content:
                    filtered_messages.append({
                        "role": role,
                        "content": str(content)
                    })
            
            if not filtered_messages:
                return {
                    "error": "No hay mensajes válidos después del filtrado",
                    "success": False
                }
            
            data = {
                "messages": filtered_messages,
                "use_context": use_context,
                "include_sources": include_sources,
                "stream": stream
            }
            
            response = self.session.post(
                f"{self.base_url}/v1/chat/completions",
                json=data,
                timeout=self.timeout * 2  # Más tiempo para respuestas del LLM
            )
            
            # Capturar detalles del error si hay
            if response.status_code != 200:
                error_detail = ""
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", str(error_json))
                except:
                    error_detail = response.text[:500]  # Primeros 500 caracteres
                
                return {
                    "error": f"{response.status_code} {response.reason}: {error_detail}",
                    "success": False,
                    "status_code": response.status_code
                }
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            return {
                "error": f"Timeout esperando respuesta de PrivateGPT (más de {self.timeout * 2}s)",
                "success": False
            }
        except requests.exceptions.ConnectionError:
            return {
                "error": f"No se pudo conectar con PrivateGPT en {self.base_url}. Verifica que el servicio esté ejecutándose.",
                "success": False
            }
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            # Intentar extraer más detalles del error
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_json = e.response.json()
                    error_detail = error_json.get("detail", str(error_json))
                    error_msg = f"{error_msg}: {error_detail}"
                except:
                    error_msg = f"{error_msg}: {e.response.text[:500]}"
            
            return {
                "error": error_msg,
                "success": False
            }
    
    def get_chunks(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Obtiene chunks relevantes para una query.
        
        Args:
            query: Texto de búsqueda
            limit: Número máximo de chunks a devolver
        
        Returns:
            Dict con chunks relevantes
        """
        try:
            data = {
                "text": query,
                "limit": limit
            }
            response = self.session.post(
                f"{self.base_url}/v1/chunks",
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "success": False
            }
    
    def list_documents(self) -> Dict[str, Any]:
        """
        Lista todos los documentos ingestionados.
        
        Returns:
            Dict con lista de documentos
        """
        try:
            response = self.session.get(
                f"{self.base_url}/v1/ingest/list",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "error": str(e),
                "success": False
            }
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Elimina un documento por ID.
        
        Args:
            doc_id: ID del documento a eliminar
        
        Returns:
            True si se eliminó correctamente, False en caso contrario
        """
        try:
            response = self.session.delete(
                f"{self.base_url}/v1/ingest/{doc_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False


# Instancia global del cliente
_global_client = None


def get_privategpt_client() -> PrivateGPTClient:
    """Obtiene la instancia global del cliente PrivateGPT."""
    global _global_client
    if _global_client is None:
        _global_client = PrivateGPTClient()
    return _global_client


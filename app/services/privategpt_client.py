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
        url = "http://localhost:8001"  # Volver a 8001 hasta que PrivateGPT se reinicie en 8002
    
    final_url = url.rstrip("/")
    return final_url


# URL base de PrivateGPT API
PRIVATEGPT_API_URL = _load_privategpt_url()

# Timeout para requests (segundos)
REQUEST_TIMEOUT = 30  # Aumentado a 30 segundos para respuestas del LLM
HEALTH_CHECK_TIMEOUT = 5  # Timeout para health check (aumentado para dar más tiempo)


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
        print(f"🔗 [PrivateGPT Client] Inicializado con URL: {self.base_url}, timeout: {self.timeout}s")
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica que la API de PrivateGPT esté funcionando.
        
        Returns:
            Dict con status de la API
        """
        try:
            # Usar timeout más corto para health check
            # Hacer petición directa sin Session para evitar conexiones bloqueadas
            response = requests.get(
                f"{self.base_url}/health",
                timeout=HEALTH_CHECK_TIMEOUT,
                headers={"Connection": "close"}  # Forzar cierre de conexión
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            print(f"⏱️ [PrivateGPT Health] Timeout después de {HEALTH_CHECK_TIMEOUT}s")
            return {
                "status": "error",
                "error": f"Timeout después de {HEALTH_CHECK_TIMEOUT}s",
                "available": False
            }
        except requests.exceptions.RequestException as e:
            print(f"❌ [PrivateGPT Health] Error: {str(e)}")
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
                response = requests.post(
                    f"{self.base_url}/v1/ingest/file",
                    files=files,
                    timeout=self.timeout * 2,  # Más tiempo para archivos grandes
                    headers={"Connection": "close"}
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
            response = requests.post(
                f"{self.base_url}/v1/ingest/text",
                json=data,
                timeout=self.timeout,
                headers={"Connection": "close"}
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
        stream: bool = False,
        session_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Envía un mensaje al chat de PrivateGPT con contexto de documentos.
        
        Args:
            messages: Lista de mensajes en formato [{"role": "user", "content": "..."}]
            use_context: Si True, usa el contexto de documentos ingestionados
            include_sources: Si True, incluye fuentes en la respuesta
            stream: Si True, devuelve streaming (no implementado aún)
            session_context: Contexto estructurado de la sesión (usuario, perfil, etc.)
        
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
            
            # Procesar mensajes manteniendo el contexto de sistema si existe
            filtered_messages = []
            system_context = None
            
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                
                if role == "system":
                    # Guardar contexto del sistema para agregarlo al primer mensaje del usuario
                    system_context = content
                elif role in ("user", "assistant") and content:
                    # Si hay contexto de sistema y es el primer mensaje de usuario, agregarlo
                    if system_context and role == "user" and not filtered_messages:
                        filtered_messages.append({
                            "role": "user",
                            "content": f"[Contexto del sistema: {system_context}]\n\n{str(content)}"
                        })
                        system_context = None  # Ya usado
                    else:
                        filtered_messages.append({
                            "role": role,
                            "content": str(content)
                        })
            
            # Si quedó contexto de sistema sin usar, agregarlo al primer mensaje
            if system_context and filtered_messages:
                first_msg = filtered_messages[0]
                if first_msg.get("role") == "user":
                    first_msg["content"] = f"[Contexto del sistema: {system_context}]\n\n{first_msg['content']}"
            
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
            if session_context:
                data["session_context"] = session_context
            
            endpoint_url = f"{self.base_url}/v1/chat/completions"
            print(f"📤 [PrivateGPT] Haciendo POST a: {endpoint_url}")
            print(f"   Payload: {json.dumps(data, indent=2, default=str)[:500]}...")
            # Para chat completions, usar timeout más largo (60 segundos)
            # ya que el LLM puede tardar en procesar y generar respuesta
            chat_timeout = 60
            print(f"   Timeout configurado: {chat_timeout}s (aumentado para respuestas del LLM)")
            print(f"   Timestamp antes de petición: {__import__('time').time()}")
            
            # Hacer la petición con timeout
            # NO usar self.session para evitar conexiones bloqueadas
            # Hacer petición directa con requests.post
            # Cerrar explícitamente la conexión después de usar la respuesta
            try:
                print(f"   ⏳ Iniciando petición POST...")
                print(f"   Usando conexión nueva (no persistente)...")
                response = requests.post(
                    endpoint_url,
                    json=data,
                    timeout=chat_timeout,  # 60 segundos para respuestas del LLM
                    headers={
                        "Content-Type": "application/json",
                        "Connection": "close"  # Forzar cierre de conexión después de la petición
                    }
                )
                print(f"   ✅ Petición completada")
                print(f"📥 [PrivateGPT] Respuesta recibida - Status: {response.status_code}")
                print(f"   Headers recibidos: {dict(response.headers)}")
                
                try:
                    # Capturar detalles del error si hay
                    if response.status_code != 200:
                        error_detail = ""
                        try:
                            error_json = response.json()
                            error_detail = error_json.get("detail", str(error_json))
                        except:
                            error_detail = response.text[:500]  # Primeros 500 caracteres
                        
                        result = {
                            "error": f"{response.status_code} {response.reason}: {error_detail}",
                            "success": False,
                            "status_code": response.status_code
                        }
                        return result
                    
                    response.raise_for_status()
                    result = response.json()
                    return result
                finally:
                    # Cerrar explícitamente la conexión para evitar acumulación
                    response.close()
            except requests.exceptions.Timeout as e:
                print(f"   ❌ TIMEOUT: La petición excedió {chat_timeout}s")
                print(f"   Error: {str(e)}")
                print(f"   Esto puede indicar que PrivateGPT está procesando pero tarda mucho, o está bloqueado")
                raise
            except Exception as e:
                print(f"   ❌ ERROR en petición POST: {type(e).__name__}: {str(e)}")
                raise
        except requests.exceptions.Timeout:
            return {
                "error": f"Timeout esperando respuesta de PrivateGPT (más de 60s). El servidor puede estar procesando pero tarda mucho, o está bloqueado.",
                "success": False
            }
        except requests.exceptions.ConnectionError as e:
            print(f"❌ [PrivateGPT] Error de conexión: {str(e)}")
            print(f"   URL intentada: {self.base_url}/v1/chat/completions")
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
            response = requests.post(
                f"{self.base_url}/v1/chunks",
                json=data,
                timeout=self.timeout,
                headers={"Connection": "close"}
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
            response = requests.get(
                f"{self.base_url}/v1/ingest/list",
                timeout=self.timeout,
                headers={"Connection": "close"}
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
            response = requests.delete(
                f"{self.base_url}/v1/ingest/{doc_id}",
                timeout=self.timeout,
                headers={"Connection": "close"}
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


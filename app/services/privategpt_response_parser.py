# app/services/privategpt_response_parser.py
"""
Parser para respuestas de PrivateGPT API.
Maneja múltiples formatos de respuesta y extrae información de manera consistente.
"""
from typing import Dict, List, Any, Optional
import json


class PrivateGPTResponseParser:
    """Parsea respuestas de PrivateGPT independientemente del formato."""
    
    # Patrones de disculpa/negativa para detectar respuestas sin información útil
    DISCULPA_PATTERNS = [
        "no tengo información",
        "no encuentro información",
        "no puedo ayudarte",
        "no puedo proporcionar",
        "no está disponible",
        "no se encuentra",
        "no hay información",
        "no dispongo de",
        "no tengo acceso",
        "no puedo acceder",
        "no puedo consultar",
        "te sugiero que te pongas en contacto",
        "contacta directamente",
        "ponte en contacto",
        "contacta al",
        "debes contactar",
        "deberías contactar",
        "lo siento, no",
        "disculpa, no",
        "perdón, no",
        "no puedo darte",
        "no puedo ofrecerte",
        "no puedo brindarte",
        "lamentablemente no encontré",
        "no pude localizar",
        "no pude encontrar",
        "no encontré información específica",
        "no localicé",
        "no pude ubicar",
        "no está disponible en los documentos",
        "no se encuentra en los documentos",
    ]
    
    @staticmethod
    def parse(response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parsea respuesta de PrivateGPT y normaliza el formato.
        
        Args:
            response: Respuesta raw de PrivateGPT API
        
        Returns:
            Dict normalizado con keys: has_information, response, fuentes
        """
        # Formato nuevo: ya viene normalizado
        if "response" in response and "has_information" in response:
            return {
                "has_information": response.get("has_information", False),
                "response": response.get("response", ""),
                "fuentes": response.get("fuentes", [])
            }
        
        # Formato chat completions estándar
        if "choices" in response:
            return PrivateGPTResponseParser._parse_chat_completions_format(response)
        
        # Formato legacy o desconocido
        return PrivateGPTResponseParser._parse_legacy_format(response)
    
    @staticmethod
    def _parse_chat_completions_format(response: Dict[str, Any]) -> Dict[str, Any]:
        """Parsea formato estándar de chat completions."""
        choices = response.get("choices", [])
        if not choices:
            return {
                "has_information": False,
                "response": "No pude procesar tu solicitud.",
                "fuentes": []
            }
        
        choice = choices[0]
        message = choice.get("message", {})
        content_raw = message.get("content", "") if isinstance(message, dict) else ""
        
        # Intentar parsear content como JSON y extraer response y has_information
        parsed_content = PrivateGPTResponseParser._extract_response_and_has_info(content_raw)
        response_text = parsed_content.get("response", "")
        has_information_from_json = parsed_content.get("has_information")
        
        # Extraer fuentes desde todas las ubicaciones posibles
        fuentes = PrivateGPTResponseParser._extract_sources(response, choice, message)
        
        # Determinar si hay información usando solo heurísticas (sin LLM):
        # 1. Si viene has_information del JSON, validarlo con heurísticas
        # 2. Si no viene, usar heurísticas directamente
        if has_information_from_json is not None:
            # Validar que si viene true, realmente haya información útil usando solo heurísticas
            has_information = PrivateGPTResponseParser._validate_has_information(
                has_information_from_json, response_text, fuentes
            )
        else:
            # No viene en JSON, usar heurísticas
            has_information = PrivateGPTResponseParser._determine_has_information(
                response_text, fuentes
            )
        
        return {
            "has_information": has_information,
            "response": response_text or "No pude procesar tu solicitud.",
            "fuentes": fuentes
        }
    
    @staticmethod
    def _extract_response_and_has_info(content_raw: str) -> Dict[str, Any]:
        """
        Extrae response y has_information desde content (puede ser JSON o texto plano).
        
        Returns:
            Dict con keys: response (str), has_information (bool|None)
        """
        if not content_raw:
            return {"response": "", "has_information": None}
        
        # Intentar parsear como JSON
        if isinstance(content_raw, str) and content_raw.strip().startswith("{"):
            try:
                content_parsed = json.loads(content_raw)
                if isinstance(content_parsed, dict):
                    return {
                        "response": content_parsed.get("response", content_raw),
                        "has_information": content_parsed.get("has_information") if "has_information" in content_parsed else None
                    }
            except (json.JSONDecodeError, ValueError):
                pass
        
        return {"response": content_raw, "has_information": None}
    
    @staticmethod
    def _extract_response_text(content_raw: str) -> str:
        """Extrae texto de respuesta desde content (puede ser JSON o texto plano)."""
        parsed = PrivateGPTResponseParser._extract_response_and_has_info(content_raw)
        return parsed.get("response", "")
    
    @staticmethod
    def _extract_sources(
        response: Dict[str, Any],
        choice: Dict[str, Any],
        message: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Extrae fuentes desde todas las ubicaciones posibles."""
        fuentes = []
        
        # 1. En el nivel de response
        if "sources" in response:
            fuentes.extend(PrivateGPTResponseParser._parse_sources_list(
                response.get("sources", [])
            ))
        
        # 2. En choice[0]
        if "sources" in choice:
            fuentes.extend(PrivateGPTResponseParser._parse_sources_list(
                choice.get("sources", [])
            ))
        
        # 3. En message
        if isinstance(message, dict) and "sources" in message:
            fuentes.extend(PrivateGPTResponseParser._parse_sources_list(
                message.get("sources", [])
            ))
        
        # 4. En context.citations
        if "context" in choice:
            context = choice.get("context", {})
            if isinstance(context, dict) and "citations" in context:
                fuentes.extend(PrivateGPTResponseParser._parse_sources_list(
                    context.get("citations", [])
                ))
        
        return fuentes
    
    @staticmethod
    def _parse_sources_list(sources_raw: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Parsea lista de fuentes raw a formato normalizado."""
        fuentes = []
        for source in sources_raw:
            if not isinstance(source, dict):
                continue
            
            archivo = ""
            pagina = ""
            
            # Formato 1: source.document.doc_metadata.file_name
            if "document" in source:
                doc = source.get("document", {})
                if "doc_metadata" in doc:
                    metadata = doc.get("doc_metadata", {})
                    archivo = metadata.get("file_name", "")
                    pagina = str(metadata.get("page_label", metadata.get("page", "")))
            
            # Formato 2: source.file_name directamente
            if not archivo:
                archivo = source.get("file_name", source.get("document_name", ""))
            if not pagina:
                pagina = str(source.get("page", source.get("page_number", "")))
            
            if archivo:
                fuentes.append({
                    "archivo": archivo,
                    "pagina": pagina
                })
        
        return fuentes
    
    @staticmethod
    def _validate_has_information(
        has_information_from_json: bool,
        response_text: str,
        fuentes: List[Dict]
    ) -> bool:
        """
        Valida has_information usando solo heurísticas, sin hacer nuevas llamadas a PrivateGPT.

        Estrategia:
        - Si el JSON dice has_information = False → devolver False directo.
        - Si el JSON dice True:
          - Rechazar si parece una disculpa/negativa.
          - Rechazar si es demasiado corta.
          - Aceptar si hay fuentes y no es una disculpa.
          - Si no hay fuentes, exigir longitud mínima sustancial.
        """
        if not has_information_from_json:
            return False

        if not response_text:
            return False

        return PrivateGPTResponseParser._fallback_validate_has_info(
            response_text, fuentes
        )
    
    @staticmethod
    def _fallback_validate_has_info(
        response_text: str,
        fuentes: List[Dict]
    ) -> bool:
        """
        Fallback heurístico cuando no se puede usar el LLM para validar.
        Usa estructura básica: longitud, presencia de fuentes, y detección de disculpas.
        """
        response_clean = response_text.strip().lower()
        response_length = len(response_clean)
        
        # Si la respuesta contiene patrones de disculpa, retornar False
        for pattern in PrivateGPTResponseParser.DISCULPA_PATTERNS:
            if pattern in response_clean:
                print(f"⚠️ [Parser] Fallback detectó disculpa: '{pattern}' → has_information=False")
                return False
        
        # Con fuentes válidas, asumir que hay información (si no es disculpa)
        if fuentes:
            return response_length >= 50
        
        # Sin fuentes pero respuesta sustancial
        return response_length >= 100
    
    @staticmethod
    def _determine_has_information(response_text: str, fuentes: List[Dict]) -> bool:
        """
        Determina si la respuesta contiene información útil usando heurísticas básicas.
        
        Se usa cuando private-gpt NO retornó has_information en el JSON.
        En este caso, el modelo no siguió el formato JSON esperado, así que usamos
        heurísticas simples basadas en estructura (longitud, presencia de fuentes).
        
        Estrategia basada en estructura:
        1. Si no hay respuesta → no hay información
        2. Detectar disculpas/negativas → no hay información
        3. Si hay fuentes → probablemente hay información útil (si no es disculpa)
        4. Si no hay fuentes pero respuesta sustancial → puede haber información
        """
        if not response_text:
            return False
        
        response_clean = response_text.strip().lower()
        response_length = len(response_clean)
        
        # Respuestas muy cortas probablemente no tienen información útil
        if response_length < 30:
            return False
        
        # Si la respuesta contiene patrones de disculpa, retornar False
        for pattern in PrivateGPTResponseParser.DISCULPA_PATTERNS:
            if pattern in response_clean:
                print(f"⚠️ [Parser] Detectó disculpa en respuesta sin has_information: '{pattern}' → has_information=False")
                return False
        
        # Si hay fuentes, es muy probable que haya información útil
        # PrivateGPT solo retorna fuentes cuando encuentra información relevante en documentos
        if fuentes:
            # Con fuentes, aceptar si la respuesta tiene contenido mínimo
            if response_length >= 50:
                return True
            # Con fuentes pero respuesta muy corta, puede ser información válida pero concisa
            return True
        
        # Sin fuentes pero respuesta sustancial (>= 150 chars)
        # Puede ser información general válida aunque no tenga fuentes explícitas
        if response_length >= 150:
            return True
        
        # Sin fuentes y respuesta corta: probablemente no hay información útil
        return False
    
    @staticmethod
    def _parse_legacy_format(response: Dict[str, Any]) -> Dict[str, Any]:
        """Parsea formato legacy o desconocido."""
        return {
            "has_information": False,
            "response": str(response.get("error", "Formato de respuesta desconocido")),
            "fuentes": []
        }


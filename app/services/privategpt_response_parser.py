# app/services/privategpt_response_parser.py
"""
Parser para respuestas de PrivateGPT API.
Maneja múltiples formatos de respuesta y extrae información de manera consistente.

Ahora confía principalmente en PrivateGPT para la decisión de has_information,
solo aplicando heurísticas suaves como backup cuando no se puede parsear el JSON.
"""
from typing import Dict, List, Any, Optional
import json
import re
import logging

logger = logging.getLogger(__name__)


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
        
        Ahora confía principalmente en PrivateGPT para has_information,
        solo aplicando validación suave como backup.
        
        Args:
            response: Respuesta raw de PrivateGPT API
        
        Returns:
            Dict normalizado con keys:
            - has_information_pgpt: lo que decidió PrivateGPT
            - has_information: versión final (solo ligeramente suavizada)
            - response: texto de respuesta
            - fuentes: lista de fuentes
        """
        # Formato nuevo: ya viene normalizado
        if "response" in response and "has_information" in response:
            has_info_pgpt = response.get("has_information", False)
            return {
                "has_information_pgpt": has_info_pgpt,
                "has_information": has_info_pgpt,  # Confiar en PrivateGPT
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
        """
        Parsea formato estándar de chat completions.
        
        Ahora confía principalmente en PrivateGPT para has_information,
        solo aplicando validación suave como backup.
        """
        logger.debug("Parseando respuesta de PrivateGPT (formato chat completions)")
        
        choices = response.get("choices", [])
        if not choices:
            logger.warning("No hay choices en la respuesta de PrivateGPT")
            return {
                "has_information_pgpt": False,
                "has_information": False,
                "response": "No pude procesar tu solicitud.",
                "fuentes": []
            }
        
        choice = choices[0]
        message = choice.get("message", {})
        content_raw = message.get("content", "") if isinstance(message, dict) else ""
        
        # Intentar parsear content como JSON (PrivateGPT ahora SIEMPRE retorna JSON)
        parsed_content = PrivateGPTResponseParser._extract_response_and_has_info(content_raw)
        response_text = parsed_content.get("response", "")
        has_info_pgpt = parsed_content.get("has_information")
        
        # Extraer fuentes desde todas las ubicaciones posibles
        fuentes = PrivateGPTResponseParser._extract_sources(response, choice, message)
        
        # Decisión final: confiar en PrivateGPT si viene explícito
        has_info_final = bool(has_info_pgpt) if has_info_pgpt is not None else None
        
        # Solo aplicar validación suave si no tenemos decisión de PrivateGPT
        if has_info_final is None:
            # Heurística mínima solo si no viene JSON
            lowered = response_text.lower()
            if any(pattern in lowered for pattern in ["no tengo información", "no encontré información"]):
                has_info_final = False
            elif len(response_text.strip()) < 40:
                has_info_final = False
            else:
                has_info_final = True
        else:
            # Validación suave: si PrivateGPT dice True pero la respuesta es muy corta, corregir
            if has_info_final and len(response_text.strip()) < 20:
                logger.warning(
                    "BalconDemo corrigiendo has_information: PrivateGPT dijo True pero respuesta muy corta",
                    extra={
                        "has_info_pgpt": has_info_pgpt,
                        "response_length": len(response_text.strip())
                    }
                )
                has_info_final = False
        
        # Log comparativo
        if has_info_pgpt is not None and has_info_pgpt != has_info_final:
            logger.warning(
                "Diferencia en has_information (PGPT vs Final)",
                extra={
                    "has_info_pgpt": has_info_pgpt,
                    "has_info_final": has_info_final,
                    "response_preview": response_text[:200]
                }
            )
        else:
            logger.info(
                "BalconDemo has_information pipeline",
                extra={
                    "has_info_pgpt": has_info_pgpt,
                    "has_info_final": has_info_final
                }
            )
        
        return {
            "has_information_pgpt": bool(has_info_pgpt) if has_info_pgpt is not None else None,
            "has_information": has_info_final,
            "response": response_text or "No pude procesar tu solicitud.",
            "fuentes": fuentes
        }
    
    @staticmethod
    def _extract_response_and_has_info(content_raw: str) -> Dict[str, Any]:
        """
        Extrae response y has_information desde content (puede ser JSON o texto plano).
        
        Maneja múltiples formatos:
        1. JSON válido: {"has_information": false, "response": "..."}
        2. Texto plano con has_information al inicio: "has_information: false\n..."
        3. Texto plano sin has_information
        
        Returns:
            Dict con keys: response (str), has_information (bool|None)
        """
        if not content_raw:
            return {"response": "", "has_information": None}
        
        content_raw = content_raw.strip()
        
        # 1. Intentar parsear como JSON completo
        if content_raw.startswith("{"):
            try:
                content_parsed = json.loads(content_raw)
                if isinstance(content_parsed, dict):
                    return {
                        "response": content_parsed.get("response", content_raw),
                        "has_information": content_parsed.get("has_information") if "has_information" in content_parsed else None
                    }
            except (json.JSONDecodeError, ValueError):
                pass
        
        # 2. Intentar extraer JSON parcial (buscar { ... } en cualquier parte del texto)
        json_match = re.search(r'\{[^{}]*"has_information"[^{}]*\}', content_raw)
        if json_match:
            try:
                json_str = json_match.group(0)
                content_parsed = json.loads(json_str)
                if isinstance(content_parsed, dict) and "has_information" in content_parsed:
                    # Extraer el resto del texto como response si no está en el JSON
                    response_text = content_parsed.get("response", "")
                    if not response_text:
                        # Si no hay response en el JSON, usar el texto después del JSON
                        json_end = json_match.end()
                        response_text = content_raw[json_end:].strip()
                    return {
                        "response": response_text or content_raw,
                        "has_information": content_parsed.get("has_information")
                    }
            except (json.JSONDecodeError, ValueError):
                pass
        
        # 3. Detectar patrón "has_information: false" o "has_information=false" en texto plano
        # Patrones: "has_information: false", "has_information=false", "has_information = false"
        has_info_patterns = [
            r'has_information\s*:\s*(true|false)',
            r'has_information\s*=\s*(true|false)',
            r'"has_information"\s*:\s*(true|false)',
            r'"has_information"\s*=\s*(true|false)',
        ]
        
        print(f"🔍 [Parser] Buscando patrones has_information en texto (longitud: {len(content_raw)} chars)")
        print(f"   Primeros 200 chars: {content_raw[:200]}")
        
        for pattern in has_info_patterns:
            match = re.search(pattern, content_raw, re.IGNORECASE)
            if match:
                value_str = match.group(1).lower()
                has_information = value_str in ["true", "1", "yes", "sí", "si"]
                
                print(f"✅ [Parser] Detectado patrón '{pattern}': valor='{value_str}' → has_information={has_information}")
                
                # Extraer el texto después de has_information como response
                # Buscar el final de la línea que contiene has_information
                match_end = match.end()
                # Buscar el siguiente salto de línea o el final del texto
                next_newline = content_raw.find('\n', match_end)
                if next_newline != -1:
                    response_text = content_raw[next_newline:].strip()
                else:
                    # Si no hay salto de línea, buscar desde el final del match
                    response_text = content_raw[match_end:].strip()
                    # Limpiar si empieza con ":" o "="
                    response_text = re.sub(r'^[:=]\s*', '', response_text).strip()
                
                # Si el response_text está vacío o es muy corto, usar todo el texto original
                if not response_text or len(response_text) < 10:
                    response_text = content_raw
                
                print(f"   Response extraído (primeros 200): {response_text[:200]}...")
                
                return {
                    "response": response_text,
                    "has_information": has_information
                }
        
        print(f"⚠️ [Parser] No se encontró patrón has_information explícito en el texto")
        
        # 4. No se encontró has_information explícito
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
            "has_information_pgpt": None,
            "has_information": False,
            "response": str(response.get("error", "Formato de respuesta desconocido")),
            "fuentes": []
        }


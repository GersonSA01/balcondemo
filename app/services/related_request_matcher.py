# app/services/related_request_matcher.py
"""
Servicio para encontrar solicitudes relacionadas usando LLM.
Compara la solicitud del usuario con las solicitudes existentes en data_estudiante.json
"""
from typing import Dict, List, Any, Optional
import json
from pathlib import Path
from .config import llm
from .config import guarded_invoke, ALLOW_RELATED_LLM

def load_student_requests(student_data: Dict = None) -> List[Dict]:
    """
    Carga las solicitudes del estudiante desde student_data.
    
    Args:
        student_data: Datos del estudiante que incluyen solicitudes
    
    Returns:
        Lista de solicitudes del estudiante
    """
    if not student_data:
        return []
    
    # Nuevo esquema principal
    solicitudes = student_data.get("solicitudes", [])
    # Compatibilidad hacia atrás
    if not solicitudes:
        solicitudes = student_data.get("solicitudes_balcon", [])
    return solicitudes if isinstance(solicitudes, list) else []


def format_request_for_llm(solicitud: Dict) -> str:
    """
    Formatea una solicitud para ser enviada al LLM.
    
    Args:
        solicitud: Diccionario con la solicitud
    
    Returns:
        String formateado con la información de la solicitud
    """
    parts = []

    parts.append(f"ID: {solicitud.get('id', 'N/A')}")
    parts.append(f"Código: {solicitud.get('codigo', 'N/A')}")
    parts.append(f"Estado: {solicitud.get('estado', 'N/A')}")
    parts.append(f"Tipo: {solicitud.get('tipo', 'N/A')}")
    if solicitud.get('fecha_creacion'):
        parts.append(f"Fecha creación: {solicitud.get('fecha_creacion')}")
    if solicitud.get('descripcion'):
        parts.append(f"Descripción: {solicitud.get('descripcion')}")

    return "\n".join(parts)


def find_related_requests(
    user_request: str,
    intent_slots: Dict[str, Any],
    student_data: Dict = None,
    max_results: int = 3
) -> Dict[str, Any]:
    """
    Encuentra solicitudes relacionadas usando LLM.
    
    Args:
        user_request: Texto de la solicitud del usuario
        intent_slots: Slots de intención extraídos del mensaje
        student_data: Datos del estudiante (incluye solicitudes_balcon)
        max_results: Número máximo de solicitudes relacionadas a retornar
    
    Returns:
        Dict con:
        - related_requests: Lista de solicitudes relacionadas (máximo max_results)
        - no_related: True si no hay solicitudes relacionadas
        - reasoning: Razonamiento del LLM
    """
    # Cargar solicitudes del estudiante
    solicitudes = load_student_requests(student_data)
    
    if not solicitudes:
        return {
            "related_requests": [],
            "no_related": True,
            "reasoning": "No hay solicitudes previas del estudiante"
        }
    
    # Si no se permite LLM para related, usar método local
    if not ALLOW_RELATED_LLM:
        return _find_related_local(user_request, solicitudes, max_results)

    # Formatear todas las solicitudes para el LLM
    formatted_requests = []
    for sol in solicitudes:
        formatted_requests.append({
            "id": sol.get("id"),
            "formatted": format_request_for_llm(sol),
            "original": sol
        })
    
    # Construir prompt para el LLM
    intent_summary = intent_slots.get("intent_short", user_request)
    
    prompt = f"""Eres un asistente que ayuda a identificar solicitudes relacionadas en un sistema de gestión estudiantil.

SOLICITUD ACTUAL DEL USUARIO:
{user_request}

RESUMEN DE INTENCIÓN:
{intent_summary}

SOLICITUDES PREVIAS DEL ESTUDIANTE:
{chr(10).join([f"{i+1}. {req['formatted']}" for i, req in enumerate(formatted_requests)])}

INSTRUCCIONES:
1. Analiza la solicitud actual del usuario y compárala con las solicitudes previas.
2. Identifica si alguna solicitud previa está RELACIONADA con la solicitud actual.
3. Dos solicitudes están relacionadas si:
   - Comparten contexto (ej: citas médicas, justificaciones, asuntos académicos)
   - La nueva solicitud es continuación o seguimiento de una previa
   - Están relacionadas temáticamente por su descripción

4. Retorna SOLO las solicitudes que tengan relación significativa (no todas).
5. Si NO hay solicitudes relacionadas, retorna una lista vacía.

FORMATO DE RESPUESTA (JSON):
{{
    "related_request_ids": [210107, 199980],
    "reasoning": "Breve explicación de por qué estas solicitudes están relacionadas",
    "no_related": false
}}

Si no hay solicitudes relacionadas:
{{
    "related_request_ids": [],
    "reasoning": "No se encontraron solicitudes relacionadas",
    "no_related": true
}}
"""
    
    try:
        # Llamar al LLM
        response = guarded_invoke(llm, prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Extraer JSON de la respuesta
        # El LLM puede devolver texto con JSON, necesitamos extraerlo
        import re
        json_match = re.search(r'\{[^{}]*"related_request_ids"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # Intentar parsear toda la respuesta como JSON
            json_str = response_text.strip()
            # Limpiar markdown si existe
            if json_str.startswith("```"):
                json_str = re.sub(r'^```(?:json)?\s*', '', json_str, flags=re.MULTILINE)
                json_str = re.sub(r'\s*```\s*$', '', json_str, flags=re.MULTILINE)
        
        result = json.loads(json_str)
        
        # Obtener las solicitudes relacionadas
        related_ids = result.get("related_request_ids", [])
        reasoning = result.get("reasoning", "Sin razonamiento")
        no_related = result.get("no_related", len(related_ids) == 0)
        
        # Filtrar y formatear solicitudes relacionadas
        related_requests = []
        for req_info in formatted_requests:
            if req_info["id"] in related_ids:
                related_requests.append({
                    "id": req_info["id"],
                    "codigo": req_info["original"].get("codigo", ""),
                    "estado": req_info["original"].get("estado", ""),
                    "tipo": req_info["original"].get("tipo", ""),
                    "fecha_creacion": req_info["original"].get("fecha_creacion", ""),
                    "descripcion": req_info["original"].get("descripcion", ""),
                    "display": _generate_request_display(req_info["original"])
                })
        
        # Limitar a max_results
        related_requests = related_requests[:max_results]
        
        return {
            "related_requests": related_requests,
            "no_related": no_related,
            "reasoning": reasoning
        }
        
    except Exception as e:
        print(f"⚠️ Error al buscar solicitudes relacionadas: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: retornar que no hay solicitudes relacionadas
        return {
            "related_requests": [],
            "no_related": True,
            "reasoning": f"Error al procesar: {str(e)}"
        }


def _generate_request_display(solicitud: Dict) -> str:
    """
    Genera un texto descriptivo para mostrar la solicitud al usuario.
    
    Args:
        solicitud: Diccionario con la solicitud
    
    Returns:
        String descriptivo de la solicitud
    """
    tipo = solicitud.get("tipo", "SOLICITUD")
    estado = solicitud.get("estado", "PENDIENTE")
    fecha = solicitud.get("fecha_creacion", "")
    codigo = solicitud.get("codigo", "")
    descripcion = solicitud.get("descripcion", "")

    # Formatear fecha si existe (acepta "YYYY-MM-DD HH:MM:SS" o ISO)
    fecha_display = ""
    if fecha:
        try:
            from datetime import datetime
            # Intentar formato "YYYY-MM-DD HH:MM:SS"
            try:
                dt = datetime.strptime(fecha, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Intentar ISO con o sin Z
                dt = datetime.fromisoformat(fecha.replace("Z", "+00:00"))
            fecha_display = dt.strftime("%d/%m/%Y")
        except Exception:
            fecha_display = fecha[:10] if len(fecha) >= 10 else fecha

    base = f"{tipo.title()} ({estado})"
    if fecha_display:
        base += f" - {fecha_display}"
    if codigo:
        base += f" - {codigo}"
    if descripcion:
        base += f" - {descripcion[:120]}"

    return base

def _find_related_local(user_request: str, solicitudes: List[Dict], max_results: int) -> Dict[str, Any]:
    """Fallback sin LLM: coincidencia simple por tokens en 'tipo' y 'descripcion'."""
    if not solicitudes:
        return {"related_requests": [], "no_related": True, "reasoning": "Sin solicitudes previas"}
    import re
    uq = (user_request or "").lower()
    uq_tokens = set(re.findall(r"[a-záéíóúüñ0-9]+", uq))
    scored = []
    for sol in solicitudes:
        desc = (sol.get("descripcion") or "").lower()
        tipo = (sol.get("tipo") or "").lower()
        text = f"{tipo} {desc}"
        tokens = set(re.findall(r"[a-záéíóúüñ0-9]+", text))
        inter = uq_tokens & tokens
        score = len(inter) / (len(uq_tokens) + 1e-6)
        if score > 0.05:
            scored.append((score, sol))
    scored.sort(key=lambda x: x[0], reverse=True)
    related = []
    for score, sol in scored[:max_results]:
        related.append({
            "id": sol.get("id"),
            "codigo": sol.get("codigo", ""),
            "estado": sol.get("estado", ""),
            "tipo": sol.get("tipo", ""),
            "fecha_creacion": sol.get("fecha_creacion", ""),
            "descripcion": sol.get("descripcion", ""),
            "display": _generate_request_display(sol)
        })
    return {
        "related_requests": related,
        "no_related": len(related) == 0,
        "reasoning": "Coincidencia local por tokens"
    }


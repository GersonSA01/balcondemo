# app/services/related_request_matcher.py
"""
Servicio para encontrar solicitudes relacionadas usando LLM.
Compara la solicitud del usuario con las solicitudes existentes en data_estudiante.json
"""
from typing import Dict, List, Any, Optional
import json
from pathlib import Path
from .config import llm
from .config import guarded_invoke

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
    Solo incluye ID, código, fecha y descripción.
    
    Args:
        solicitud: Diccionario con la solicitud
    
    Returns:
        String formateado con la información de la solicitud
    """
    parts = []

    parts.append(f"ID: {solicitud.get('id', 'N/A')}")
    codigo = solicitud.get('codigo', 'N/A')
    parts.append(f"Código: {codigo}")
    
    if solicitud.get('fecha_creacion'):
        parts.append(f"Fecha: {solicitud.get('fecha_creacion')}")
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
    
    print(f"\n{'='*80}")
    print(f"🔍 [RELATED REQUESTS] Iniciando búsqueda de solicitudes relacionadas")
    print(f"{'='*80}")
    print(f"📝 Solicitud del usuario: '{user_request}'")
    print(f"📊 Total de solicitudes previas encontradas: {len(solicitudes)}")
    
    if not solicitudes:
        print(f"⚠️ No hay solicitudes previas del estudiante")
        return {
            "related_requests": [],
            "no_related": True,
            "reasoning": "No hay solicitudes previas del estudiante"
        }
    
    # Formatear todas las solicitudes para el LLM
    formatted_requests = []
    for sol in solicitudes:
        formatted_requests.append({
            "id": sol.get("id"),
            "formatted": format_request_for_llm(sol),
            "original": sol
        })
    
    print(f"\n📋 Solicitudes previas del estudiante:")
    for i, req in enumerate(formatted_requests, 1):
        print(f"   {i}. ID: {req['id']} | Tipo: {req['original'].get('tipo', 'N/A')} | Estado: {req['original'].get('estado', 'N/A')}")
        if req['original'].get('descripcion'):
            desc = req['original'].get('descripcion', '')[:60]
            print(f"      Descripción: {desc}...")
    
    # Construir prompt para el LLM
    intent_summary = intent_slots.get("intent_short", user_request)
    print(f"\n🎯 Resumen de intención: '{intent_summary}'")
    
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

IMPORTANTE: Debes generar un mensaje natural y entendible para el usuario que explique las solicitudes relacionadas encontradas. 
Cita las solicitudes usando su CÓDIGO (ej: "SOL-BIENESTAR ESTUDIANTIL-20247-210107") para que el usuario pueda identificarlas fácilmente.
El mensaje debe ser amigable, claro y explicar por qué estas solicitudes están relacionadas con su requerimiento actual.

FORMATO DE RESPUESTA (JSON):
{{
    "related_request_ids": [210107, 199980],
    "user_message": "He encontrado 2 solicitudes relacionadas con tu requerimiento:\n\n1. SOL-BIENESTAR ESTUDIANTIL-20247-210107 - Esta solicitud está relacionada porque...\n2. SOL-JUST-OMI-SUFR-202112-010410 - Esta solicitud está relacionada porque...\n\n¿Deseas relacionar tu solicitud con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar.",
    "reasoning": "Breve explicación técnica de por qué estas solicitudes están relacionadas",
    "no_related": false
}}

Si no hay solicitudes relacionadas:
{{
    "related_request_ids": [],
    "user_message": "No he encontrado solicitudes relacionadas con tu requerimiento. ¿Deseas continuar sin relacionar tu solicitud con ninguna solicitud previa?",
    "reasoning": "No se encontraron solicitudes relacionadas",
    "no_related": true
}}
"""
    
    print(f"\n{'='*80}")
    print(f"📤 PROMPT ENVIADO AL LLM:")
    print(f"{'='*80}")
    print(prompt)
    print(f"{'='*80}\n")
    
    try:
        # Llamar al LLM
        print(f"⏳ Llamando al LLM...")
        response = guarded_invoke(llm, prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        print(f"\n{'='*80}")
        print(f"📥 RESPUESTA COMPLETA DEL LLM:")
        print(f"{'='*80}")
        print(response_text)
        print(f"{'='*80}\n")
        
        # Extraer JSON de la respuesta
        # El LLM puede devolver texto con JSON, necesitamos extraerlo
        import re
        print(f"🔧 Extrayendo JSON de la respuesta...")
        
        # Limpiar markdown si existe primero
        json_str = response_text.strip()
        if json_str.startswith("```"):
            json_str = re.sub(r'^```(?:json)?\s*', '', json_str, flags=re.MULTILINE)
            json_str = re.sub(r'\s*```\s*$', '', json_str, flags=re.MULTILINE)
            print(f"✅ JSON limpiado de markdown")
        
        # Intentar encontrar JSON con un patrón que maneje user_message con múltiples líneas
        # Buscar desde el primer { hasta el último } que contenga related_request_ids
        json_match = re.search(r'\{.*?"related_request_ids".*?\}', json_str, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(0)
            print(f"✅ JSON encontrado mediante regex")
        else:
            # Si no se encuentra, intentar parsear toda la respuesta como JSON
            print(f"⚠️ No se encontró JSON con regex, intentando parsear toda la respuesta")
        
        print(f"\n📄 JSON extraído (antes de parsear):")
        print(f"{json_str[:500]}..." if len(json_str) > 500 else f"{json_str}\n")
        
        # Intentar parsear el JSON
        result = None
        try:
            result = json.loads(json_str)
            print(f"✅ JSON parseado correctamente")
        except json.JSONDecodeError as e:
            print(f"⚠️ Error al parsear JSON: {e}")
            # Intentar arreglar saltos de línea no escapados en user_message
            # Reemplazar saltos de línea reales dentro de strings JSON con \n
            json_str_fixed = re.sub(r'(?<="user_message":\s*")([^"]*)"', 
                                   lambda m: m.group(1).replace('\n', '\\n').replace('\r', '\\r') + '"', 
                                   json_str, flags=re.DOTALL)
            try:
                result = json.loads(json_str_fixed)
                print(f"✅ JSON reparado y parseado correctamente")
            except json.JSONDecodeError:
                # Si aún falla, intentar extraer solo los campos necesarios manualmente
                print(f"❌ No se pudo parsear el JSON, intentando extracción manual...")
                # Extraer related_request_ids
                ids_match = re.search(r'"related_request_ids":\s*\[([^\]]*)\]', json_str)
                related_ids = []
                if ids_match:
                    ids_str = ids_match.group(1)
                    related_ids = [int(x.strip()) for x in ids_str.split(',') if x.strip().isdigit()]
                
                # Extraer user_message (puede tener múltiples líneas)
                msg_match = re.search(r'"user_message":\s*"((?:[^"\\]|\\.)*)"', json_str, re.DOTALL)
                user_message = ""
                if msg_match:
                    user_message = msg_match.group(1).replace('\\n', '\n').replace('\\r', '\r')
                
                # Extraer reasoning
                reason_match = re.search(r'"reasoning":\s*"((?:[^"\\]|\\.)*)"', json_str, re.DOTALL)
                reasoning = reason_match.group(1).replace('\\n', '\n').replace('\\r', '\r') if reason_match else "Sin razonamiento"
                
                # Extraer no_related
                no_related_match = re.search(r'"no_related":\s*(true|false)', json_str, re.IGNORECASE)
                no_related = no_related_match.group(1).lower() == 'true' if no_related_match else len(related_ids) == 0
                
                result = {
                    "related_request_ids": related_ids,
                    "user_message": user_message,
                    "reasoning": reasoning,
                    "no_related": no_related
                }
                print(f"✅ Campos extraídos manualmente")
        
        # Obtener las solicitudes relacionadas
        related_ids = result.get("related_request_ids", [])
        user_message = result.get("user_message", "")
        reasoning = result.get("reasoning", "Sin razonamiento")
        no_related = result.get("no_related", len(related_ids) == 0)
        
        print(f"📊 RESULTADO DEL LLM:")
        print(f"   - IDs de solicitudes relacionadas: {related_ids}")
        print(f"   - Mensaje para el usuario: {user_message[:100]}..." if len(user_message) > 100 else f"   - Mensaje para el usuario: {user_message}")
        print(f"   - Razonamiento técnico: {reasoning}")
        print(f"   - No relacionadas: {no_related}")
        
        # Filtrar y formatear solicitudes relacionadas
        related_requests = []
        print(f"\n🔍 Filtrando solicitudes relacionadas...")
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
                print(f"   ✅ ID {req_info['id']} agregado: {req_info['original'].get('tipo', 'N/A')}")
        
        # Limitar a max_results
        related_requests = related_requests[:max_results]
        
        print(f"\n✅ RESULTADO FINAL:")
        print(f"   - Solicitudes relacionadas encontradas: {len(related_requests)}")
        print(f"   - Límite aplicado (max_results={max_results}): {len(related_requests)}")
        print(f"{'='*80}\n")
        
        return {
            "related_requests": related_requests,
            "no_related": no_related,
            "reasoning": reasoning,
            "user_message": user_message  # Mensaje generado por el LLM para el usuario
        }
        
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ ERROR al buscar solicitudes relacionadas:")
        print(f"{'='*80}")
        print(f"   Tipo de error: {type(e).__name__}")
        print(f"   Mensaje: {str(e)}")
        print(f"{'='*80}")
        import traceback
        traceback.print_exc()
        print(f"{'='*80}\n")
        
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


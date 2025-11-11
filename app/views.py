from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import json
from pathlib import Path
from .services.rag_chat_service import classify_with_rag
import os

def balcon_view(request):
    return render(request, 'app/index.html')

def taxonomia_api(request):
    """Endpoint para servir la taxonomía desde el JSON."""
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    
    try:
        json_path = Path(__file__).resolve().parent / "data" / "taxonomia.json"
        
        if not json_path.exists():
            return JsonResponse({"error": "Taxonomía no encontrada"}, status=404)
        
        with open(json_path, "r", encoding="utf-8") as f:
            taxonomy = json.load(f)
        
        # Convertir a formato compatible con App.svelte: [{titulo, items}, ...]
        categorias = [
            {"titulo": cat, "items": subs}
            for cat, subs in taxonomy.items()
        ]
        
        return JsonResponse({"categorias": categorias}, status=200, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def estudiante_api(request):
    """Endpoint para servir los datos del estudiante simulado."""
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    
    try:
        json_path = Path(__file__).resolve().parent / "data" / "data_estudiante.json"
        
        if not json_path.exists():
            return JsonResponse({"error": "Datos del estudiante no encontrados"}, status=404)
        
        with open(json_path, "r", encoding="utf-8") as f:
            estudiante_data = json.load(f)
        
        return JsonResponse(estudiante_data, status=200, json_dumps_params={"ensure_ascii": False})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def chat_api(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        text = (payload.get("message") or "").strip()
        conversation_history = payload.get("history", [])  # Historial de conversación
        category = payload.get("category")  # Categoría seleccionada
        subcategory = payload.get("subcategory")  # Subcategoría seleccionada
        student_data = payload.get("student_data")  # Datos del estudiante
        
        if not text:
            return JsonResponse({"error": "message vacío"}, status=400)
        
        # Log de contexto recibido (opcional, para debugging)
        if category and subcategory:
            print(f"[Chat API] Contexto: {category} > {subcategory}")
        if student_data:
            nombre = student_data.get("credenciales", {}).get("nombre_completo", "N/A")
            matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A")
            print(f"[Chat API] Estudiante: {nombre} (Matrícula: {matricula})")
            
    except Exception:
        return JsonResponse({"error": "JSON inválido"}, status=400)

    # Usar el nuevo servicio RAG
    try:
        # Pasar contexto adicional al servicio RAG
        result = classify_with_rag(
            text, 
            conversation_history,
            category=category,
            subcategory=subcategory,
            student_data=student_data
        )
    except Exception as e:
        import traceback
        traceback.print_exc()  # Imprimir traceback completo en consola
        
        # Detectar errores de API
        error_str = str(e).lower()
        
        # Error de cuota agotada
        if "429" in error_str or "quota exceeded" in error_str or "resourceexhausted" in error_str:
            return JsonResponse({
                "message": "Cuota de consultas por IA agotada. Por favor, intenta nuevamente mañana o contacta al administrador del sistema.",
                "category": None,
                "subcategory": None,
                "confidence": 0.0,
                "fields_required": [],
                "needs_confirmation": False,
                "confirmed": None,
                "intent_slots": None,
                "evidence": [],
                "source_pdfs": [],
            }, status=200)
        
        # Error de API key expirada o inválida
        if "api key expired" in error_str or "api_key_invalid" in error_str or "api key invalid" in error_str:
            return JsonResponse({
                "message": "La clave de API ha expirado o es inválida. Por favor, contacta al administrador del sistema para renovarla.",
                "category": None,
                "subcategory": None,
                "confidence": 0.0,
                "fields_required": [],
                "needs_confirmation": False,
                "confirmed": None,
                "intent_slots": None,
                "evidence": [],
                "source_pdfs": [],
            }, status=200)
        
        return JsonResponse({
            "error": f"Error al procesar la solicitud: {str(e)}"
        }, status=500)

    # Extraer respuesta
    reply = result.get("summary", "No pude procesar tu solicitud.")
    
    # Debug: verificar contenido antes de limpiar
    if student_data:
        nombre_esperado = student_data.get("credenciales", {}).get("nombre_completo", "").split()[0] if student_data.get("credenciales", {}).get("nombre_completo") else ""
        if nombre_esperado:
            print(f"🔍 [Views] Nombre esperado en saludo: '{nombre_esperado}'")
            print(f"🔍 [Views] Reply contiene nombre?: {nombre_esperado in reply}")
            print(f"🔍 [Views] Primeros 100 chars de reply: '{reply[:100]}'")
    
    # Limpiar respuesta de markdown si viene del LLM (solo asteriscos, NO afecta el saludo)
    reply = reply.replace("**", "").strip()
    
    # Debug: verificar después de limpiar
    if student_data:
        nombre_esperado = student_data.get("credenciales", {}).get("nombre_completo", "").split()[0] if student_data.get("credenciales", {}).get("nombre_completo") else ""
        if nombre_esperado:
            print(f"🔍 [Views] Después de limpiar markdown - Reply contiene nombre?: {nombre_esperado in reply}")
            print(f"🔍 [Views] Primeros 100 chars después: '{reply[:100]}'")
    
    # Si hay handoff automático, solo loguear (sin crear ticket)
    if result.get("handoff_auto"):
        try:
            import time
            
            # Extraer info del estudiante para logging
            nombre = student_data.get("credenciales", {}).get("nombre_completo", "Usuario") if student_data else "Usuario"
            matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A") if student_data else "N/A"
            email = student_data.get("credenciales", {}).get("correo", "no-email@unemi.edu.ec") if student_data else "no-email@unemi.edu.ec"
            
            # Log de derivación (sin ticket)
            print(f"\n{'='*60}")
            print(f"📤 DERIVACIÓN AUTOMÁTICA A AGENTE")
            print(f"{'='*60}")
            print(f"📅 Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"👤 Estudiante: {nombre} ({matricula})")
            print(f"📧 Email: {email}")
            print(f"📂 Categoría: {result.get('category')} › {result.get('subcategory')}")
            print(f"🏢 Canal: {result.get('handoff_channel')}")
            print(f"📊 Motivo: {result.get('handoff_reason')}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            print(f"⚠️ Error al registrar derivación: {e}")

    return JsonResponse({
        "message": reply,
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "confidence": result.get("confidence", 0.7),
        "fields_required": result.get("campos_requeridos") or [],
        "needs_confirmation": result.get("needs_confirmation", False),
        "confirmed": result.get("confirmed", None),
        "intent_slots": result.get("intent_slots"),  # Incluir slots para el historial
        "evidence": [],  # Ya no usamos evidence separada, está integrada en la respuesta RAG
        "source_pdfs": result.get("source_pdfs", []),  # PDFs fuente
        "handoff": result.get("handoff", False),
        "handoff_auto": result.get("handoff_auto", False),
        "handoff_reason": result.get("handoff_reason"),
        "handoff_channel": result.get("handoff_channel"),
    }, status=200)


def serve_pdf(request, pdf_path):
    """Endpoint para servir PDFs desde app/data con navegación en subdirectorios."""
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    
    try:
        # Construir path seguro dentro de app/data
        data_dir = Path(__file__).resolve().parent / "data"
        
        # Normalizar y validar path (evitar directory traversal)
        requested_path = Path(pdf_path).as_posix()  # Normalizar barras
        full_path = (data_dir / requested_path).resolve()
        
        # Verificar que el path esté dentro de data_dir
        if not str(full_path).startswith(str(data_dir)):
            raise Http404("Ruta no permitida")
        
        # Verificar que el archivo existe
        if not full_path.exists() or not full_path.is_file():
            raise Http404("Archivo no encontrado")
        
        # Determinar content_type según extensión
        suffix = full_path.suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
        }
        
        content_type = content_types.get(suffix, 'application/octet-stream')
        
        # Servir el archivo
        return FileResponse(
            open(full_path, 'rb'),
            content_type=content_type,
            as_attachment=False,  # False = abrir en navegador, True = descargar
            filename=full_path.name
        )
    except Http404 as e:
        return JsonResponse({"error": str(e)}, status=404)
    except Exception as e:
        return JsonResponse({"error": f"Error al servir archivo: {str(e)}"}, status=500)



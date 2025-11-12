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

    uploaded_file = None
    text = ""
    conversation_history = []
    category = None
    subcategory = None
    student_data = None

    try:
        # Detectar si viene como multipart/form-data (con archivo) o JSON
        if request.content_type and "multipart/form-data" in request.content_type:
            # FormData: extraer campos y archivo
            text = request.POST.get("message", "").strip()
            history_str = request.POST.get("history", "[]")
            try:
                conversation_history = json.loads(history_str) if history_str else []
            except json.JSONDecodeError:
                conversation_history = []
            
            category = request.POST.get("category")
            subcategory = request.POST.get("subcategory")
            
            student_data_str = request.POST.get("student_data")
            if student_data_str:
                try:
                    student_data = json.loads(student_data_str)
                except json.JSONDecodeError:
                    student_data = None
            
            # Procesar archivo si existe
            if "file" in request.FILES:
                uploaded_file = request.FILES["file"]
                
                # Validar tamaño (máximo 4MB)
                MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB en bytes
                if uploaded_file.size > MAX_FILE_SIZE:
                    return JsonResponse({
                        "error": f"El archivo es demasiado grande. El tamaño máximo es 4MB. Tu archivo tiene {(uploaded_file.size / 1024 / 1024):.2f}MB."
                    }, status=400)
                
                # Validar tipo de archivo
                allowed_types = [
                    'application/pdf',
                    'image/jpeg',
                    'image/jpg',
                    'image/png'
                ]
                allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
                
                file_type = uploaded_file.content_type
                file_name = uploaded_file.name.lower()
                has_valid_extension = any(file_name.endswith(ext) for ext in allowed_extensions)
                
                if file_type not in allowed_types and not has_valid_extension:
                    return JsonResponse({
                        "error": "Tipo de archivo no permitido. Solo se aceptan PDF, JPG, JPEG o PNG."
                    }, status=400)
                
                print(f"[Chat API] ✅ Archivo recibido: {uploaded_file.name} ({uploaded_file.size} bytes, tipo: {file_type})")
        else:
            # JSON normal (sin archivo)
            payload = json.loads(request.body.decode("utf-8"))
            text = payload.get("message")
            
            # Convertir a string si es un número o None
            if text is None:
                text = ""
            else:
                text = str(text).strip()
            
            conversation_history = payload.get("history", [])  # Historial de conversación
            category = payload.get("category")  # Categoría seleccionada
            subcategory = payload.get("subcategory")  # Subcategoría seleccionada
            student_data = payload.get("student_data")  # Datos del estudiante del frontend
        
        # Debug: Log del payload recibido
        print(f"[Chat API] 📥 Payload recibido:")
        print(f"   message: {text} (type: {type(text)})")
        print(f"   category: {category}")
        print(f"   subcategory: {subcategory}")
        print(f"   history length: {len(conversation_history)}")
        print(f"   student_data: {student_data is not None}")
        
        # Si no se recibió student_data del frontend, intentar cargarlo desde el archivo JSON (datos de prueba)
        if not student_data:
            try:
                import os
                from pathlib import Path
                # Buscar el archivo en la ruta relativa desde views.py
                # views.py está en app/, y data_estudiante.json está en app/data/
                json_path = Path(__file__).parent / "data" / "data_estudiante.json"
                if json_path.exists():
                    with open(json_path, "r", encoding="utf-8") as f:
                        student_data = json.load(f)
                        print(f"[Chat API] ✅ Cargados datos del estudiante desde {json_path}")
                        print(f"[Chat API] Estudiante: {student_data.get('credenciales', {}).get('nombre_completo', 'N/A')}")
                else:
                    print(f"[Chat API] ⚠️ No se encontró el archivo en {json_path}")
            except Exception as e:
                print(f"[Chat API] ⚠️ No se pudieron cargar datos del estudiante: {e}")
                import traceback
                traceback.print_exc()
                student_data = None
        
        # Validar que haya texto (permitir números e IDs como texto válido)
        if not text:
            # Si no hay texto, podría ser una selección de solicitud relacionada por botón
            # En ese caso, el mensaje debería venir en el historial o como parte del contexto
            print(f"[Chat API] ⚠️ Mensaje vacío, verificando historial...")
            # Buscar en el historial si hay un mensaje reciente del usuario
            if conversation_history:
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        msg_text = msg.get("content") or msg.get("text", "")
                        if msg_text:
                            text = str(msg_text).strip()
                            print(f"[Chat API] ✅ Usando mensaje del historial: {text[:50]}")
                            break
            
            # Si aún no hay texto, usar un mensaje por defecto
            if not text:
                text = "solicitud relacionada seleccionada"
                print(f"[Chat API] ⚠️ Usando mensaje por defecto: {text}")
        
        # Log de contexto recibido (opcional, para debugging)
        if category and subcategory:
            print(f"[Chat API] Contexto: {category} > {subcategory}")
        if student_data:
            nombre = student_data.get("credenciales", {}).get("nombre_completo", "N/A")
            matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A")
            print(f"[Chat API] Estudiante: {nombre} (Matrícula: {matricula})")
        else:
            print(f"[Chat API] ⚠️ No hay datos del estudiante disponibles")
            
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": f"Error al procesar la solicitud: {str(e)}"}, status=400)

    # Usar el nuevo servicio RAG
    try:
        # Pasar contexto adicional al servicio RAG (incluyendo archivo si existe)
        result = classify_with_rag(
            text, 
            conversation_history,
            category=category,
            subcategory=subcategory,
            student_data=student_data,
            uploaded_file=uploaded_file  # Pasar archivo si existe
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
    
    # Si hay handoff enviado, el log ya se hizo en rag_chat_service
    # Solo mantener esta sección por compatibilidad, pero ya no se usa handoff_auto
    if result.get("handoff_sent"):
        # El log ya se hizo en rag_chat_service.py
        pass

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
        "handoff_sent": result.get("handoff_sent", False),  # Nuevo flag para handoff enviado
        "needs_handoff_details": result.get("needs_handoff_details", False),  # Flag para pedir más detalles
        "needs_handoff_file": result.get("needs_handoff_file", False),  # Flag para requerir archivo
        "handoff_file_max_size_mb": result.get("handoff_file_max_size_mb", 4),  # Tamaño máximo del archivo
        "handoff_file_types": result.get("handoff_file_types", []),  # Tipos de archivo permitidos
        "handoff_reason": result.get("handoff_reason"),
        "handoff_channel": result.get("handoff_channel"),
        "close_chat": result.get("close_chat", False),  # Flag para cerrar el chat
        # Nuevos campos para solicitudes relacionadas
        "needs_related_request_selection": result.get("needs_related_request_selection", False),
        "needs_related_request_confirmation": result.get("needs_related_request_confirmation", False),
        "needs_more_details": result.get("needs_more_details", False),
        "related_requests": result.get("related_requests", []),
        "no_related_request_option": result.get("no_related_request_option", False),
        "selected_related_request_id": result.get("selected_related_request_id"),
        "selected_related_request": result.get("selected_related_request"),
        "reasoning": result.get("reasoning"),
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



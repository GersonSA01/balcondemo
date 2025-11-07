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
    
    # Limpiar respuesta de markdown si viene del LLM
    reply = reply.replace("**", "").strip()
    
    # Si hay handoff automático, crear ticket silenciosamente
    ticket_id = None
    if result.get("handoff_auto"):
        try:
            import time
            import random
            
            ticket_id = f"TKT-{int(time.time())}-{random.randint(1000, 9999)}"
            
            # Extraer info del estudiante
            nombre = student_data.get("credenciales", {}).get("nombre_completo", "Usuario") if student_data else "Usuario"
            matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A") if student_data else "N/A"
            email = student_data.get("credenciales", {}).get("correo", "no-email@unemi.edu.ec") if student_data else "no-email@unemi.edu.ec"
            
            # Construir resumen de conversación
            recent_messages = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
            conversation_summary = "\n\n".join([
                f"{'👤 Usuario' if msg.get('who') == 'user' else '🤖 Bot'}: {msg.get('text', '')[:200]}..."
                for msg in recent_messages
            ])
            
            # Log del ticket
            print(f"\n{'='*60}")
            print(f"🎫 TICKET AUTOMÁTICO CREADO: {ticket_id}")
            print(f"{'='*60}")
            print(f"📅 Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"👤 Estudiante: {nombre} ({matricula})")
            print(f"📧 Email: {email}")
            print(f"📂 Categoría: {result.get('category')} › {result.get('subcategory')}")
            print(f"🏢 Canal: {result.get('handoff_channel')}")
            print(f"📊 Motivo: {result.get('handoff_reason')}")
            print(f"\n💬 Resumen de conversación:")
            print(conversation_summary)
            print(f"{'='*60}\n")
            
            # Agregar ticket ID al mensaje
            reply = f"{reply}\n\n🎫 **Ticket #{ticket_id}** creado automáticamente."
            
        except Exception as e:
            print(f"⚠️ Error al crear ticket automático: {e}")

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
        "ticket_id": ticket_id,
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
        
        # Verificar que el archivo existe y es PDF
        if not full_path.exists() or not full_path.is_file():
            raise Http404("PDF no encontrado")
        
        if not full_path.suffix.lower() == '.pdf':
            raise Http404("Solo se permiten archivos PDF")
        
        # Servir el archivo
        return FileResponse(
            open(full_path, 'rb'),
            content_type='application/pdf',
            as_attachment=False,  # False = abrir en navegador, True = descargar
            filename=full_path.name
        )
    except Http404 as e:
        return JsonResponse({"error": str(e)}, status=404)
    except Exception as e:
        return JsonResponse({"error": f"Error al servir PDF: {str(e)}"}, status=500)


@csrf_exempt
def create_ticket(request):
    """
    Endpoint para crear tickets de soporte cuando se requiere handoff a agente humano.
    
    Request Body:
    {
        "category": "Académico",
        "subcategory": "Matriculación",
        "student_data": {...},
        "conversation": [...],
        "handoff_reason": "baja_confianza<0.42",
        "handoff_channel": "Mesa de Ayuda SGA"
    }
    
    Response:
    {
        "ticket_id": "TKT-2024-001234",
        "channel": "Mesa de Ayuda SGA",
        "status": "created",
        "message": "Ticket creado exitosamente"
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    
    try:
        payload = json.loads(request.body.decode("utf-8"))
        
        category = payload.get("category", "Consultas varias")
        subcategory = payload.get("subcategory", "Consultas varias")
        student_data = payload.get("student_data", {})
        conversation = payload.get("conversation", [])
        handoff_reason = payload.get("handoff_reason", "")
        handoff_channel = payload.get("handoff_channel", "Mesa de Ayuda SGA")
        
        # Extraer información del estudiante
        nombre = student_data.get("credenciales", {}).get("nombre_completo", "Usuario")
        matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A")
        email = student_data.get("credenciales", {}).get("correo", "no-email@unemi.edu.ec")
        
        # Generar ticket ID único (timestamp + random)
        import time
        import random
        ticket_id = f"TKT-{int(time.time())}-{random.randint(1000, 9999)}"
        
        # Construir resumen de conversación (últimos 5 mensajes)
        recent_messages = conversation[-5:] if len(conversation) > 5 else conversation
        conversation_summary = "\n\n".join([
            f"{'👤 Usuario' if msg.get('who') == 'user' else '🤖 Bot'}: {msg.get('text', '')[:200]}..."
            for msg in recent_messages
        ])
        
        # Log del ticket (en producción, aquí insertarías en BD)
        ticket_data = {
            "ticket_id": ticket_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "subcategory": subcategory,
            "channel": handoff_channel,
            "student": {
                "nombre": nombre,
                "matricula": matricula,
                "email": email
            },
            "handoff_reason": handoff_reason,
            "conversation_summary": conversation_summary,
            "status": "pending",
            "priority": "normal"
        }
        
        # Log en consola (desarrollo)
        print(f"\n{'='*60}")
        print(f"🎫 NUEVO TICKET CREADO: {ticket_id}")
        print(f"{'='*60}")
        print(f"📅 Fecha: {ticket_data['created_at']}")
        print(f"👤 Estudiante: {nombre} ({matricula})")
        print(f"📧 Email: {email}")
        print(f"📂 Categoría: {category} › {subcategory}")
        print(f"🏢 Canal: {handoff_channel}")
        print(f"📊 Motivo: {handoff_reason}")
        print(f"\n💬 Resumen de conversación:")
        print(conversation_summary)
        print(f"{'='*60}\n")
        
        # En producción, guardar en base de datos:
        # Ticket.objects.create(**ticket_data)
        
        # También podrías enviar email/notificación aquí:
        # send_ticket_notification(ticket_data)
        
        return JsonResponse({
            "ticket_id": ticket_id,
            "channel": handoff_channel,
            "status": "created",
            "message": "Ticket creado exitosamente. Un agente te contactará pronto.",
            "estimated_response_time": "24 horas",
            "contact_methods": ["correo electrónico", "portal SGA"]
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "error": f"Error al crear ticket: {str(e)}"
        }, status=500)

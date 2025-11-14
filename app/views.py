from django.shortcuts import render
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
import json
from pathlib import Path
from typing import Dict, Optional
from .services.privategpt_chat_service import classify_with_privategpt
from .services.solicitud_service import (
    crear_solicitud,
    obtener_solicitudes_usuario,
    obtener_historial_solicitud,
    corregir_solicitud,
    eliminar_solicitud
)
from .services.config import encrypt, decrypt

DATA_UNEMI_FILE = "data_unemi.json"


def _load_student_data_from_unemi(usuario_cedula: str, perfil_id: str) -> Optional[Dict]:
    """
    Carga los datos completos del estudiante desde data_unemi.json.
    
    Args:
        usuario_cedula: Cédula del usuario
        perfil_id: ID del perfil seleccionado
    
    Returns:
        Dict con estructura completa: {persona, perfiles, solicitudes_balcon, ...}
        o None si no se encuentra
    """
    try:
        json_path = Path(__file__).resolve().parent / "data" / DATA_UNEMI_FILE
        if not json_path.exists():
            return None
        
        with open(json_path, "r", encoding="utf-8") as f:
            data_unemi = json.load(f)
        
        usuario_data = data_unemi.get(usuario_cedula)
        if not usuario_data:
            return None
        
        # Retornar datos completos del usuario (incluye persona, perfiles, solicitudes_balcon)
        return usuario_data
    except Exception as e:
        print(f"[Views] Error cargando datos desde data_unemi.json: {e}")
        return None

def balcon_view(request):
    return render(request, 'app/index.html')

def usuarios_api(request):
    """Endpoint para listar todos los usuarios disponibles desde data_unemi.json."""
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    
    try:
        json_path = Path(__file__).resolve().parent / "data" / DATA_UNEMI_FILE
        
        if not json_path.exists():
            return JsonResponse({"error": "Archivo de datos no encontrado"}, status=404)
        
        with open(json_path, "r", encoding="utf-8") as f:
            data_unemi = json.load(f)
        
        # Convertir el formato {cedula: {persona, perfiles, ...}} a lista de usuarios
        usuarios = []
        for cedula, datos in data_unemi.items():
            persona = datos.get("persona", {})
            perfiles = datos.get("perfiles", [])
            
            # Construir nombre completo
            nombres = persona.get("nombres", "")
            apellido1 = persona.get("apellido1", "")
            apellido2 = persona.get("apellido2", "")
            nombre_completo = f"{nombres} {apellido1} {apellido2}".strip()
            
            # Filtrar solo perfiles activos (status: true)
            perfiles_activos = [p for p in perfiles if p.get("status", False)]
            
            # Mapear perfiles a formato esperado por el frontend
            perfiles_formateados = []
            for perfil in perfiles_activos:
                # Determinar rol basado en los flags del perfil
                rol = "estudiante"
                if perfil.get("es_profesor", False):
                    rol = "profesor"
                elif perfil.get("es_administrativo", False):
                    rol = "administrativo"
                elif perfil.get("es_externo", False):
                    rol = "externo"
                elif perfil.get("es_postulante", False):
                    rol = "postulante"
                elif perfil.get("es_postulanteempleo", False):
                    rol = "postulante_empleo"
                
                perfiles_formateados.append({
                    "id": perfil.get("id"),
                    "tipo": perfil.get("tipo", ""),
                    "rol": rol,
                    "carrera_nombre": perfil.get("carrera_nombre"),
                    "facultad_nombre": perfil.get("facultad_nombre"),
                    "modalidad_nombre": perfil.get("modalidad_nombre"),
                })
            
            usuarios.append({
                "cedula": cedula,
                "nombre": nombre_completo or f"Usuario {cedula}",
                "perfiles": perfiles_formateados
            })
        
        return JsonResponse(
            {"usuarios": usuarios},
            status=200,
            json_dumps_params={"ensure_ascii": False}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)

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
    """Endpoint para servir los datos de un usuario y perfil específico desde data_unemi.json."""
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)

    usuario_cedula = request.GET.get("usuario")  # Cédula del usuario
    perfil_id = request.GET.get("perfil")  # ID del perfil

    if not usuario_cedula:
        return JsonResponse(
            {"error": "Parámetro 'usuario' (cédula) requerido"},
            status=400,
        )

    if not perfil_id:
        return JsonResponse(
            {"error": "Parámetro 'perfil' (ID) requerido"},
            status=400,
        )

    try:
        json_path = Path(__file__).resolve().parent / "data" / DATA_UNEMI_FILE

        if not json_path.exists():
            return JsonResponse(
                {"error": "Archivo de datos no encontrado"},
                status=404,
            )

        with open(json_path, "r", encoding="utf-8") as f:
            data_unemi = json.load(f)

        # Buscar el usuario por cédula
        usuario_data = data_unemi.get(usuario_cedula)
        if not usuario_data:
            return JsonResponse(
                {"error": f"Usuario con cédula {usuario_cedula} no encontrado"},
                status=404,
            )

        persona = usuario_data.get("persona", {})
        perfiles = usuario_data.get("perfiles", [])
        solicitudes_balcon = usuario_data.get("solicitudes_balcon", [])

        # Buscar el perfil específico
        perfil_seleccionado = None
        for perfil in perfiles:
            if str(perfil.get("id")) == str(perfil_id):
                perfil_seleccionado = perfil
                break

        if not perfil_seleccionado:
            return JsonResponse(
                {"error": f"Perfil con ID {perfil_id} no encontrado para el usuario {usuario_cedula}"},
                status=404,
            )

        # Construir nombre completo
        nombres = persona.get("nombres", "")
        apellido1 = persona.get("apellido1", "")
        apellido2 = persona.get("apellido2", "")
        nombre_completo = f"{nombres} {apellido1} {apellido2}".strip()

        # Determinar rol del perfil
        rol = "estudiante"
        if perfil_seleccionado.get("es_profesor", False):
            rol = "profesor"
        elif perfil_seleccionado.get("es_administrativo", False):
            rol = "administrativo"
        elif perfil_seleccionado.get("es_externo", False):
            rol = "externo"
        elif perfil_seleccionado.get("es_postulante", False):
            rol = "postulante"
        elif perfil_seleccionado.get("es_postulanteempleo", False):
            rol = "postulante_empleo"

        # Construir contexto del estudiante en formato compatible con el código existente
        contexto = {
            "credenciales": {
                "nombre_completo": nombre_completo,
                "cedula": usuario_cedula,
            },
            "datos_personales": {
                "nombres": nombres,
                "apellido_paterno": apellido1,
                "apellido_materno": apellido2,
                "cedula": usuario_cedula,
                "email": persona.get("email", ""),
                "telefono": persona.get("telefono", ""),
            },
            "informacion_academica": {
                "carrera": perfil_seleccionado.get("carrera_nombre", ""),
                "facultad": perfil_seleccionado.get("facultad_nombre", ""),
                "modalidad": perfil_seleccionado.get("modalidad_nombre", ""),
            },
            "solicitudes": solicitudes_balcon,  # Para compatibilidad con load_student_requests
            "solicitudes_balcon": solicitudes_balcon,  # También mantener el nombre original
        }

        # Metadatos del perfil
        perfil_meta = {
            "id": perfil_seleccionado.get("id"),
            "tipo": perfil_seleccionado.get("tipo", ""),
            "rol": rol,
            "carrera_nombre": perfil_seleccionado.get("carrera_nombre"),
            "facultad_nombre": perfil_seleccionado.get("facultad_nombre"),
            "modalidad_nombre": perfil_seleccionado.get("modalidad_nombre"),
        }

        return JsonResponse(
            {
                "usuario": {
                    "cedula": usuario_cedula,
                    "nombre": nombre_completo,
                },
                "perfil": perfil_meta,
                "contexto": contexto,
            },
            status=200,
            json_dumps_params={"ensure_ascii": False},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
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
    profile_type = None

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
            profile_type = request.POST.get("profile_type") or request.POST.get("profileType")
            
            student_data_str = request.POST.get("student_data")
            student_data_raw = None
            if student_data_str:
                try:
                    student_data_raw = json.loads(student_data_str)
                except json.JSONDecodeError:
                    student_data_raw = None
            
            # Cargar datos completos desde data_unemi.json si tenemos información del perfil
            student_data = None
            perfil_id_final = None
            
            if student_data_raw:
                usuario_cedula = None
                perfil_id = None
                
                if isinstance(student_data_raw, dict):
                    usuario_cedula = (
                        student_data_raw.get("credenciales", {}).get("cedula") or
                        student_data_raw.get("datos_personales", {}).get("cedula") or
                        student_data_raw.get("cedula")
                    )
                    
                    perfil_info = student_data_raw.get("perfil") or request.POST.get("perfil")
                    if perfil_info:
                        if isinstance(perfil_info, str):
                            try:
                                perfil_info = json.loads(perfil_info)
                            except:
                                pass
                        if isinstance(perfil_info, dict):
                            perfil_id = perfil_info.get("id")
                    
                    # También buscar perfil_id directo en POST
                    if not perfil_id:
                        perfil_id = request.POST.get("perfil_id") or request.POST.get("perfilId")
                
                perfil_id_final = perfil_id
                
                if usuario_cedula and perfil_id:
                    student_data = _load_student_data_from_unemi(usuario_cedula, perfil_id)
                    if not student_data:
                        student_data = student_data_raw
                else:
                    student_data = student_data_raw
            
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
            student_data_raw = payload.get("student_data")  # Datos del estudiante del frontend (puede venir como contexto)
            profile_type = payload.get("profile_type")
            perfil_id_from_payload = payload.get("perfil_id") or payload.get("perfilId")  # ID del perfil desde el frontend
            
            # Cargar datos completos desde data_unemi.json si tenemos información del perfil
            student_data = None
            perfil_id_final = None
            
            if student_data_raw:
                # Intentar extraer cédula y perfil_id desde student_data_raw
                usuario_cedula = None
                perfil_id = None
                
                # Buscar cédula en diferentes ubicaciones
                if isinstance(student_data_raw, dict):
                    usuario_cedula = (
                        student_data_raw.get("credenciales", {}).get("cedula") or
                        student_data_raw.get("datos_personales", {}).get("cedula") or
                        student_data_raw.get("cedula")
                    )
                    
                    # Buscar perfil_id desde diferentes ubicaciones
                    perfil_info = student_data_raw.get("perfil") or payload.get("perfil")
                    if perfil_info:
                        if isinstance(perfil_info, dict):
                            perfil_id = perfil_info.get("id")
                        elif isinstance(perfil_info, str):
                            try:
                                perfil_info_parsed = json.loads(perfil_info)
                                perfil_id = perfil_info_parsed.get("id") if isinstance(perfil_info_parsed, dict) else None
                            except:
                                pass
                
                # Priorizar perfil_id desde payload directo
                if perfil_id_from_payload:
                    perfil_id = perfil_id_from_payload
                
                perfil_id_final = perfil_id
                
                # Si tenemos cédula y perfil_id, cargar desde data_unemi.json
                if usuario_cedula and perfil_id:
                    student_data = _load_student_data_from_unemi(usuario_cedula, perfil_id)
                    if student_data:
                        print(f"[Chat API] ✅ Datos cargados desde data_unemi.json para usuario {usuario_cedula}, perfil {perfil_id}")
                    else:
                        print(f"[Chat API] ⚠️ No se pudieron cargar datos desde data_unemi.json, usando datos del frontend")
                        student_data = student_data_raw
                else:
                    # Usar datos del frontend como fallback
                    student_data = student_data_raw
                    print(f"[Chat API] ⚠️ Usando datos del frontend (no se pudo determinar cédula={usuario_cedula}/perfil_id={perfil_id})")
        
        if not student_data:
            print(f"[Chat API] ⚠️ No se recibieron datos del estudiante del frontend")
        
        if not text:
            if conversation_history:
                for msg in reversed(conversation_history):
                    role = msg.get("role") or msg.get("who")
                    if role in ("user", "student", "estudiante"):
                        msg_text = msg.get("content") or msg.get("text", "")
                        if msg_text:
                            text = str(msg_text).strip()
                            break
            if not text:
                text = "solicitud relacionada seleccionada"
        
        if category and subcategory:
            print(f"[Chat API] Contexto: {category} > {subcategory}")
        if student_data:
            if isinstance(student_data, dict):
                credenciales_nombre = student_data.get("credenciales", {}).get("nombre_completo")
                datos_personales_nombre = student_data.get("datos_personales", {}).get("nombres")
                nombre = credenciales_nombre or datos_personales_nombre or "N/A"
                matricula = student_data.get("informacion_academica", {}).get("matricula", "N/A")
            else:
                nombre = "N/A"
                matricula = "N/A"
            print(f"[Chat API] Perfil activo: {profile_type or 'desconocido'} | Identificador: {matricula} | Nombre: {nombre}")
        else:
            print(f"[Chat API] ⚠️ No hay datos del estudiante disponibles")
            
    except json.JSONDecodeError:
        return JsonResponse({"error": "JSON inválido"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": f"Error al procesar la solicitud: {str(e)}"}, status=400)

    # Usar el servicio PrivateGPT
    try:
        # Pasar contexto adicional al servicio PrivateGPT (incluyendo archivo si existe)
        # También pasar perfil_id para que se use en la extracción del rol
        perfil_id_para_service = None
        if 'perfil_id_final' in locals():
            perfil_id_para_service = perfil_id_final
        
        result = classify_with_privategpt(
            text, 
            conversation_history,
            category=category,
            subcategory=subcategory,
            student_data=student_data,
            uploaded_file=uploaded_file,  # Pasar archivo si existe
            perfil_id=perfil_id_para_service  # Pasar perfil_id si está disponible
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

    # Validar que result no sea None
    if result is None:
        print(f"⚠️ [Views] Error: result es None")
        return JsonResponse({
            "message": "No pude procesar tu solicitud. Por favor, intenta nuevamente.",
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

    # Extraer respuesta
    # Buscar "summary" (formato de classify_with_privategpt) o "response" (formato directo de PrivateGPT)
    reply = result.get("summary") or result.get("response") or "No pude procesar tu solicitud."
    
    if student_data:
        nombre_esperado = student_data.get("credenciales", {}).get("nombre_completo", "").split()[0] if student_data.get("credenciales", {}).get("nombre_completo") else ""
        if nombre_esperado:
            print(f"🔍 [Views] Nombre esperado en saludo: '{nombre_esperado}'")
            print(f"🔍 [Views] Reply contiene nombre?: {nombre_esperado in reply}")
            print(f"🔍 [Views] Primeros 100 chars de reply: '{reply[:100]}'")
    
    # Limpiar respuesta de markdown si viene del LLM (solo asteriscos, NO afecta el saludo)
    reply = reply.replace("**", "").strip()
    

    return JsonResponse({
        "message": reply,  # Campo legacy para compatibilidad
        "response": reply,  # Campo nuevo (formato PrivateGPT) - mismo contenido que message
        "category": result.get("category"),
        "subcategory": result.get("subcategory"),
        "confidence": result.get("confidence", 0.7),
        "fields_required": result.get("campos_requeridos") or [],
        "needs_confirmation": result.get("needs_confirmation", False),
        "confirmed": result.get("confirmed", None),
        "intent_slots": result.get("intent_slots"),  # Incluir slots para el historial
        "evidence": [],  # Ya no usamos evidence separada, está integrada en la respuesta RAG
        "source_pdfs": result.get("source_pdfs", []),  # PDFs fuente (nombres de archivos)
        "fuentes": result.get("fuentes", []),  # Fuentes completas con archivo y página [{"archivo": str, "pagina": str}]
        "has_information": result.get("has_information", False),  # Si se encontró información en los documentos
        "needs_related_request_selection": result.get("needs_related_request_selection", False),  # Si necesita selección de solicitud relacionada
        "related_requests": result.get("related_requests", []),  # Lista de solicitudes relacionadas
        "no_related_request_option": result.get("no_related_request_option", False),  # Si se debe mostrar opción "No hay solicitud relacionada"
        "handoff": result.get("handoff", False),
        "handoff_reason": result.get("handoff_reason"),
        "handoff_channel": result.get("handoff_channel"),
        "handoff_sent": result.get("handoff_sent", False),
        "needs_handoff_details": result.get("needs_handoff_details", False),
        "needs_handoff_file": result.get("needs_handoff_file", False),
        "handoff_file_max_size_mb": result.get("handoff_file_max_size_mb", 4),
        "handoff_file_types": result.get("handoff_file_types", []),
        "department": result.get("department"),  # Departamento al que se deriva
        "thinking_status": result.get("thinking_status"),  # Estado de pensamiento dinámico
    }, status=200)


def serve_pdf(request, pdf_path):
    """
    Endpoint para servir PDFs desde la carpeta PDF (raíz) o app/data.
    Prioridad: 1. Carpeta PDF, 2. app/data
    """
    if request.method != "GET":
        return JsonResponse({"error": "GET only"}, status=405)
    
    try:
        # Normalizar y validar path (evitar directory traversal)
        requested_path = Path(pdf_path).as_posix()  # Normalizar barras
        file_name = Path(requested_path).name  # Solo el nombre del archivo
        
        # Opción 1: Buscar en la carpeta PDF (raíz del proyecto)
        pdf_dir = Path(__file__).resolve().parent.parent / "PDF"
        full_path_pdf = (pdf_dir / file_name).resolve()
        
        # Opción 2: Buscar en app/data con subdirectorios
        data_dir = Path(__file__).resolve().parent / "data"
        full_path_data = (data_dir / requested_path).resolve()
        
        # Determinar qué archivo usar
        full_path = None
        if pdf_dir.exists() and full_path_pdf.exists() and full_path_pdf.is_file():
            # Verificar que esté dentro de pdf_dir (seguridad)
            if str(full_path_pdf).startswith(str(pdf_dir)):
                full_path = full_path_pdf
        elif data_dir.exists() and full_path_data.exists() and full_path_data.is_file():
            # Verificar que esté dentro de data_dir (seguridad)
            if str(full_path_data).startswith(str(data_dir)):
                full_path = full_path_data
        
        if not full_path:
            raise Http404(f"Archivo no encontrado: {file_name}")
        
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


@csrf_exempt
def balcon_servicios_api(request):
    """
    Endpoint para manejar solicitudes del balcón de servicios.
    Simula el comportamiento del sistema real usando JSON como almacenamiento.
    
    Acciones soportadas:
    - addRequestService: Crear nueva solicitud
    - getMyRequests: Obtener solicitudes del usuario
    - getViewHistoricalRequestService: Ver historial de una solicitud
    - correctRequestService: Corregir una solicitud
    - delRequestService: Eliminar una solicitud
    """
    try:
        # Obtener datos del estudiante desde el payload o request
        solicitante_id = None
        perfil_id = None
        
        # Intentar obtener desde diferentes fuentes
        if request.method == "POST":
            if 'multipart/form-data' in request.content_type:
                eRequest = request.POST
                eFiles = request.FILES
            else:
                try:
                    data = json.loads(request.body)
                    eRequest = data
                    eFiles = {}
                except:
                    eRequest = request.POST
                    eFiles = request.FILES
        else:
            eRequest = request.GET
            eFiles = {}
        
        # Obtener action
        action = eRequest.get('action')
        if not action:
            return JsonResponse({
                "isSuccess": False,
                "data": {},
                "message": "Parámetro 'action' no encontrado"
            }, status=200)
        
        # Obtener solicitante_id desde diferentes fuentes
        # 1. Desde payload del frontend (si existe)
        try:
            if 'payload' in eRequest:
                payload_str = eRequest['payload']
                if isinstance(payload_str, str):
                    payload = json.loads(payload_str)
                else:
                    payload = payload_str
                
                perfil_info = payload.get('perfilprincipal') or payload.get('perfil')
                if perfil_info:
                    if isinstance(perfil_info, dict):
                        perfil_id = perfil_info.get('id')
                    elif isinstance(perfil_info, str):
                        try:
                            perfil_id = decrypt(perfil_info)
                        except:
                            perfil_id = None
                
                # Obtener persona_id desde payload
                persona_info = payload.get('persona') or payload.get('persona_id')
                if persona_info:
                    if isinstance(persona_info, dict):
                        solicitante_id = persona_info.get('id')
                    elif isinstance(persona_info, (int, str)):
                        try:
                            solicitante_id = int(persona_info)
                        except:
                            solicitante_id = decrypt(str(persona_info)) if isinstance(persona_info, str) else None
        except Exception as e:
            print(f"⚠️ [BalconServiciosAPI] Error obteniendo payload: {e}")
        
        # 2. Si no se obtuvo, intentar desde data_unemi.json usando cédula
        if not solicitante_id:
            try:
                usuario_cedula = eRequest.get('usuario') or eRequest.get('cedula')
                if usuario_cedula and perfil_id:
                    student_data = _load_student_data_from_unemi(usuario_cedula, str(perfil_id))
                    if student_data:
                        persona = student_data.get('persona', {})
                        solicitante_id = persona.get('id')
            except Exception as e:
                print(f"⚠️ [BalconServiciosAPI] Error cargando desde data_unemi: {e}")
        
        # 3. Fallback: usar ID ficticio basado en cédula o perfil
        if not solicitante_id:
            # Para simulación, usar un ID basado en cédula o perfil
            usuario_cedula = eRequest.get('usuario') or eRequest.get('cedula') or '0000000000'
            # Generar ID ficticio pero consistente
            try:
                # Usar últimos 6 dígitos de la cédula como base
                solicitante_id = int(usuario_cedula[-6:]) if len(usuario_cedula) >= 6 else hash(usuario_cedula) % 1000000
            except:
                solicitante_id = hash(str(usuario_cedula)) % 1000000
        
        print(f"🔍 [BalconServiciosAPI] Action: {action}, Solicitante ID: {solicitante_id}")
        
        # Procesar acciones
        if action == 'addRequestService':
            # Crear nueva solicitud
            try:
                # Obtener datos del request
                descripcion = eRequest.get('descripcion', '').strip()
                if not descripcion:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "La descripción es obligatoria"
                    }, status=200)
                
                tipo = int(eRequest.get('tipo', '2'))
                servicio_nombre = eRequest.get('servicio_nombre', 'Solicitud General')
                servicio_sigla = eRequest.get('servicio_sigla', 'GEN')
                departamento = eRequest.get('departamento', 'DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS')
                
                # Obtener archivo de solicitud
                archivo_solicitud = eFiles.get('file_uprequest')
                
                # Obtener requisitos
                requisitos = []
                for key, value in eFiles.items():
                    if key.startswith('file_requirement_'):
                        req_id_str = key.replace('file_requirement_', '')
                        try:
                            req_id = decrypt(req_id_str)
                            requisitos.append({
                                "requisito_id": req_id,
                                "archivo": value
                            })
                        except:
                            pass
                
                # Crear solicitud
                solicitud = crear_solicitud(
                    solicitante_id=solicitante_id,
                    descripcion=descripcion,
                    tipo=tipo,
                    archivo_solicitud=archivo_solicitud,
                    servicio_nombre=servicio_nombre,
                    servicio_sigla=servicio_sigla,
                    departamento=departamento,
                    agente_id=None,  # Se asignará automáticamente
                    agente_nombre="Sistema",
                    carrera_id=None,
                    requisitos=requisitos if requisitos else None
                )
                
                return JsonResponse({
                    "isSuccess": True,
                    "data": {
                        "urlservice": None,
                        "solicitud_id": encrypt(solicitud['id'])
                    }
                }, status=200)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    "isSuccess": False,
                    "data": {},
                    "message": f"Error al crear solicitud: {str(e)}"
                }, status=200)
        
        elif action == 'getMyRequests':
            # Obtener solicitudes del usuario
            try:
                solicitudes = obtener_solicitudes_usuario(solicitante_id)
                
                # Encriptar IDs para respuesta
                for sol in solicitudes:
                    sol['id'] = encrypt(sol['id'])
                
                return JsonResponse({
                    "isSuccess": True,
                    "data": {
                        "eBalconyRequests": solicitudes,
                        "cantSolicitudesSinResponderEncuesta": 0,
                        "mensajeResponderEncuesta": ""
                    }
                }, status=200)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    "isSuccess": False,
                    "data": {},
                    "message": f"Error al obtener solicitudes: {str(e)}"
                }, status=200)
        
        elif action == 'getViewHistoricalRequestService':
            # Ver historial de una solicitud
            try:
                solicitud_id_enc = eRequest.get('id')
                if not solicitud_id_enc:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "ID de solicitud no proporcionado"
                    }, status=200)
                
                solicitud_id = decrypt(solicitud_id_enc)
                historial_data = obtener_historial_solicitud(solicitud_id)
                
                if not historial_data:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "Solicitud no encontrada"
                    }, status=200)
                
                # Encriptar IDs
                historial_data['eBalconyRequest']['id'] = encrypt(historial_data['eBalconyRequest']['id'])
                for hist in historial_data['eBalconyRequestHistories']:
                    hist['id'] = encrypt(hist['id'])
                
                return JsonResponse({
                    "isSuccess": True,
                    "data": historial_data
                }, status=200)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    "isSuccess": False,
                    "data": {},
                    "message": f"Error al obtener historial: {str(e)}"
                }, status=200)
        
        elif action == 'correctRequestService':
            # Corregir solicitud
            try:
                solicitud_id_enc = eRequest.get('id')
                if not solicitud_id_enc:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "ID de solicitud no proporcionado"
                    }, status=200)
                
                solicitud_id = decrypt(solicitud_id_enc)
                descripcion_correccion = eRequest.get('descripcion', '').strip()
                archivo = eFiles.get('file_uprequest')
                
                if not descripcion_correccion:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "La descripción de corrección es obligatoria"
                    }, status=200)
                
                success = corregir_solicitud(
                    solicitud_id=solicitud_id,
                    descripcion_correccion=descripcion_correccion,
                    archivo=archivo
                )
                
                if success:
                    return JsonResponse({
                        "isSuccess": True,
                        "data": {}
                    }, status=200)
                else:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "No se pudo corregir la solicitud. Verifique que esté en estado CORRECCIÓN."
                    }, status=200)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    "isSuccess": False,
                    "data": {},
                    "message": f"Error al corregir solicitud: {str(e)}"
                }, status=200)
        
        elif action == 'delRequestService':
            # Eliminar solicitud
            try:
                solicitud_id_enc = eRequest.get('id')
                if not solicitud_id_enc:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "ID de solicitud no proporcionado"
                    }, status=200)
                
                solicitud_id = decrypt(solicitud_id_enc)
                success = eliminar_solicitud(solicitud_id, solicitante_id)
                
                if success:
                    return JsonResponse({
                        "isSuccess": True,
                        "data": {}
                    }, status=200)
                else:
                    return JsonResponse({
                        "isSuccess": False,
                        "data": {},
                        "message": "No se pudo eliminar la solicitud. Solo se pueden eliminar solicitudes en estado INGRESADO o LEIDO."
                    }, status=200)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    "isSuccess": False,
                    "data": {},
                    "message": f"Error al eliminar solicitud: {str(e)}"
                }, status=200)
        
        else:
            return JsonResponse({
                "isSuccess": False,
                "data": {},
                "message": f"Acción '{action}' no reconocida"
            }, status=200)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "isSuccess": False,
            "data": {},
            "message": f"Error en el servidor: {str(e)}"
        }, status=500)



# app/services/student_data_service.py
"""
Servicio para manejo de datos del estudiante.
Funciones para extraer y responder consultas usando solo student_data (sin LLM ni PrivateGPT).
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from .solicitud_service import obtener_solicitudes_usuario


# Intenciones que se pueden responder SOLO con student_data (sin LLM ni PrivateGPT)
DATA_INTENTS = {
    "consultar_solicitudes_balcon",
    "consultar_carrera_actual",
    "consultar_roles_usuario",
    "consultar_datos_personales",
}

# Campos seguros que se pueden mostrar del JSON (whitelist)
SAFE_PERSON_FIELDS = {
    "nombres", "apellido1", "apellido2", "emailinst", "email"
}


def capitalize_name(name: str) -> str:
    """
    Capitaliza un nombre correctamente: solo la primera letra de cada palabra en mayúscula.
    
    Args:
        name: Nombre a capitalizar
    
    Returns:
        Nombre capitalizado correctamente
    """
    if not name:
        return ""
    
    # Dividir por espacios y capitalizar cada palabra
    palabras = name.strip().split()
    palabras_capitalizadas = []
    
    for palabra in palabras:
        if palabra:
            # Capitalizar: primera letra mayúscula, resto minúsculas
            palabra_capitalizada = palabra[0].upper() + palabra[1:].lower() if len(palabra) > 1 else palabra.upper()
            palabras_capitalizadas.append(palabra_capitalizada)
    
    return " ".join(palabras_capitalizadas)


def get_student_name(student_data: Optional[Dict]) -> str:
    """
    Obtiene el nombre completo del estudiante desde student_data.
    Busca en múltiples ubicaciones posibles y lo capitaliza correctamente.
    
    Args:
        student_data: Datos completos del usuario desde data_unemi.json
    
    Returns:
        Nombre completo del estudiante capitalizado correctamente o cadena vacía si no se encuentra
    """
    if not student_data:
        return ""
    
    nombre_sin_capitalizar = ""
    
    # Prioridad 1: contexto.credenciales.nombre_completo
    contexto = student_data.get("contexto", {})
    if contexto:
        credenciales = contexto.get("credenciales", {})
        if credenciales:
            nombre = credenciales.get("nombre_completo", "").strip()
            if nombre:
                nombre_sin_capitalizar = nombre
    
    # Prioridad 2: persona.nombres + apellidos
    if not nombre_sin_capitalizar:
        persona = student_data.get("persona", {})
        if persona:
            nombres = persona.get("nombres", "").strip()
            apellido1 = persona.get("apellido1", "").strip()
            apellido2 = persona.get("apellido2", "").strip()
            if nombres:
                nombre_completo = f"{nombres} {apellido1} {apellido2}".strip()
                if nombre_completo:
                    nombre_sin_capitalizar = nombre_completo
    
    # Prioridad 3: datos_personales.nombres + apellidos
    if not nombre_sin_capitalizar:
        datos_personales = contexto.get("datos_personales", {}) if contexto else {}
        if datos_personales:
            nombres = datos_personales.get("nombres", "").strip()
            apellido_paterno = datos_personales.get("apellido_paterno", "").strip()
            apellido_materno = datos_personales.get("apellido_materno", "").strip()
            if nombres:
                nombre_completo = f"{nombres} {apellido_paterno} {apellido_materno}".strip()
                if nombre_completo:
                    nombre_sin_capitalizar = nombre_completo
    
    # Prioridad 4: credenciales directo (sin contexto)
    if not nombre_sin_capitalizar:
        credenciales_directo = student_data.get("credenciales", {})
        if credenciales_directo:
            nombre = credenciales_directo.get("nombre_completo", "").strip()
            if nombre:
                nombre_sin_capitalizar = nombre
    
    # Capitalizar el nombre antes de retornarlo
    return capitalize_name(nombre_sin_capitalizar)


def get_current_student_profile(student_data: Dict) -> Optional[Dict]:
    """
    Obtiene el perfil de estudiante activo principal del student_data.
    
    Prioriza perfiles con inscripcionprincipal=True, luego el más reciente.
    """
    if not student_data:
        return None
    
    perfiles = student_data.get("perfiles", [])
    if not perfiles:
        # Intentar desde contexto si viene en formato diferente
        contexto = student_data.get("contexto", {})
        if contexto:
            # Si viene del formato del API, no tiene perfiles directamente
            return None
    
    # Buscar perfiles activos de estudiante
    candidatos = [
        p for p in perfiles
        if p.get("status") and p.get("es_estudiante") and p.get("inscripcionprincipal")
    ]
    
    # Si no hay principal, buscar cualquier estudiante activo
    if not candidatos:
        candidatos = [
            p for p in perfiles
            if p.get("status") and p.get("es_estudiante")
        ]
    
    if not candidatos:
        return None
    
    # Retornar el más reciente (por fecha_creacion)
    return sorted(candidatos, key=lambda p: p.get("fecha_creacion") or "")[-1]


def extract_carrera_data(student_data: Dict) -> Optional[Dict[str, str]]:
    """
    Extrae datos de carrera desde cualquier ubicación posible en student_data.
    
    Returns:
        Dict con keys: carrera, facultad, modalidad, o None si no se encuentra
    """
    # Prioridad 1: informacion_academica directa
    info_academica = student_data.get("informacion_academica", {})
    if info_academica.get("carrera"):
        return {
            "carrera": info_academica.get("carrera", ""),
            "facultad": info_academica.get("facultad", ""),
            "modalidad": info_academica.get("modalidad", "")
        }
    
    # Prioridad 2: contexto.informacion_academica
    contexto = student_data.get("contexto", {})
    if contexto:
        info_academica = contexto.get("informacion_academica", {})
        if info_academica.get("carrera"):
            return {
                "carrera": info_academica.get("carrera", ""),
                "facultad": info_academica.get("facultad", ""),
                "modalidad": info_academica.get("modalidad", "")
            }
    
    # Prioridad 3: perfiles
    perfil = get_current_student_profile(student_data)
    if perfil:
        return {
            "carrera": perfil.get("carrera_nombre", ""),
            "facultad": perfil.get("facultad_nombre", ""),
            "modalidad": perfil.get("modalidad_nombre", "")
        }
    
    return None


def extract_user_role(student_data: Optional[Dict], perfil_id: Optional[str] = None) -> str:
    """
    Extrae el rol del usuario desde student_data.
    
    Funciona tanto con los datos completos de data_unemi.json como con el payload
    reducido que envía el frontend (que suele incluir solo un perfil).
    """
    if not isinstance(student_data, dict):
        return "usuario"
    
    def _collect_perfiles(origen: Optional[Dict]) -> List[Dict]:
        perfiles_colectados: List[Dict] = []
        if not isinstance(origen, dict):
            return perfiles_colectados
        
        posibles_listas = [
            origen.get("perfiles"),
            origen.get("contexto", {}).get("perfiles") if isinstance(origen.get("contexto"), dict) else None,
        ]
        for posible in posibles_listas:
            if isinstance(posible, list):
                perfiles_colectados.extend([p for p in posible if isinstance(p, dict)])
        
        posibles_individuales = [
            origen.get("perfil"),
            origen.get("perfilprincipal"),
            origen.get("perfil_actual"),
            origen.get("contexto", {}).get("perfil") if isinstance(origen.get("contexto"), dict) else None,
            origen.get("contexto", {}).get("perfilprincipal") if isinstance(origen.get("contexto"), dict) else None,
        ]
        for posible in posibles_individuales:
            if isinstance(posible, dict):
                perfiles_colectados.append(posible)
        
        return perfiles_colectados
    
    perfiles = _collect_perfiles(student_data)
    
    # En algunos casos el student_data ES el perfil (payload reducido del frontend)
    perfil_parece_directo = any(
        key in student_data
        for key in ("es_estudiante", "es_profesor", "es_administrativo", "rol", "tipo")
    )
    if perfil_parece_directo:
        perfiles.append(student_data)
    
    # Limpiar duplicados (por id)
    vistos: set[str] = set()
    perfiles_filtrados: list[Dict] = []
    for perfil in perfiles:
        perfil_id_actual = perfil.get("id")
        key = str(perfil_id_actual) if perfil_id_actual is not None else str(id(perfil))
        if key not in vistos:
            vistos.add(key)
            perfiles_filtrados.append(perfil)
    
    if not perfiles_filtrados:
        rol_directo = student_data.get("rol") or student_data.get("role")
        if isinstance(rol_directo, str) and rol_directo.strip():
            return rol_directo.strip().lower()
        return "usuario"
    
    def _perfil_activo(perfil: Dict) -> bool:
        if isinstance(perfil.get("status"), bool):
            return perfil["status"]
        if isinstance(perfil.get("activo"), bool):
            return perfil["activo"]
        return True  # asume activo si no se especifica
    
    perfiles_activos = [p for p in perfiles_filtrados if _perfil_activo(p)]
    if not perfiles_activos:
        perfiles_activos = perfiles_filtrados
    
    def _coincide_id(perfil: Dict, objetivo: Optional[str]) -> bool:
        if objetivo is None:
            return False
        return str(perfil.get("id")) == str(objetivo)
    
    perfil_seleccionado = None
    if perfil_id:
        perfil_seleccionado = next(
            (p for p in perfiles_activos if _coincide_id(p, perfil_id)),
            None
        )
    
    if not perfil_seleccionado:
        perfil_seleccionado = next(
            (p for p in perfiles_activos if p.get("inscripcionprincipal") or p.get("principal")),
            None
        )
    
    if not perfil_seleccionado and perfiles_activos:
        perfil_seleccionado = perfiles_activos[0]
    
    if not perfil_seleccionado:
        return "usuario"
    
    # Determinar rol según flags del perfil
    if perfil_seleccionado.get("es_estudiante"):
        return "estudiante"
    if perfil_seleccionado.get("es_profesor"):
        return "profesor"
    if perfil_seleccionado.get("es_administrativo"):
        return "administrativo"
    if perfil_seleccionado.get("es_externo"):
        return "externo"
    if perfil_seleccionado.get("es_postulanteempleo"):
        return "postulante_empleo"
    if perfil_seleccionado.get("es_postulante"):
        return "postulante"
    
    rol_explicito = perfil_seleccionado.get("rol") or perfil_seleccionado.get("role")
    if isinstance(rol_explicito, str) and rol_explicito.strip():
        return rol_explicito.strip().lower()
    
    # Fallback: usar el tipo del perfil
    tipo = (perfil_seleccionado.get("tipo") or "").upper()
    if "ESTUDIANTE" in tipo or "INGENIER" in tipo or "SOFTWARE" in tipo or "ADMISI" in tipo:
        return "estudiante"
    if "PROFESOR" in tipo:
        return "profesor"
    if "ADMINISTRATIVO" in tipo:
        return "administrativo"
    if "EXTERNO" in tipo:
        return "externo"
    if "POSTULANTE" in tipo:
        return "postulante"
    
    return "usuario"


def answer_solicitudes_balcon(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre las solicitudes del balcón consultando el servicio de solicitudes.
    Usa el servicio de solicitudes para obtener datos actualizados.
    """
    # Obtener ID del solicitante desde student_data
    solicitante_id = None
    if student_data:
        persona = student_data.get("persona", {})
        solicitante_id = persona.get("id")
    
    # Si no hay ID, generar uno basado en cédula
    if not solicitante_id:
        cedula = (
            student_data.get("datos_personales", {}).get("cedula") or
            student_data.get("cedula") or
            "0000000000"
        )
        try:
            solicitante_id = int(cedula[-6:]) if len(cedula) >= 6 else hash(cedula) % 1000000
        except:
            solicitante_id = hash(str(cedula)) % 1000000
    
    # Consultar solicitudes desde el servicio
    try:
        solicitudes = obtener_solicitudes_usuario(solicitante_id)
    except Exception as e:
        print(f"⚠️ [AnswerSolicitudes] Error obteniendo solicitudes: {e}")
        solicitudes = []
    
    # Si no hay solicitudes desde el servicio, intentar desde student_data como fallback
    if not solicitudes:
        solicitudes_data = (
            student_data.get("solicitudes_balcon") or 
            student_data.get("solicitudes") or
            student_data.get("contexto", {}).get("solicitudes") or
            student_data.get("contexto", {}).get("solicitudes_balcon") or
            []
        )
        
        # Convertir formato de student_data al formato esperado
        for s in solicitudes_data:
            solicitudes.append({
                "codigo": s.get("codigo_generado") or s.get("codigo") or "SIN CÓDIGO",
                "estado_display": s.get("estado_display") or s.get("estado") or "Sin estado",
                "nombre_servicio_minus": s.get("tipo") or s.get("descripcion", "")[:50] or "Sin servicio",
                "fecha_creacion": s.get("fecha_creacion") or s.get("fecha") or "",
                "fecha_creacion_v2": s.get("fecha_creacion_v2") or ""
            })
    
    if not solicitudes:
        return {
            "summary": "No tienes solicitudes registradas en el Balcón de Servicios.",
            "has_information": True,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    # Formatear respuesta
    lineas = []
    for s in solicitudes:
        codigo = s.get("codigo", "SIN CÓDIGO")
        estado = s.get("estado_display", "Sin estado")
        servicio = s.get("nombre_servicio_minus", "Solicitud General")
        
        # Formatear fecha
        fecha_display = s.get("fecha_creacion_v2", "")
        if not fecha_display:
            fecha_str = s.get("fecha_creacion", "")
            if fecha_str:
                try:
                    if "T" in fecha_str:
                        fecha_obj = datetime.fromisoformat(fecha_str.replace("Z", "+00:00"))
                        fecha_display = fecha_obj.strftime("%d/%m/%Y")
                    else:
                        fecha_display = fecha_str[:10]
                except:
                    fecha_display = fecha_str[:10] if len(fecha_str) >= 10 else fecha_str
        
        linea = f"- **{codigo}** · {servicio} · {estado}"
        if fecha_display:
            linea += f" · {fecha_display}"
        lineas.append(linea)
    
    texto = (
        "Aquí tienes tus solicitudes en el Balcón de Servicios:\n\n" +
        "\n".join(lineas) +
        "\n\nPuedes preguntar por el estado de una solicitud específica o ver más detalles."
    )
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def build_carrera_response(carrera_data: Dict[str, str], intent_slots: Dict) -> Dict[str, Any]:
    """Construye la respuesta sobre carrera desde datos extraídos."""
    carrera = carrera_data.get("carrera", "").strip()
    facultad = carrera_data.get("facultad", "").strip()
    modalidad = carrera_data.get("modalidad", "").strip()
    
    if not carrera:
        return {
            "summary": "No encuentro información de tu carrera en el sistema. Por favor, verifica que hayas seleccionado el perfil correcto.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    texto = f"Estás estudiando la carrera de **{carrera}**"
    if facultad:
        texto += f" en la **{facultad}**"
    if modalidad:
        texto += f", en modalidad **{modalidad}**"
    texto += "."
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def answer_carrera_actual(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre la carrera actual usando solo student_data.
    No usa LLM ni PrivateGPT.
    """
    carrera_data = extract_carrera_data(student_data)
    if not carrera_data:
        return {
            "summary": "No encuentro información de tu carrera en el sistema. Por favor, verifica que hayas seleccionado el perfil correcto.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    return build_carrera_response(carrera_data, intent_slots)


def answer_roles_usuario(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre los roles/perfiles del usuario usando solo student_data.
    No usa LLM ni PrivateGPT.
    """
    perfiles = student_data.get("perfiles", [])
    if not perfiles:
        # Intentar desde contexto
        contexto = student_data.get("contexto", {})
        if contexto:
            return {
                "summary": "No encuentro información de perfiles para este usuario.",
                "has_information": False,
                "from_student_data": True,
                "source_pdfs": [],
                "fuentes": [],
                "category": None,
                "subcategory": None,
                "confidence": 1.0,
                "campos_requeridos": [],
                "needs_confirmation": False,
                "confirmed": True,
                "intent_slots": intent_slots,
            }
    
    # Filtrar solo perfiles activos
    perfiles_activos = [p for p in perfiles if p.get("status")]
    
    if not perfiles_activos:
        return {
            "summary": "No tienes perfiles activos registrados.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    roles = []
    for p in perfiles_activos:
        tipo = p.get("tipo") or "Sin tipo"
        rol_parts = []
        
        if p.get("es_estudiante"):
            rol_parts.append("Estudiante")
        if p.get("es_profesor"):
            rol_parts.append("Profesor")
        if p.get("es_administrativo"):
            rol_parts.append("Administrativo")
        if p.get("es_externo"):
            rol_parts.append("Externo")
        
        rol_str = " · ".join(rol_parts) if rol_parts else "Sin rol específico"
        roles.append(f"- **{tipo}**: {rol_str}")
    
    texto = (
        f"Tienes {len(perfiles_activos)} perfil(es) activo(s):\n\n" +
        "\n".join(roles)
    )
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def answer_datos_personales(student_data: Dict, intent_slots: Dict) -> Dict[str, Any]:
    """
    Responde sobre datos personales básicos usando solo student_data.
    Solo muestra campos seguros (whitelist).
    No usa LLM ni PrivateGPT.
    """
    # Obtener datos desde diferentes ubicaciones
    persona = student_data.get("persona", {})
    contexto = student_data.get("contexto", {})
    credenciales = contexto.get("credenciales", {}) if contexto else {}
    datos_personales = contexto.get("datos_personales", {}) if contexto else {}
    
    # Construir respuesta solo con campos seguros
    partes = []
    
    # Nombre
    nombre_completo = (
        credenciales.get("nombre_completo") or
        datos_personales.get("nombres") or
        persona.get("nombres", "")
    )
    if nombre_completo:
        apellido1 = datos_personales.get("apellido_paterno") or persona.get("apellido1", "")
        apellido2 = datos_personales.get("apellido_materno") or persona.get("apellido2", "")
        if apellido1 or apellido2:
            nombre_completo = f"{nombre_completo} {apellido1} {apellido2}".strip()
        partes.append(f"**Nombre completo**: {nombre_completo}")
    
    # Email institucional
    email_inst = (
        datos_personales.get("email") or
        persona.get("emailinst") or
        persona.get("email", "")
    )
    if email_inst:
        partes.append(f"**Email institucional**: {email_inst}")
    
    if not partes:
        return {
            "summary": "No encuentro datos personales disponibles para mostrar.",
            "has_information": False,
            "from_student_data": True,
            "source_pdfs": [],
            "fuentes": [],
            "category": None,
            "subcategory": None,
            "confidence": 1.0,
            "campos_requeridos": [],
            "needs_confirmation": False,
            "confirmed": True,
            "intent_slots": intent_slots,
        }
    
    texto = "Aquí tienes tus datos personales:\n\n" + "\n".join(partes)
    
    return {
        "summary": texto,
        "has_information": True,
        "from_student_data": True,
        "source_pdfs": [],
        "fuentes": [],
        "category": None,
        "subcategory": None,
        "confidence": 1.0,
        "campos_requeridos": [],
        "needs_confirmation": False,
        "confirmed": True,
        "intent_slots": intent_slots,
    }


def maybe_answer_with_student_data(intent_slots: Dict, student_data: Dict) -> Optional[Dict[str, Any]]:
    """
    Intenta responder usando solo student_data si el intent_code está en DATA_INTENTS.
    
    Retorna None si no se puede responder con datos, o un dict con la respuesta si sí.
    """
    if not student_data:
        return None
    
    intent_code = intent_slots.get("intent_code", "").strip()
    
    if not intent_code or intent_code not in DATA_INTENTS:
        return None
    
    print(f"📊 [Data Intent] Detectado intent_code: '{intent_code}' - Respondiendo con student_data")
    
    try:
        if intent_code == "consultar_solicitudes_balcon":
            return answer_solicitudes_balcon(student_data, intent_slots)
        
        elif intent_code == "consultar_carrera_actual":
            return answer_carrera_actual(student_data, intent_slots)
        
        elif intent_code == "consultar_roles_usuario":
            return answer_roles_usuario(student_data, intent_slots)
        
        elif intent_code == "consultar_datos_personales":
            return answer_datos_personales(student_data, intent_slots)
        
    except Exception as e:
        import traceback
        print(f"⚠️ [Data Intent] Error al responder con student_data: {e}")
        traceback.print_exc()
        return None
    
    return None


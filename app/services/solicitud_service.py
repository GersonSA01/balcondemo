"""
Servicio para manejar solicitudes del balcón de servicios usando JSON como almacenamiento.
Simula el comportamiento del sistema real sin necesidad de base de datos.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


SOLICITUDES_JSON_FILE = "solicitudes_balcon.json"
MEDIA_SOLICITUDES = "solicitudbalcon"
MEDIA_HISTORIAL = "solicitudbalconhistorial"
MEDIA_REQUISITOS = "solicitudbalconrequisitos"

# Estados de solicitud
ESTADO_INGRESADO = 1
ESTADO_RECHAZADO = 2
ESTADO_EN_TRAMITE = 3
ESTADO_APROBADO = 4
ESTADO_ATENDIDO = 5
ESTADO_CORRECCION = 6
ESTADO_CERRADA = 7
ESTADO_LEIDO = 8

ESTADOS_SOLICITUD = {
    1: "INGRESADO",
    2: "RECHAZADO",
    3: "EN TRÁMITE",
    4: "APROBADO",
    5: "ATENDIDO",
    6: "CORRECCIÓN",
    7: "CERRADA",
    8: "LEIDO"
}

ESTADOS_HISTORIAL = {
    1: "INGRESADO",
    2: "EN TRÁMITE",
    3: "CORRECCIÓN",
    4: "ATENDIDO",
    5: "APROBADO",
    6: "RECHAZADO",
    7: "CERRADA",
    8: "LEIDO"
}

TIPO_INFORMACION = 1
TIPO_SOLICITUD = 2


def _get_solicitudes_file_path() -> Path:
    """Obtiene la ruta del archivo JSON de solicitudes."""
    return Path(__file__).resolve().parent.parent / "data" / SOLICITUDES_JSON_FILE


def _load_solicitudes() -> Dict[str, Any]:
    """Carga todas las solicitudes desde el archivo JSON."""
    file_path = _get_solicitudes_file_path()
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # Crear estructura inicial si no existe
            return {
                "solicitudes": [],
                "historiales": [],
                "requisitos": [],
                "next_id": 1,
                "next_historial_id": 1,
                "next_requisito_id": 1
            }
    except Exception as e:
        print(f"⚠️ [SolicitudService] Error cargando solicitudes: {e}")
        return {
            "solicitudes": [],
            "historiales": [],
            "requisitos": [],
            "next_id": 1,
            "next_historial_id": 1,
            "next_requisito_id": 1
        }


def _save_solicitudes(data: Dict[str, Any]) -> bool:
    """Guarda las solicitudes en el archivo JSON."""
    file_path = _get_solicitudes_file_path()
    try:
        # Crear directorio si no existe
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ [SolicitudService] Error guardando solicitudes: {e}")
        return False


def _generar_codigo_solicitud(sigla: str, numero: int) -> str:
    """Genera código único de solicitud: SOL-{SIGLA}-{AÑO}{MES}-{NUMERO}"""
    ahora = datetime.now()
    return f"SOL-{sigla}-{ahora.year}{ahora.month:02d}-{numero:06d}"


def _guardar_archivo(archivo, subdirectorio: str, nombre_base: str) -> Optional[str]:
    """Guarda un archivo en el sistema de archivos y retorna la ruta."""
    try:
        if not archivo:
            return None
        
        # Generar nombre único
        extension = os.path.splitext(archivo.name)[1] if hasattr(archivo, 'name') else '.pdf'
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        nombre_archivo = f"{nombre_base}_{timestamp}{extension}"
        
        # Ruta completa
        ruta_completa = f"{subdirectorio}/{nombre_archivo}"
        
        # Leer contenido del archivo
        if hasattr(archivo, 'read'):
            contenido = archivo.read()
        elif isinstance(archivo, bytes):
            contenido = archivo
        else:
            return None
        
        # Guardar usando Django storage
        file_obj = ContentFile(contenido)
        saved_path = default_storage.save(ruta_completa, file_obj)
        
        return saved_path
    except Exception as e:
        print(f"⚠️ [SolicitudService] Error guardando archivo: {e}")
        return None


def _añadir_solicitud_a_data_unemi(
    cedula: str,
    perfil_id: Optional[int],
    perfil_tipo: Optional[str],
    solicitud: Dict[str, Any]
) -> bool:
    """
    Añade una solicitud al archivo data_unemi.json según el perfil elegido.
    
    Args:
        cedula: Cédula del usuario
        perfil_id: ID del perfil activo
        perfil_tipo: Tipo/nombre del perfil activo
        solicitud: Dict con la solicitud creada
    
    Returns:
        True si se añadió exitosamente, False en caso contrario
    """
    try:
        data_unemi_path = Path(__file__).resolve().parent.parent / "data" / "data_unemi.json"
        if not data_unemi_path.exists():
            print(f"⚠️ [SolicitudService] data_unemi.json no existe, omitiendo actualización")
            return False
        
        with open(data_unemi_path, "r", encoding="utf-8") as f:
            data_unemi = json.load(f)
        
        # Buscar usuario por cédula (probar diferentes formatos)
        print(f"🔍 [SolicitudService] Buscando usuario con cédula: {cedula}")
        print(f"🔍 [SolicitudService] Total de usuarios en data_unemi: {len(data_unemi)}")
        
        usuario_data = None
        cedula_encontrada = None
        
        # Intentar diferentes formatos de cédula
        formatos_cedula = [
            cedula,  # Formato original
            cedula.lstrip('0'),  # Sin ceros iniciales
            cedula.zfill(10),  # Con ceros a la izquierda hasta 10 dígitos
            cedula.strip()  # Sin espacios
        ]
        
        for formato in formatos_cedula:
            if formato in data_unemi:
                usuario_data = data_unemi[formato]
                cedula_encontrada = formato
                print(f"✅ [SolicitudService] Usuario encontrado con formato: {formato}")
                break
        
        if not usuario_data:
            # Si aún no se encuentra, buscar por coincidencia parcial en las claves
            print(f"⚠️ [SolicitudService] Usuario {cedula} no encontrado con formatos estándar")
            print(f"🔍 [SolicitudService] Buscando coincidencias parciales...")
            for key in data_unemi.keys():
                if cedula in key or key in cedula:
                    usuario_data = data_unemi[key]
                    cedula_encontrada = key
                    print(f"✅ [SolicitudService] Usuario encontrado por coincidencia parcial: {key}")
                    break
        
        if not usuario_data:
            print(f"❌ [SolicitudService] Usuario {cedula} no encontrado en data_unemi.json")
            print(f"   Formatos intentados: {formatos_cedula}")
            print(f"   Primeras 5 claves disponibles: {list(data_unemi.keys())[:5]}")
            return False
        
        # Preparar solicitud en formato data_unemi
        solicitud_data_unemi = {
            "id": solicitud.get("id"),
            "fecha_creacion": solicitud.get("fecha_creacion"),
            "fecha_modificacion": solicitud.get("fecha_modificacion"),
            "codigo": solicitud.get("codigo", ""),
            "estado": solicitud.get("estado"),
            "tipo": solicitud.get("tipo"),
            "archivo": solicitud.get("archivo"),
            "descripcion": solicitud.get("descripcion"),
            "perfil": perfil_id,
            "externo": False,
            "numero": solicitud.get("numero"),
            "tiempoespera": 0,
            "tiempoesperareal": 0,
            "solicitud_devuelta": False,
            "fecha_expiracion_solicitud": solicitud.get("fecha_expiracion_solicitud"),
            "solicitudasociada": None,
            "estado_display": ESTADOS_SOLICITUD.get(solicitud.get("estado"), "INGRESADO"),
            "tipo_display": "SOLICITUD" if solicitud.get("tipo") == 2 else "INFORMACIÓN",
            "codigo_generado": solicitud.get("codigo"),
            "perfil_id": perfil_id,
            "perfil_tipo": perfil_tipo or "SIN PERFIL",
            "agente_id": solicitud.get("agente_id"),
            "agente_nombre": "Sistema",
            "agenteactual_id": solicitud.get("agente_id"),
            "agenteactual_nombre": "Sistema",
            "historial": [],
            "requisitos": [],
            "respuestas_encuesta": []
        }
        
        # Asegurar que existe el array solicitudes_balcon
        if "solicitudes_balcon" not in usuario_data:
            usuario_data["solicitudes_balcon"] = []
        
        # Añadir solicitud al inicio del array
        usuario_data["solicitudes_balcon"].insert(0, solicitud_data_unemi)
        
        # Guardar archivo
        with open(data_unemi_path, "w", encoding="utf-8") as f:
            json.dump(data_unemi, f, ensure_ascii=False, indent=2)
        
        print(f"✅ [SolicitudService] Solicitud añadida a data_unemi.json para usuario {cedula}, perfil {perfil_id}")
        return True
        
    except Exception as e:
        print(f"⚠️ [SolicitudService] Error añadiendo solicitud a data_unemi.json: {e}")
        import traceback
        traceback.print_exc()
        return False


def crear_solicitud(
    solicitante_id: int,
    descripcion: str,
    tipo: int = TIPO_SOLICITUD,
    archivo_solicitud: Optional[Any] = None,
    servicio_nombre: str = "Solicitud General",
    servicio_sigla: str = "GEN",
    departamento: str = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    agente_id: Optional[int] = None,
    agente_nombre: Optional[str] = None,
    carrera_id: Optional[int] = None,
    requisitos: Optional[List[Dict]] = None,
    cedula: Optional[str] = None,
    perfil_id: Optional[int] = None,
    perfil_tipo: Optional[str] = None
) -> Dict[str, Any]:
    """
    Crea una nueva solicitud en el sistema.
    
    Args:
        solicitante_id: ID de la persona que solicita
        descripcion: Descripción de la solicitud
        tipo: Tipo de solicitud (1=INFORMACIÓN, 2=SOLICITUD)
        archivo_solicitud: Archivo adjunto (opcional)
        servicio_nombre: Nombre del servicio
        servicio_sigla: Sigla del servicio para el código
        departamento: Departamento al que se asigna
        agente_id: ID del agente asignado
        agente_nombre: Nombre del agente asignado
        carrera_id: ID de la carrera del estudiante
        requisitos: Lista de requisitos con archivos [{"requisito_id": int, "archivo": file}]
    
    Returns:
        Dict con la solicitud creada
    """
    data = _load_solicitudes()
    
    # Obtener siguiente ID y número de solicitud
    solicitud_id = data.get("next_id", 1)
    data["next_id"] = solicitud_id + 1
    
    # Obtener último número de solicitud del estudiante
    solicitudes_estudiante = [
        s for s in data["solicitudes"] 
        if s.get("solicitante_id") == solicitante_id
    ]
    ultimo_numero = max([s.get("numero", 0) for s in solicitudes_estudiante], default=0)
    numero_solicitud = ultimo_numero + 1
    
    # Generar código
    codigo = _generar_codigo_solicitud(servicio_sigla, solicitud_id)
    
    # Guardar archivo si existe
    ruta_archivo = None
    if archivo_solicitud:
        ruta_archivo = _guardar_archivo(archivo_solicitud, MEDIA_SOLICITUDES, "solicitud")
    
    # Crear solicitud
    ahora = datetime.now()
    solicitud = {
        "id": solicitud_id,
        "codigo": codigo,
        "solicitante_id": solicitante_id,
        "agente_id": agente_id,
        "estado": ESTADO_INGRESADO,
        "tipo": tipo,
        "archivo": ruta_archivo,
        "descripcion": descripcion.upper().strip(),
        "numero": numero_solicitud,
        "fecha_creacion": ahora.isoformat(),
        "fecha_modificacion": ahora.isoformat(),
        "fecha_expiracion_solicitud": None,
        "servicio": {
            "id": 0,  # ID ficticio para simulación
            "nombre": servicio_nombre,
            "proceso": {
                "id": 0,
                "sigla": servicio_sigla,
                "descripcion": servicio_nombre.upper()
            }
        }
    }
    
    data["solicitudes"].append(solicitud)
    
    # Crear historial inicial
    historial_id = data.get("next_historial_id", 1)
    data["next_historial_id"] = historial_id + 1
    
    historial = {
        "id": historial_id,
        "solicitud_id": solicitud_id,
        "estado": ESTADO_INGRESADO,
        "observacion": "Solicitud recibida en el sistema. Se procederá a revisar la documentación adjunta.",
        "asignadorecibe_id": agente_id,
        "asignadorecibe": agente_nombre or "Sistema",
        "departamento": departamento,
        "carrera_id": carrera_id,
        "archivo": None,
        "fecha_creacion": ahora.isoformat(),
        "servicio": servicio_nombre
    }
    
    data["historiales"].append(historial)
    
    # Guardar requisitos si existen
    if requisitos:
        for req in requisitos:
            requisito_id = data.get("next_requisito_id", 1)
            data["next_requisito_id"] = requisito_id + 1
            
            ruta_req = None
            if req.get("archivo"):
                ruta_req = _guardar_archivo(
                    req["archivo"], 
                    MEDIA_REQUISITOS, 
                    f"requisito_{req.get('requisito_id', requisito_id)}"
                )
            
            requisito = {
                "id": requisito_id,
                "solicitud_id": solicitud_id,
                "requisito_id": req.get("requisito_id"),
                "archivo": ruta_req,
                "fecha_creacion": ahora.isoformat()
            }
            data["requisitos"].append(requisito)
    
    # Guardar datos
    _save_solicitudes(data)
    
    # Añadir solicitud a data_unemi.json si se proporciona cédula y perfil
    print(f"🔍 [SolicitudService] Intentando añadir a data_unemi.json - cedula: {cedula}, perfil_id: {perfil_id}")
    if cedula and perfil_id:
        resultado = _añadir_solicitud_a_data_unemi(cedula, perfil_id, perfil_tipo, solicitud)
        if resultado:
            print(f"✅ [SolicitudService] Solicitud añadida exitosamente a data_unemi.json")
        else:
            print(f"⚠️ [SolicitudService] No se pudo añadir solicitud a data_unemi.json")
    else:
        print(f"⚠️ [SolicitudService] No se añadió a data_unemi.json - cedula o perfil_id faltantes")
    
    print(f"✅ [SolicitudService] Solicitud creada: {codigo} (ID: {solicitud_id})")
    
    return solicitud


def obtener_solicitudes_usuario(solicitante_id: int) -> List[Dict[str, Any]]:
    """
    Obtiene todas las solicitudes de un usuario.
    
    Args:
        solicitante_id: ID de la persona solicitante
    
    Returns:
        Lista de solicitudes con información formateada
    """
    data = _load_solicitudes()
    
    solicitudes = [
        s for s in data["solicitudes"]
        if s.get("solicitante_id") == solicitante_id
    ]
    
    # Formatear para respuesta API
    solicitudes_formateadas = []
    for sol in solicitudes:
        fecha_creacion = datetime.fromisoformat(sol["fecha_creacion"])
        
        solicitud_formateada = {
            "id": sol["id"],
            "numero": sol["numero"],
            "numero_display": f"{sol['numero']:05d}",
            "codigo": sol["codigo"],
            "descripcion": sol["descripcion"],
            "estado": sol["estado"],
            "estado_display": ESTADOS_SOLICITUD.get(sol["estado"], "DESCONOCIDO"),
            "fecha_creacion": sol["fecha_creacion"],
            "fecha_creacion_v2": fecha_creacion.strftime("%d/%m/%Y"),
            "hora_creacion_v2": fecha_creacion.strftime("%H:%M"),
            "nombre_servicio": sol.get("servicio", {}).get("nombre", "Solicitud General"),
            "nombre_servicio_minus": sol.get("servicio", {}).get("nombre", "Solicitud General"),
            "archivo": sol.get("archivo"),
            "typefile": os.path.splitext(sol.get("archivo", ""))[1] if sol.get("archivo") else None,
            "puede_calificar_proceso": False  # Por ahora siempre False
        }
        
        solicitudes_formateadas.append(solicitud_formateada)
    
    # Ordenar por fecha de creación descendente
    solicitudes_formateadas.sort(key=lambda x: x["fecha_creacion"], reverse=True)
    
    return solicitudes_formateadas


def obtener_historial_solicitud(solicitud_id: int) -> Dict[str, Any]:
    """
    Obtiene el historial completo de una solicitud.
    
    Args:
        solicitud_id: ID de la solicitud
    
    Returns:
        Dict con solicitud e historiales
    """
    data = _load_solicitudes()
    
    # Buscar solicitud
    solicitud = next(
        (s for s in data["solicitudes"] if s.get("id") == solicitud_id),
        None
    )
    
    if not solicitud:
        return None
    
    # Buscar historiales
    historiales = [
        h for h in data["historiales"]
        if h.get("solicitud_id") == solicitud_id
    ]
    
    # Ordenar por fecha
    historiales.sort(key=lambda x: x["fecha_creacion"])
    
    # Formatear historiales
    historiales_formateados = []
    colores_estado = {
        1: "#FF9900",  # INGRESADO - Naranja
        2: "#0dcaf0",  # EN TRÁMITE - Azul claro
        3: "#9E68DC",  # CORRECCIÓN - Morado
        4: "#0dcaf0",  # ATENDIDO - Azul claro
        5: "#209884",  # APROBADO - Verde
        6: "#E93939",  # RECHAZADO - Rojo
        7: "#0dcaf0",  # CERRADA - Azul claro
        8: "#5d6cb4"   # LEIDO - Azul oscuro
    }
    
    for hist in historiales:
        fecha_creacion = datetime.fromisoformat(hist["fecha_creacion"])
        
        historial_formateado = {
            "id": hist["id"],
            "estado": hist["estado"],
            "estado_display": ESTADOS_HISTORIAL.get(hist["estado"], "DESCONOCIDO"),
            "observacion": hist.get("observacion", ""),
            "asignadorecibe": hist.get("asignadorecibe", "Sistema"),
            "departamento": hist.get("departamento"),
            "fecha_creacion": hist["fecha_creacion"],
            "fecha_creacion_v2": fecha_creacion.strftime("%d/%m/%Y"),
            "hora_creacion_v2": fecha_creacion.strftime("%H:%M"),
            "archivo": hist.get("archivo"),
            "color": colores_estado.get(hist["estado"], "#12216A"),
            "servicio": hist.get("servicio")
        }
        
        historiales_formateados.append(historial_formateado)
    
    # Formatear solicitud
    solicitud_formateada = {
        "id": solicitud["id"],
        "codigo": solicitud["codigo"],
        "descripcion": solicitud["descripcion"],
        "estado": solicitud["estado"],
        "estado_display": ESTADOS_SOLICITUD.get(solicitud["estado"], "DESCONOCIDO"),
        "solicitante": "Usuario",  # Se puede obtener del data_unemi.json
        "agente": historiales_formateados[0].get("asignadorecibe", "Sistema") if historiales_formateados else "Sistema",
        "archivo": solicitud.get("archivo"),
        "nombre_servicio_minus": solicitud.get("servicio", {}).get("nombre", "Solicitud General")
    }
    
    return {
        "eBalconyRequest": solicitud_formateada,
        "eBalconyRequestHistories": historiales_formateados
    }


def corregir_solicitud(
    solicitud_id: int,
    descripcion_correccion: str,
    archivo: Optional[Any] = None
) -> bool:
    """
    Corrige una solicitud que está en estado CORRECCIÓN.
    
    Args:
        solicitud_id: ID de la solicitud
        descripcion_correccion: Descripción de las correcciones realizadas
        archivo: Archivo corregido (opcional)
    
    Returns:
        True si se corrigió exitosamente
    """
    data = _load_solicitudes()
    
    # Buscar solicitud
    solicitud = next(
        (s for s in data["solicitudes"] if s.get("id") == solicitud_id),
        None
    )
    
    if not solicitud:
        return False
    
    # Verificar que esté en estado CORRECCIÓN
    if solicitud.get("estado") != ESTADO_CORRECCION:
        return False
    
    # Actualizar descripción
    descripcion_original = solicitud.get("descripcion", "")
    solicitud["descripcion"] = f"{descripcion_original}\nCorrecciones realizadas:\n{descripcion_correccion}"
    
    # Actualizar archivo si se proporciona
    if archivo:
        ruta_archivo = _guardar_archivo(archivo, MEDIA_SOLICITUDES, "solicitud")
        if ruta_archivo:
            solicitud["archivo"] = ruta_archivo
    
    # Cambiar estado a EN TRÁMITE
    solicitud["estado"] = ESTADO_EN_TRAMITE
    solicitud["fecha_modificacion"] = datetime.now().isoformat()
    
    # Crear nuevo historial
    historial_id = data.get("next_historial_id", 1)
    data["next_historial_id"] = historial_id + 1
    
    # Obtener último historial para mantener asignación
    historiales_anteriores = [
        h for h in data["historiales"]
        if h.get("solicitud_id") == solicitud_id
    ]
    ultimo_historial = historiales_anteriores[-1] if historiales_anteriores else None
    
    ahora = datetime.now()
    historial = {
        "id": historial_id,
        "solicitud_id": solicitud_id,
        "estado": ESTADO_EN_TRAMITE,
        "observacion": f"Solicitud corregida por el estudiante. {descripcion_correccion}",
        "asignadorecibe_id": ultimo_historial.get("asignadorecibe_id") if ultimo_historial else None,
        "asignadorecibe": ultimo_historial.get("asignadorecibe", "Sistema") if ultimo_historial else "Sistema",
        "departamento": ultimo_historial.get("departamento") if ultimo_historial else None,
        "carrera_id": ultimo_historial.get("carrera_id") if ultimo_historial else None,
        "archivo": solicitud.get("archivo"),
        "fecha_creacion": ahora.isoformat(),
        "servicio": solicitud.get("servicio", {}).get("nombre", "Solicitud General")
    }
    
    data["historiales"].append(historial)
    
    # Guardar
    _save_solicitudes(data)
    
    print(f"✅ [SolicitudService] Solicitud {solicitud_id} corregida")
    
    return True


def eliminar_solicitud(solicitud_id: int, solicitante_id: int) -> bool:
    """
    Elimina una solicitud (solo si está en estado INGRESADO o LEIDO).
    
    Args:
        solicitud_id: ID de la solicitud
        solicitante_id: ID del solicitante (para verificación)
    
    Returns:
        True si se eliminó exitosamente
    """
    data = _load_solicitudes()
    
    # Buscar solicitud
    solicitud = next(
        (s for s in data["solicitudes"] if s.get("id") == solicitud_id),
        None
    )
    
    if not solicitud:
        return False
    
    # Verificar que pertenezca al solicitante
    if solicitud.get("solicitante_id") != solicitante_id:
        return False
    
    # Verificar que esté en estado permitido para eliminar
    estado = solicitud.get("estado")
    if estado not in [ESTADO_INGRESADO, ESTADO_LEIDO]:
        return False
    
    # Eliminar solicitud
    data["solicitudes"] = [
        s for s in data["solicitudes"]
        if s.get("id") != solicitud_id
    ]
    
    # Eliminar historiales relacionados
    data["historiales"] = [
        h for h in data["historiales"]
        if h.get("solicitud_id") != solicitud_id
    ]
    
    # Eliminar requisitos relacionados
    data["requisitos"] = [
        r for r in data["requisitos"]
        if r.get("solicitud_id") != solicitud_id
    ]
    
    # Guardar
    _save_solicitudes(data)
    
    print(f"✅ [SolicitudService] Solicitud {solicitud_id} eliminada")
    
    return True


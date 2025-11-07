# app/services/hierarchical_router.py
"""
Router jerárquico de 3 niveles:
1. Carpeta (por palabras gatillo)
2. Título/Acrónimo (por TitleLexicon)
3. Retrieval completo (BM25+Dense sobre candidatos)
"""
from typing import List, Dict
from .title_lexicon import get_title_lexicon, ACRONYM_MAP
from .query_planner import detect_entities, plan_queries


# Mapeo: carpeta → palabras gatillo
FOLDER_ROUTING = {
    # Nacional - Legal
    "legal_nacional/carta_suprema": [
        "constitucion", "carta magna", "derechos fundamentales", "garantias constitucionales"
    ],
    "legal_nacional/normas_internacionales": [
        "pidesc", "cadh", "dudh", "derechos humanos", "tratados internacionales",
        "convencion americana", "declaracion universal"
    ],
    "legal_nacional/codigos": [
        "coa", "cogep", "copfp", "coescci", "codigo", "codigo administrativo",
        "codigo de trabajo", "codigo tributario", "codigo procesos",
        "codigo planificacion", "codigo organico", "planificacion finanzas",
        "codigo economia", "finanzas publicas", "copfp"
    ],
    "legal_nacional/leyes_organicas": [
        "loes", "losep", "lopdp", "ley organica", "ley educacion superior",
        "ley servicio publico", "ley proteccion datos", "ley cultura",
        "ley contraloria", "ley contratacion publica"
    ],
    "legal_nacional/leyes_ordinarias": [
        "ley ordinaria", "ley seguridad publica", "regimen tributario interno"
    ],
    "legal_nacional/decretos_ejecutivos": [
        "decreto ejecutivo", "austeridad", "instructivo art 12"
    ],
    "legal_nacional/reglamentos_de_leyes": [
        "regimen academico", "rra", "reglamento general loes", "gratuidad",
        "doctorados", "formacion dual", "reglamento ces"
    ],
    "legal_nacional/normativas": [
        "normas control", "sector publico", "contraloria"
    ],
    "legal_nacional/acuerdos": [
        "acuerdo", "salario digno", "mdt"
    ],
    "legal_nacional/instructivos": [
        "instructivo", "verificacion estatutos", "ies"
    ],
    
    # UNEMI Interno (Estudiantes logueados) - MÁS ESPECÍFICO
    "unemi_interno/estudiantes": [
        "matricula", "permanencia", "retiro", "anulacion", "asistencia",
        "evaluacion", "supletorio", "remedial", "gracia", "becas",
        "practicas", "vinculacion", "titulacion", "datos personales",
        "violencia", "acoso", "inclusion", "paralelo", "horario",
        "cambio carrera", "cambio paralelo", "inasistencias", "faltas",
        "justificar falta", "cambio horario", "reglamento facultad",
        "estudiante", "matriculacion", "inscripcion", "notas", "calificaciones"
    ],
    "unemi_interno/tic": [
        "correo institucional", "sga", "politicas tic", "cuentas",
        "sistema gestion academica", "balcon servicios", "gestion del sga",
        "acceso sga", "usuario sga", "contraseña sga"
    ],
    
    # EPUNEMI
    "epunemi": [
        "certificados", "validacion", "jornadas", "formacion continua",
        "no llega certificado", "epunemi", "sagest", "capacitacion",
        "webinar", "curso epunemi"
    ],
}


def route_folders(user_text: str, entities: List[str] = None, queries: List[str] = None) -> List[str]:
    """
    Determina carpetas candidatas basado en palabras gatillo.
    
    Args:
        user_text: Texto original del usuario
        entities: Entidades detectadas (opcional)
        queries: Subconsultas planeadas (opcional)
    
    Returns:
        Lista de carpetas candidatas (top 3)
    """
    txt_lower = user_text.lower()
    
    # Detectar entidades si no se proporcionan
    if entities is None:
        entities = detect_entities(user_text)
    
    # Generar queries si no se proporcionan
    if queries is None:
        queries = plan_queries({}, txt_lower, user_text)[:3]
    
    # Combinar texto + entidades + queries
    hints = " ".join([txt_lower] + [q.lower() for q in queries] + [e.lower() for e in entities])
    
    # Scoring de carpetas
    folder_scores = {}
    for folder, triggers in FOLDER_ROUTING.items():
        score = sum(1 for trigger in triggers if trigger in hints)
        if score > 0:
            folder_scores[folder] = score
    
    # Ordenar por score y tomar top 2 (más selectivo)
    sorted_folders = sorted(folder_scores.items(), key=lambda x: x[1], reverse=True)
    top_folders = [folder for folder, score in sorted_folders[:2]]
    
    # Fallback: si no hay match, usar defaults por contexto
    if not top_folders:
        # Contexto estudiante logueado → priorizar UNEMI estudiantes + TIC
        top_folders = ["unemi_interno/estudiantes", "unemi_interno/tic"]
    
    print(f"📁 [Folder Routing] Carpetas candidatas: {top_folders}")
    return top_folders


def shortlist_by_title(user_text: str, folders: List[str] = None) -> List[str]:
    """
    Genera shortlist de archivos por título/acrónimo, opcionalmente filtrado por carpetas.
    
    Args:
        user_text: Texto original del usuario
        folders: Carpetas donde buscar (opcional)
    
    Returns:
        Lista de file paths (top 8)
    """
    lexicon = get_title_lexicon()
    
    # 1. Búsqueda global por título/acrónimo
    candidates = lexicon.search(user_text, limit=12)
    
    # 2. Filtrar por carpetas si se especifican
    if folders:
        filtered = []
        for file_path in candidates:
            # Verificar si el file_path está en alguna de las carpetas
            for folder in folders:
                if folder in file_path or file_path.startswith(f"app/data/{folder}"):
                    filtered.append(file_path)
                    break
        candidates = filtered
    
    # 3. Si hay carpetas pero no matches, buscar todos los files de esas carpetas
    if folders and not candidates:
        for folder in folders:
            candidates.extend(lexicon.get_by_category(folder))
    
    result = candidates[:8]
    print(f"📄 [Title Shortlist] Archivos candidatos: {len(result)} files")
    return result


def hierarchical_candidates(user_text: str, entities: List[str] = None, queries: List[str] = None) -> Dict:
    """
    Router jerárquico completo: carpetas + títulos.
    
    Args:
        user_text: Texto original del usuario
        entities: Entidades detectadas (opcional)
        queries: Subconsultas planeadas (opcional)
    
    Returns:
        Dict con:
        - folders: Lista de carpetas candidatas
        - files: Lista de file paths candidatos
        - method: Método usado ("folders+titles", "titles_only", "folders_only")
    """
    # Nivel 1: Routing por carpeta
    folders = route_folders(user_text, entities, queries)
    
    # Nivel 2: Shortlist por título
    files = shortlist_by_title(user_text, folders)
    
    # Determinar método usado
    method = "folders+titles" if folders and files else ("folders_only" if folders else "titles_only")
    
    result = {
        "folders": folders,
        "files": files,
        "method": method
    }
    
    print(f"🎯 [Hierarchical Router] Method: {method}")
    print(f"   Folders: {folders}")
    print(f"   Files: {len(files)} candidatos")
    
    return result


# app/services/query_planner.py
"""
Query Planning y Query Understanding avanzado.
Estrategias multi-stage para mejorar recall y precision.
"""
from typing import List, Dict, Tuple
import re
from collections import defaultdict


# === ENTIDADES DEL DOMINIO ===
ENTITY_PATTERNS = {
    "EPUNEMI": [
        r"\bepunemi\b",
        r"\b(centro de )?educaci[oó]n (continua|permanente)\b",
        r"\b(formaci[oó]n continua|capacitaci[oó]n|jornada|webinar)[a-z ]*epunemi\b",
    ],
    "SGA": [
        r"\bsga\b",
        r"\bsistema de gesti[oó]n acad[eé]mica\b",
        r"\bbalc[oó]n de servicios\b",
        r"\bm[oó]dulo acad[eé]mico\b",
    ],
    "CERTIFICADOS": [
        r"\bcertificado(s)?\b",
        r"\bvalidar certificado\b",
        r"\bcertificaci[oó]n\b",
    ],
    "INASISTENCIAS": [
        r"\b(falta|inasistencia|ausencia)(s)?\b",
        r"\bjustificar (falta|inasistencia)\b",
        r"\bporcentaje de asistencia\b",
    ],
    "MATRICULA": [
        r"\bmatr[ií]cula\b",
        r"\binscripci[oó]n\b",
        r"\bmatriculaci[oó]n\b",
    ],
    "CAMBIOS": [
        r"\bcambio de (carrera|paralelo|horario|jornada)\b",
        r"\btraslado\b",
        r"\bcambio de IES\b",
    ],
}


def detect_entities(text: str) -> List[str]:
    """Detecta entidades del dominio en el texto."""
    text_lower = text.lower()
    detected = []
    
    for entity, patterns in ENTITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                if entity not in detected:
                    detected.append(entity)
                break
    
    return detected


# === PLANNER: GENERACIÓN DE SUBCONSULTAS ===
def plan_queries(intent_slots: dict, q_canon: str, user_text: str = "") -> List[str]:
    """
    Genera variantes de la consulta para mejorar recall (OPTIMIZADO para velocidad).
    
    Estrategias (reducidas a 2):
    1. Query canónica (la más efectiva)
    2. Query original del usuario (fallback)
    """
    queries = []
    
    # Q1: Canónica es la más importante
    if q_canon and q_canon.strip():
        queries.append(q_canon.strip())
    
    # Q2: Original del usuario como fallback
    if user_text and user_text.strip() and user_text not in queries:
        queries.append(user_text.strip())
    
    # Backup: usar intent_short si no hay nada
    if not queries:
        core = intent_slots.get("intent_short", "").strip()
        if core:
            queries.append(core)
    
    # Deduplicar y limpiar
    unique_queries = []
    seen = set()
    for q in queries:
        q_clean = q.strip().lower()
        if q_clean and q_clean not in seen and len(q_clean) > 3:
            seen.add(q_clean)
            unique_queries.append(q.strip())
    
    return unique_queries[:5]  # Máximo 5 queries para no saturar


# === RRF: RECIPROCAL RANK FUSION ===
def rrf_fuse(doc_lists: List[List], k: int = 12, K: int = 60) -> List:
    """
    Fusiona múltiples listas de documentos usando Reciprocal Rank Fusion.
    
    Args:
        doc_lists: Lista de listas de documentos
        k: Número de documentos a retornar
        K: Constante de RRF (típicamente 60)
    
    Returns:
        Lista fusionada de top-k documentos
    """
    scores = defaultdict(float)
    doc_map = {}  # Para mantener referencia al documento original
    
    for doc_list in doc_lists:
        for rank, doc in enumerate(doc_list):
            # Usar el contenido o ID del documento como clave
            doc_id = _get_doc_id(doc)
            doc_map[doc_id] = doc
            
            # RRF score: 1 / (K + rank + 1)
            scores[doc_id] += 1.0 / (K + rank + 1)
    
    # Ordenar por score y retornar top-k
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    
    return [doc_map[doc_id] for doc_id, _ in sorted_ids]


def _get_doc_id(doc) -> str:
    """Extrae un ID único del documento para deduplicación."""
    if hasattr(doc, 'page_content'):
        # Usar hash del contenido + página como ID
        content = doc.page_content[:200]  # Primeros 200 chars
        page = doc.metadata.get('page', 0) if hasattr(doc, 'metadata') else 0
        return f"{hash(content)}_{page}"
    elif isinstance(doc, dict):
        content = str(doc.get('page_content', doc))[:200]
        page = doc.get('metadata', {}).get('page', 0)
        return f"{hash(content)}_{page}"
    else:
        return str(hash(str(doc)[:200]))


# === FUZZY SAFETY NET ===
def fuzzy_anchor_search(query: str, candidates: List[str], threshold: int = 75, limit: int = 5) -> List[Tuple[str, int]]:
    """
    Búsqueda fuzzy sobre candidatos (títulos, secciones, artículos).
    
    Args:
        query: Query del usuario
        candidates: Lista de strings candidatos (títulos de secciones, etc.)
        threshold: Score mínimo para considerar match (0-100)
        limit: Número máximo de resultados
    
    Returns:
        Lista de tuplas (candidato, score) ordenadas por score
    """
    try:
        from rapidfuzz import process, fuzz
        
        # Usar WRatio para mejor tolerancia a diferencias
        results = process.extract(
            query, 
            candidates, 
            scorer=fuzz.WRatio, 
            limit=limit
        )
        
        # Filtrar por threshold
        filtered = [(match, score, idx) for match, score, idx in results if score >= threshold]
        
        return [(match, score) for match, score, idx in filtered]
    
    except ImportError:
        print("⚠️ RapidFuzz no instalado. Safety net fuzzy desactivado.")
        return []


# === SECTION ANCHORS (precarga de títulos/secciones conocidas) ===
SECTION_ANCHORS = [
    # Gestión del SGA
    "Certificados que no llegan EPUNEMI",
    "Certificados EPUNEMI validación",
    "Cambio de carrera",
    "Cambio de IES",
    "Renuncia de cupo",
    "Retiro de matrícula",
    "Justificación de inasistencias",
    "Asistencia mínima",
    "Faltas permitidas",
    "Sistema de gestión académica SGA",
    "Balcón de servicios",
    "Formación continua EPUNEMI",
    "Jornadas académicas EPUNEMI",
    "Validar certificado en línea",
    "SAGEST certificados",
    "Centro de servicios EPUNEMI",
    
    # Reglamento general
    "Régimen académico",
    "Matrícula ordinaria",
    "Matrícula extraordinaria",
    "Horarios y paralelos",
    "Evaluación académica",
    "Calificaciones",
    "Exámenes",
    "Proyectos de grado",
    "Titulación",
]


def get_section_anchors() -> List[str]:
    """Retorna lista de anclas de secciones conocidas."""
    return SECTION_ANCHORS


# === ENTITY ROUTER ===
def route_by_entity(entities: List[str], query: str) -> Dict:
    """
    Router que determina filtros y boosts basados en entidades detectadas.
    
    Returns:
        Dict con:
        - filters: Filtros a aplicar en la búsqueda
        - boosts: Términos a boostear
        - metadata_filters: Filtros de metadata
    """
    routing = {
        "filters": [],
        "boosts": [],
        "metadata_filters": {},
    }
    
    if "EPUNEMI" in entities:
        routing["filters"].append("EPUNEMI")
        routing["boosts"].extend([
            "formación continua",
            "jornadas académicas",
            "certificados",
            "SAGEST",
            "validación en línea",
        ])
        # Filtro de metadata para buscar en PDFs de EPUNEMI
        routing["metadata_filters"]["source_pdf_contains"] = ["EPUNEMI", "Certificados", "Info_General"]
    
    if "SGA" in entities:
        routing["filters"].append("SGA")
        routing["boosts"].extend([
            "balcón de servicios",
            "sistema de gestión",
            "módulo académico",
        ])
        routing["metadata_filters"]["source_pdf_contains"] = ["SGA", "Gestion"]
    
    if "CERTIFICADOS" in entities:
        routing["boosts"].extend([
            "certificado",
            "validar",
            "descargar",
            "correo",
        ])
    
    if "INASISTENCIAS" in entities:
        routing["boosts"].extend([
            "asistencia",
            "faltas",
            "justificación",
            "porcentaje",
        ])
    
    return routing


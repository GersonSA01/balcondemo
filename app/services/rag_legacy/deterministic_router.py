# app/services/deterministic_router.py
"""
Router determinista basado en taxonomía y léxico.
Evita llamadas LLM en casos obvios (P0/P1).
"""
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from .config import DATA_DIR


# Sinónimos expandidos por familia (basado en análisis de solicitudes)
SYNONYM_MAP = {
    "admision_ingreso": [
        r"\b(admisi[oó]n|ingresar|postulaci[oó]n|postular|cupo|inscribirme|inscripci[oó]n|matriculaci[oó]n|matricular)\b",
        r"\b(proceso.*admis|requisitos.*ingres|como.*ingres|cuando.*postul)\b"
    ],
    "becas_maestrias_pagos": [
        r"\b(beca|maestr[ií]a|valor|pago|arancel|semestre|cu[oó]ta|cost[o|e]s?|nivel socioeconomico|estado socioeconomico)\b",
        r"\b(solicitar.*beca|aplicar.*beca|requisitos.*beca|monto|precio|tarifa)\b"
    ],
    "ingles_modulos_notas": [
        r"\b(m[oó]dulo.*ingl[eé]s|ingl[eé]s.*m[oó]dulo|migrar.*nota|nota.*ingl[eé]s|buckcenter|modulo \d+.*ingles|ingles.*modulo \d+)\b",
        r"\b(no puedo acceder.*modulo|siguiente modulo|aprobar.*modulo|pasar.*modulo|nota.*no.*aparece)\b"
    ],
    "soporte_sga_credenciales": [
        r"\b(SGA|contrase[nñ]a|clave.*correo|correo.*institucional|no puedo ingresar|plataforma|aula virtual|credenciales)\b",
        r"\b(olvide.*clave|recuperar.*contrase|problema.*acceso|error.*login|bloqueado.*cuenta)\b"
    ],
    "homologacion_cambio_ies": [
        r"\b(homolog|convalid|movilidad externa|cambio de universidad|cambio.*ies)\b",
        r"\b(validar.*materia|reconocer.*credito|transferir.*universidad)\b"
    ],
    "titulacion": [
        r"\b(titulaci[oó]n|proyecto de titulaci[oó]n|examen complexivo|tesis|trabajo.*grado)\b",
        r"\b(graduar|egresar|defensa.*tesis|sustentaci[oó]n)\b"
    ],
    "practicas_vinculacion": [
        r"\b(pr[aá]cticas|preprofesional|pre-profesional|vinculaci[oó]n|servicio.*comunitario)\b",
        r"\b(pasant[ií]a|internado|trabajo.*comunitario)\b"
    ],
    "certificados": [
        r"\b(certificado.*sanci[oó]n|certificado.*no.*sancio|certificado.*disciplinario)\b",
        r"\b(certificado.*epunemi|validar.*certificado|descargar.*certificado)\b"
    ],
    "examen_sede_evaluacion": [
        r"\b(ex[aá]men(?:es)?|parcial|bimestre|sede|ciudad.*ex[aá]men|evaluaci[oó]n)\b",
        r"\b(rendir.*examen|fecha.*examen|lugar.*examen|sede.*examen)\b"
    ],
    "carreras_modalidades": [
        r"\b(carrera|oferta acad[eé]mica|modalidad en l[ií]nea|derecho|psicolog[ií]a|educaci[oó]n b[aá]sica)\b",
        r"\b(que.*carreras|informacion.*carrera|cambiar.*carrera)\b"
    ],
}

# Mapeo familia → carpetas (boost)
FAMILY_TO_FOLDERS = {
    "admision_ingreso": ["unemi_interno/estudiantes"],
    "becas_maestrias_pagos": ["unemi_interno/estudiantes"],
    "ingles_modulos_notas": ["unemi_interno/estudiantes", "unemi_interno/tic"],
    "soporte_sga_credenciales": ["unemi_interno/tic"],
    "homologacion_cambio_ies": ["unemi_interno/estudiantes"],
    "titulacion": ["unemi_interno/estudiantes"],
    "practicas_vinculacion": ["unemi_interno/estudiantes"],
    "certificados": ["epunemi"],
    "examen_sede_evaluacion": ["unemi_interno/estudiantes"],
    "carreras_modalidades": ["unemi_interno/estudiantes"],
}

# Compilar regex una vez
COMPILED_SYNONYMS = {
    family: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for family, patterns in SYNONYM_MAP.items()
}


def load_taxonomy() -> Dict[str, List[str]]:
    """Carga la taxonomía desde JSON."""
    try:
        taxonomy_path = DATA_DIR / "taxonomia.json"
        if taxonomy_path.exists():
            with open(taxonomy_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def route_by_taxonomy(user_text: str) -> Tuple[Optional[str], Optional[str], float]:
    """
    Router determinista basado en taxonomía y sinónimos.
    
    Returns:
        (categoria, subcategoria, confidence)
        Si confidence >= 0.90, se puede saltar confirmación.
    """
    txt_lower = user_text.lower()
    taxonomy = load_taxonomy()
    
    # 1. Buscar en sinónimos (más rápido y preciso)
    family_scores = {}
    for family, patterns in COMPILED_SYNONYMS.items():
        score = sum(1 for pattern in patterns if pattern.search(txt_lower))
        if score > 0:
            family_scores[family] = score
    
    # 2. Si hay match claro en sinónimos, usar familia
    if family_scores:
        best_family = max(family_scores.items(), key=lambda x: x[1])[0]
        best_score = family_scores[best_family]
        
        # Mapear familia → categoría/subcategoría usando taxonomía
        category, subcategory = _map_family_to_taxonomy(best_family, taxonomy, txt_lower)
        
        # Confidence basado en número de matches y claridad
        confidence = min(0.85 + (best_score * 0.05), 0.95)
        
        return category, subcategory, confidence
    
    # 3. Buscar directamente en taxonomía (más lento pero más completo)
    for category, subcategories in taxonomy.items():
        for subcat in subcategories:
            # Buscar términos de la subcategoría en el texto
            subcat_lower = subcat.lower()
            words = subcat_lower.split()
            
            # Score: cuántas palabras de la subcategoría aparecen
            matches = sum(1 for word in words if word in txt_lower)
            if matches >= len(words) * 0.6:  # Al menos 60% de palabras
                confidence = 0.75 + (matches / len(words) * 0.15)
                return category, subcat, min(confidence, 0.90)
    
    return None, None, 0.0


def _map_family_to_taxonomy(family: str, taxonomy: Dict, user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """Mapea familia detectada a categoría/subcategoría de taxonomía."""
    # Mapeo directo familia → categoría
    family_to_category = {
        "admision_ingreso": "Academico",
        "becas_maestrias_pagos": "Bienestar estudiantil",
        "ingles_modulos_notas": "Idiomas/ofimatica",
        "soporte_sga_credenciales": "Consultas varias",
        "homologacion_cambio_ies": "Academico",
        "titulacion": "Academico",
        "practicas_vinculacion": "Vinculación",
        "certificados": "Consultas varias",
        "examen_sede_evaluacion": "Academico",
        "carreras_modalidades": "Academico",
    }
    
    category = family_to_category.get(family)
    if not category or category not in taxonomy:
        return None, None
    
    # Buscar subcategoría más cercana
    subcategories = taxonomy[category]
    txt_lower = user_text.lower()
    
    # Buscar match exacto o parcial
    for subcat in subcategories:
        subcat_lower = subcat.lower()
        if subcat_lower in txt_lower or any(word in txt_lower for word in subcat_lower.split() if len(word) > 4):
            return category, subcat
    
    # Fallback: primera subcategoría de la categoría
    return category, subcategories[0] if subcategories else None


def get_folders_for_family(family: str) -> List[str]:
    """Obtiene carpetas candidatas para una familia."""
    return FAMILY_TO_FOLDERS.get(family, [])


def expand_query_with_synonyms(query: str, family: Optional[str] = None) -> List[str]:
    """
    Expande query con sinónimos SIN LLM.
    Usa sinónimos de la familia detectada o búsqueda general.
    """
    variants = [query]
    txt_lower = query.lower()
    
    # Si tenemos familia, usar sus sinónimos
    if family and family in SYNONYM_MAP:
        # Agregar términos relacionados
        for pattern in COMPILED_SYNONYMS[family]:
            # Extraer términos del patrón (simplificado)
            # En producción, podrías tener un diccionario de expansiones
            pass
    
    # Expansiones básicas (stemming/diacríticos)
    # Normalizar diacríticos
    normalized = query.replace("ó", "o").replace("é", "e").replace("í", "i").replace("á", "a").replace("ú", "u")
    if normalized != query:
        variants.append(normalized)
    
    # Agregar variantes con/sin artículos
    words = query.split()
    if len(words) > 1:
        # Sin artículos
        no_articles = [w for w in words if w.lower() not in ["el", "la", "los", "las", "un", "una", "de", "del"]]
        if no_articles:
            variants.append(" ".join(no_articles))
    
    return list(set(variants))[:5]  # Máximo 5 variantes


# app/services/json_retriever.py
"""
Servicio para buscar información estructurada desde JSONs.
Busca por título, descripción y palabras clave.
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from .config import DATA_DIR


def load_structured_info(json_path: Path = None) -> List[Dict[str, Any]]:
    """
    Carga información estructurada desde un archivo JSON.
    
    Args:
        json_path: Ruta al archivo JSON (default: app/data/informacion_estructurada.json)
    
    Returns:
        Lista de diccionarios con información estructurada
    """
    if json_path is None:
        json_path = DATA_DIR / "informacion_estructurada.json"
    
    if not json_path.exists():
        print(f"⚠️ No se encontró {json_path}")
        return []
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Si es un diccionario con clave "items" o "informacion"
        if isinstance(data, dict):
            if "items" in data:
                return data["items"]
            elif "informacion" in data:
                return data["informacion"]
            elif "data" in data:
                return data["data"]
            # Si es un diccionario con listas anidadas, aplanar
            elif all(isinstance(v, list) for v in data.values()):
                items = []
                for category, category_items in data.items():
                    items.extend(category_items)
                return items
        
        # Si es una lista directa
        if isinstance(data, list):
            return data
        
        return []
    except Exception as e:
        print(f"⚠️ Error al cargar {json_path}: {e}")
        return []


def _normalize_text(text: str) -> str:
    """Normaliza texto para búsqueda (minúsculas, sin acentos básicos)."""
    if not text:
        return ""
    text = text.lower().strip()
    # Reemplazar acentos comunes
    replacements = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'ñ': 'n', 'ü': 'u'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _calculate_match_score(query_terms: List[str], item: Dict[str, Any]) -> float:
    """
    Calcula score de relevancia de un item para la query.
    
    Args:
        query_terms: Lista de términos de búsqueda normalizados
        item: Item de información estructurada
    
    Returns:
        Score de 0.0 a 1.0
    """
    if not query_terms:
        return 0.0
    
    # Obtener textos a buscar
    titulo = _normalize_text(item.get("titulo", ""))
    descripcion = _normalize_text(item.get("descripcion", ""))
    palabras_clave = [_normalize_text(p) for p in item.get("palabras_clave", [])]
    categorias = [_normalize_text(c) for c in item.get("categorias", [])]
    
    # Combinar todos los textos
    all_text = f"{titulo} {descripcion} {' '.join(palabras_clave)} {' '.join(categorias)}"
    
    # Contar matches
    matches = 0
    total_terms = len(query_terms)
    
    for term in query_terms:
        term_norm = _normalize_text(term)
        if term_norm in all_text:
            matches += 1
            # Bonus si está en título
            if term_norm in titulo:
                matches += 0.5
            # Bonus si está en palabras clave
            if any(term_norm in pk for pk in palabras_clave):
                matches += 0.3
    
    # Score base: proporción de términos encontrados
    base_score = matches / total_terms if total_terms > 0 else 0.0
    
    # Normalizar a [0, 1]
    score = min(base_score, 1.0)
    
    return score


def search_structured_info(
    query: str,
    json_path: Path = None,
    min_score: float = 0.3,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Busca información estructurada por términos clave.
    
    Args:
        query: Texto de búsqueda
        json_path: Ruta al archivo JSON (default: app/data/informacion_estructurada.json)
        min_score: Score mínimo para incluir resultado (0.0-1.0)
        max_results: Número máximo de resultados
    
    Returns:
        Lista de items ordenados por relevancia (score descendente)
    """
    # Cargar información estructurada
    items = load_structured_info(json_path)
    
    if not items:
        return []
    
    # Extraer términos de búsqueda (palabras de 3+ caracteres)
    query_terms = [t for t in re.findall(r'\b\w{3,}\b', query.lower()) if len(t) >= 3]
    
    if not query_terms:
        return []
    
    # Calcular scores para cada item
    scored_items = []
    for item in items:
        score = _calculate_match_score(query_terms, item)
        if score >= min_score:
            scored_items.append({
                **item,
                "_score": score,
                "_match_type": "json_structured"
            })
    
    # Ordenar por score descendente
    scored_items.sort(key=lambda x: x["_score"], reverse=True)
    
    # Limitar resultados
    results = scored_items[:max_results]
    
    if results:
        print(f"📋 [JSON Retriever] Encontrados {len(results)} resultados (score min: {min_score:.2f})")
        for i, r in enumerate(results[:3], 1):
            print(f"   {i}. {r.get('titulo', 'N/A')} (score: {r['_score']:.2f})")
    
    return results


def format_json_item_as_document(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte un item de JSON estructurado a formato de documento compatible con RAG.
    
    Args:
        item: Item de información estructurada
    
    Returns:
        Diccionario con formato de documento (page_content, metadata)
    """
    titulo = item.get("titulo", "")
    descripcion = item.get("descripcion", "")
    archivo = item.get("archivo", "")
    
    # Combinar título y descripción
    content = f"{titulo}\n\n{descripcion}"
    
    # Crear metadata
    metadata = {
        "source_type": "json_structured",
        "titulo": titulo,
        "archivo": archivo,
        "categorias": item.get("categorias", []),
        "palabras_clave": item.get("palabras_clave", []),
        "source_pdf": archivo if archivo.endswith(".pdf") else None,
        "source_image": archivo if archivo.endswith((".png", ".jpg", ".jpeg")) else None,
        "page": 0,  # Los JSONs no tienen páginas
        "score": item.get("_score", 0.0)
    }
    
    return {
        "page_content": content,
        "metadata": metadata
    }


def get_json_retriever(json_path: Path = None):
    """
    Obtiene un retriever para información estructurada en JSON.
    
    Args:
        json_path: Ruta al archivo JSON
    
    Returns:
        Función retriever compatible con el sistema RAG
    """
    def retrieve(query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Retriever que busca en JSONs estructurados.
        
        Args:
            query: Query de búsqueda
            k: Número de resultados
        
        Returns:
            Lista de documentos en formato compatible con RAG
        """
        # Buscar en JSONs
        json_results = search_structured_info(
            query,
            json_path=json_path,
            min_score=0.3,
            max_results=k
        )
        
        # Convertir a formato de documento
        documents = [format_json_item_as_document(item) for item in json_results]
        
        return documents
    
    return retrieve


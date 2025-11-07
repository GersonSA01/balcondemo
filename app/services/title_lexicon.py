# app/services/title_lexicon.py
"""
Índice rápido de títulos de documentos para routing por nombre/acrónimo.
Permite búsqueda en ~1-3ms por acrónimo (LOES, COA, RRA) o fuzzy matching.
"""
from pathlib import Path
from typing import List, Tuple
import json


# Mapa de acrónimos a nombres completos
ACRONYM_MAP = {
    # Nacional
    "loes": "Ley Orgánica de Educación Superior",
    "losep": "Ley Orgánica de Servicio Público",
    "lopdp": "Ley Orgánica de Protección de Datos Personales",
    "coa": "Código Orgánico Administrativo",
    "cogep": "Código Orgánico General de Procesos",
    "copfp": "Código Orgánico de Planificación y Finanzas Públicas",
    "coescci": "Código Orgánico de la Economía Social de los Conocimientos",
    "rra": "Reglamento de Régimen Académico",
    "ces": "Consejo de Educación Superior",
    "senescyt": "Secretaría de Educación Superior, Ciencia, Tecnología e Innovación",
    
    # UNEMI
    "unemi": "Universidad Estatal de Milagro",
    "rfgu": "Reglamento de Facultades de Grado UNEMI",
    "sga": "Sistema de Gestión Académica",
    "epunemi": "Educación Permanente UNEMI",
    
    # Otros
    "pidesc": "Pacto Internacional de Derechos Económicos, Sociales y Culturales",
    "cadh": "Convención Americana sobre Derechos Humanos",
    "dudh": "Declaración Universal de los Derechos Humanos",
}


class TitleLexicon:
    """Índice rápido de títulos de documentos para búsqueda por nombre/acrónimo."""
    
    def __init__(self, metadata_rows: List[dict]):
        """
        Args:
            metadata_rows: Lista de dicts con metadata de documentos
                          [{file, title, acronyms, category, ...}, ...]
        """
        self.rows = []
        self.titles = []
        self.acronym_map = {}  # "loes" -> set(files)
        self.category_map = {}  # "unemi/estudiantes" -> set(files)
        
        for m in metadata_rows:
            file_path = m.get("file", "")
            title = m.get("title", "")
            acronyms = m.get("acronyms", [])
            category = m.get("category", "")
            
            if not file_path or not title:
                continue
            
            # Normalizar file_path
            if not file_path.startswith("app/data/"):
                file_path = f"app/data/{file_path}"
            
            self.rows.append((title, file_path, acronyms, category))
            self.titles.append(title)
            
            # Mapear acrónimos a archivos
            for acr in acronyms:
                acr_lower = acr.lower()
                if acr_lower not in self.acronym_map:
                    self.acronym_map[acr_lower] = set()
                self.acronym_map[acr_lower].add(file_path)
            
            # Mapear categorías a archivos
            if category:
                if category not in self.category_map:
                    self.category_map[category] = set()
                self.category_map[category].add(file_path)
    
    def search_by_acronym(self, query: str) -> List[str]:
        """
        Búsqueda exacta por acrónimo.
        
        Args:
            query: Query del usuario ("loes art 77", "rra matricula")
        
        Returns:
            Lista de file paths que coinciden
        """
        query_lower = query.lower()
        tokens = [t for t in query_lower.split() if len(t) >= 2]
        
        hit_files = set()
        for token in tokens:
            # Buscar acrónimo exacto
            if token in self.acronym_map:
                hit_files |= self.acronym_map[token]
            
            # Buscar en ACRONYM_MAP expandido
            if token in ACRONYM_MAP:
                # Buscar files que contengan el nombre completo en su título
                full_name = ACRONYM_MAP[token].lower()
                for title, file_path, _, _ in self.rows:
                    if full_name in title.lower():
                        hit_files.add(file_path)
        
        return list(hit_files)
    
    def search_by_fuzzy(self, query: str, threshold: int = 80, limit: int = 8) -> List[Tuple[str, int]]:
        """
        Búsqueda fuzzy por título usando RapidFuzz.
        
        Args:
            query: Query del usuario
            threshold: Score mínimo (0-100)
            limit: Número máximo de resultados
        
        Returns:
            Lista de tuplas (file_path, score)
        """
        try:
            from rapidfuzz import process, fuzz
            
            # Buscar en títulos
            results = process.extract(
                query, 
                self.titles, 
                scorer=fuzz.WRatio, 
                limit=limit
            )
            
            # Filtrar por threshold y mapear a file paths
            fuzzy_results = []
            for title, score, idx in results:
                if score >= threshold:
                    _, file_path, _, _ = self.rows[idx]
                    fuzzy_results.append((file_path, score))
            
            return fuzzy_results
        
        except ImportError:
            print("⚠️ RapidFuzz no instalado. Búsqueda fuzzy desactivada.")
            return []
    
    def search(self, query: str, limit: int = 8) -> List[str]:
        """
        Búsqueda combinada: primero por acrónimo, luego fuzzy.
        
        Args:
            query: Query del usuario
            limit: Número máximo de resultados
        
        Returns:
            Lista de file paths ordenados por relevancia
        """
        # 1. Búsqueda por acrónimo (exacta)
        by_acronym = self.search_by_acronym(query)
        
        # 2. Búsqueda fuzzy por título
        by_fuzzy = self.search_by_fuzzy(query, threshold=75, limit=limit)
        fuzzy_files = [file_path for file_path, score in by_fuzzy]
        
        # 3. Combinar y deduplicar (acrónimos primero)
        seen = set()
        results = []
        
        for file_path in by_acronym:
            if file_path not in seen:
                results.append(file_path)
                seen.add(file_path)
        
        for file_path in fuzzy_files:
            if file_path not in seen and len(results) < limit:
                results.append(file_path)
                seen.add(file_path)
        
        return results[:limit]
    
    def get_by_category(self, category: str) -> List[str]:
        """
        Obtiene todos los files de una categoría.
        
        Args:
            category: Categoría ("unemi/estudiantes", "legal_nacional/codigos")
        
        Returns:
            Lista de file paths
        """
        return list(self.category_map.get(category, []))


def load_metadata(data_dir: Path = None) -> List[dict]:
    """
    Carga metadata desde metadata.jsonl.
    
    Args:
        data_dir: Directorio de datos (default: app/data)
    
    Returns:
        Lista de dicts con metadata
    """
    if data_dir is None:
        from .config import DATA_DIR
        data_dir = DATA_DIR
    
    metadata_file = data_dir / "metadata.jsonl"
    
    if not metadata_file.exists():
        print(f"⚠️ No se encontró {metadata_file}")
        return []
    
    metadata_rows = []
    with open(metadata_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    metadata_rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️ Error parseando metadata: {e}")
    
    return metadata_rows


# Singleton global (se inicializa al importar el módulo)
_TITLE_LEXICON_CACHE = None


def get_title_lexicon() -> TitleLexicon:
    """Obtiene el TitleLexicon singleton (con caché)."""
    global _TITLE_LEXICON_CACHE
    
    if _TITLE_LEXICON_CACHE is None:
        metadata_rows = load_metadata()
        _TITLE_LEXICON_CACHE = TitleLexicon(metadata_rows)
        print(f"📚 TitleLexicon inicializado con {len(metadata_rows)} documentos")
    
    return _TITLE_LEXICON_CACHE




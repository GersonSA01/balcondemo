#!/usr/bin/env python
"""
Script para generar metadata.jsonl automáticamente desde PDFs existentes.
"""
import json
from pathlib import Path
import re

# Mapeo de carpetas a categorías y scopes
FOLDER_MAPPING = {
    "legal_nacional/carta_suprema": {
        "scope": "nacional",
        "issuer": "Asamblea Nacional",
        "audience": ["estudiante", "docente", "administrativo"],
    },
    "legal_nacional/normas_internacionales": {
        "scope": "internacional",
        "issuer": "ONU/OEA",
        "audience": ["estudiante", "docente"],
    },
    "legal_nacional/codigos": {
        "scope": "nacional",
        "issuer": "Asamblea Nacional",
        "audience": ["administrativo", "docente"],
    },
    "legal_nacional/leyes_organicas": {
        "scope": "nacional",
        "issuer": "Asamblea Nacional",
        "audience": ["estudiante", "docente", "administrativo"],
    },
    "legal_nacional/leyes_ordinarias": {
        "scope": "nacional",
        "issuer": "Asamblea Nacional",
        "audience": ["administrativo"],
    },
    "legal_nacional/decretos_ejecutivos": {
        "scope": "nacional",
        "issuer": "Presidencia",
        "audience": ["administrativo"],
    },
    "legal_nacional/reglamentos_de_leyes": {
        "scope": "nacional",
        "issuer": "CES/Asamblea",
        "audience": ["estudiante", "docente", "administrativo"],
    },
    "legal_nacional/normativas": {
        "scope": "nacional",
        "issuer": "Contraloría",
        "audience": ["administrativo"],
    },
    "legal_nacional/acuerdos": {
        "scope": "nacional",
        "issuer": "Ministerios",
        "audience": ["administrativo"],
    },
    "legal_nacional/instructivos": {
        "scope": "nacional",
        "issuer": "CES",
        "audience": ["administrativo"],
    },
    "unemi_interno/estatuto": {
        "scope": "unemi",
        "issuer": "UNEMI",
        "audience": ["estudiante", "docente", "administrativo"],
    },
    "unemi_interno/estudiantes": {
        "scope": "unemi",
        "issuer": "UNEMI",
        "audience": ["estudiante"],
    },
    "unemi_interno/tic": {
        "scope": "unemi",
        "issuer": "UNEMI",
        "audience": ["estudiante", "docente"],
    },
    "epunemi": {
        "scope": "epunemi",
        "issuer": "EPUNEMI",
        "audience": ["estudiante", "participante"],
    },
}

# Extraer acrónimos comunes de nombres de archivos
ACRONYM_PATTERNS = [
    (r"LOES", ["LOES"]),
    (r"LOSEP", ["LOSEP"]),
    (r"LOPDP", ["LOPDP"]),
    (r"COA", ["COA"]),
    (r"COGEP", ["COGEP"]),
    (r"COPFP", ["COPFP"]),
    (r"COESCCI", ["COESCCI"]),
    (r"RRA|REGIMEN.*ACADEMICO", ["RRA"]),
    (r"CES", ["CES"]),
    (r"SGA", ["SGA"]),
    (r"UNEMI", ["UNEMI"]),
    (r"EPUNEMI", ["EPUNEMI"]),
]


def extract_acronyms(filename: str) -> list:
    """Extrae acrónimos del nombre del archivo."""
    acronyms = []
    for pattern, acrs in ACRONYM_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            acronyms.extend(acrs)
    return list(set(acronyms))


def extract_version(filename: str) -> str:
    """Extrae versión del nombre del archivo."""
    # Buscar patrones como v2024, v2023-09, 2024, etc.
    patterns = [
        r"v(\d{4}[-]\d{2})",  # v2024-09
        r"v(\d{4})",  # v2024
        r"(\d{4}[-]\d{2}[-]\d{2})",  # 2024-09-15
        r"(\d{4})",  # 2024
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
    
    return "unknown"


def clean_title(filename: str) -> str:
    """Genera un título limpio desde el nombre del archivo."""
    # Remover extensión
    name = filename.replace(".pdf", "")
    
    # Remover patrones comunes
    name = re.sub(r"v\d{4}(-\d{2})?", "", name)  # Versiones
    name = re.sub(r"\(\d+\)", "", name)  # (1), (2)
    name = re.sub(r"[-_]+", " ", name)  # Guiones y underscores
    
    # Capitalizar
    name = name.title()
    
    # Limpiar espacios múltiples
    name = re.sub(r"\s+", " ", name).strip()
    
    return name


def extract_topics(filename: str, folder: str) -> list:
    """Extrae topics del nombre y carpeta."""
    topics = []
    
    # Topics por nombre de archivo
    keywords = {
        "matricula": ["matricula", "inscripcion"],
        "evaluacion": ["evaluacion", "calificacion", "notas"],
        "asistencia": ["asistencia", "inasistencias", "faltas"],
        "titulacion": ["titulacion", "grado", "titulo"],
        "becas": ["becas", "ayuda economica"],
        "certificados": ["certificados", "validacion"],
        "gratuidad": ["gratuidad"],
        "doctorados": ["doctorados", "phd"],
        "reglamento": ["reglamento", "normativa"],
        "codigo": ["codigo"],
        "ley": ["ley"],
    }
    
    filename_lower = filename.lower()
    for key, topic_list in keywords.items():
        if key in filename_lower:
            topics.extend(topic_list)
    
    # Topics por carpeta
    if "estudiantes" in folder:
        topics.extend(["estudiantes", "academico"])
    elif "codigos" in folder:
        topics.append("codigo")
    elif "leyes" in folder:
        topics.append("ley")
    elif "reglamentos" in folder:
        topics.append("reglamento")
    elif "epunemi" in folder:
        topics.extend(["formacion continua", "capacitacion"])
    
    return list(set(topics))


def generate_metadata(data_dir: Path) -> list:
    """Genera metadata para todos los PDFs en data_dir."""
    metadata_list = []
    
    # Buscar todos los PDFs recursivamente
    for pdf_path in data_dir.rglob("*.pdf"):
        if pdf_path.is_file():
            # Obtener path relativo
            rel_path = pdf_path.relative_to(data_dir)
            file_str = str(rel_path).replace("\\", "/")
            
            # Determinar carpeta/categoría
            parts = file_str.split("/")
            if len(parts) > 1:
                category = "/".join(parts[:-1])
            else:
                category = "raiz"
            
            # Obtener metadata de carpeta
            folder_meta = FOLDER_MAPPING.get(category, {
                "scope": "unemi",
                "issuer": "UNEMI",
                "audience": ["estudiante"],
            })
            
            # Generar metadata
            metadata = {
                "file": file_str,
                "title": clean_title(pdf_path.name),
                "issuer": folder_meta["issuer"],
                "scope": folder_meta["scope"],
                "audience": folder_meta["audience"],
                "category": category,
                "topics": extract_topics(pdf_path.name, category),
                "acronyms": extract_acronyms(pdf_path.name),
                "version": extract_version(pdf_path.name),
                "vigente": True,
            }
            
            metadata_list.append(metadata)
    
    return metadata_list


def main():
    # Directorio de datos
    script_dir = Path(__file__).parent.parent
    data_dir = script_dir / "app" / "data"
    
    if not data_dir.exists():
        print(f"❌ No se encontró el directorio: {data_dir}")
        return
    
    print(f"📂 Escaneando PDFs en: {data_dir}")
    
    # Generar metadata
    metadata_list = generate_metadata(data_dir)
    
    print(f"✅ Generados {len(metadata_list)} registros de metadata")
    
    # Guardar en metadata.jsonl
    output_file = data_dir / "metadata.jsonl"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for meta in metadata_list:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    
    print(f"💾 Guardado en: {output_file}")
    print(f"\n📊 Resumen por categoría:")
    
    # Resumen
    from collections import Counter
    categories = Counter(m["category"] for m in metadata_list)
    for cat, count in categories.most_common():
        print(f"   {cat}: {count} PDFs")


if __name__ == "__main__":
    main()




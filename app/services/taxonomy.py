# app/services/taxonomy.py
"""Mapeo de intención a taxonomía para handoff al agente."""
import json
import re
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from .config import llm, DATA_DIR


def _taxonomy_path() -> Path:
    """Obtiene la ruta al archivo taxonomia.json."""
    return DATA_DIR / "taxonomia.json"


def _load_taxonomy() -> dict:
    """Carga el archivo de taxonomía JSON."""
    path = _taxonomy_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def map_to_taxonomy(user_text: str) -> dict:
    """
    Clasifica la intención del usuario en una categoría y subcategoría de taxonomía.
    Devuelve {"categoria": str, "subcategoria": str}.
    """
    taxonomy = _load_taxonomy()
    if not taxonomy:
        return {"categoria": "Consultas varias", "subcategoria": "Consultas varias"}
    
    # Crear lista plana de opciones
    opciones = []
    for cat, subs in taxonomy.items():
        if not subs:
            opciones.append(cat)
        else:
            for sub in subs:
                opciones.append(f"{cat} › {sub}")
    
    if not opciones:
        return {"categoria": "Consultas varias", "subcategoria": "Consultas varias"}
    
    # Usar LLM para clasificar
    sistema = (
        "Eres un clasificador. Debes elegir exactamente UNA ruta de taxonomía "
        "que mejor corresponda a la intención. La ruta debe ser una de la lista dada.\n"
        "Responde SOLO JSON con la clave 'ruta'. Sin explicaciones."
    )
    lista = "\n".join(f"- {o}" for o in opciones[:200])
    prompt = ChatPromptTemplate.from_messages([
        ("system", sistema),
        ("human", f"Intención: {user_text}\n"
                 f"Opciones (elige exactamente una):\n{lista}\n"
                 'Salida (estricta): {{"ruta":"<una opción exactamente como aparece arriba>"}}')
    ])
    try:
        out = llm.invoke(prompt)
        raw = getattr(out, "content", str(out)).strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        blob = m.group(0) if m else raw
        data = json.loads(blob)
        ruta = (data.get("ruta") or "").strip()
        
        # Parsear ruta
        if " › " in ruta:
            parts = ruta.split(" › ")
            return {"categoria": parts[0].strip(), "subcategoria": parts[1].strip()}
        else:
            return {"categoria": ruta, "subcategoria": ruta}
    except Exception:
        pass
    
    # Fallback
    return {"categoria": "Consultas varias", "subcategoria": "Consultas varias"}


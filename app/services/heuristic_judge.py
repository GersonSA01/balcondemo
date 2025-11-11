# app/services/heuristic_judge.py
"""
Juez heurístico no-LLM para filtrar casos obvios.
Solo invoca LLM-judge en casos "borderline" (P2).
"""
from typing import Dict, List
import re
from collections import Counter


def heuristic_answerability_score(
    query: str,
    docs: List,
    k: int = 8
) -> Dict[str, float]:
    """
    Calcula score de respondibilidad usando solo señales heurísticas.
    NO usa LLM.
    
    Returns:
        {
            "confidence": float [0,1],
            "signals": dict con señales individuales,
            "verdict": "high" | "medium" | "low" | "borderline"
        }
    """
    if not docs:
        return {
            "confidence": 0.0,
            "signals": {},
            "verdict": "low"
        }
    
    # Extraer textos y scores
    texts = []
    scores = []
    for d in docs[:k]:
        txt = getattr(d, "page_content", None) or (d.get("page_content") if isinstance(d, dict) else str(d))
        txt = (txt or "").strip()
        if txt:
            texts.append(txt)
            # Score de similitud si está disponible
            md = getattr(d, "metadata", {}) or (d.get("metadata", {}) if isinstance(d, dict) else {})
            s = float(md.get("score", 0.0))
            scores.append(s)
    
    if not texts:
        return {
            "confidence": 0.0,
            "signals": {},
            "verdict": "low"
        }
    
    # SEÑAL 1: Cobertura (# docs no vacíos)
    n_docs = len(texts)
    signal_coverage = min(n_docs / 4.0, 1.0)  # Normalizado a [0,1]
    
    # SEÑAL 2: Longitud total de contenido
    total_chars = sum(len(t) for t in texts)
    signal_length = min(total_chars / 2400.0, 1.0)
    
    # SEÑAL 3: Similitud promedio
    sim_avg = sum(scores) / len(scores) if scores else 0.0
    signal_sim = sim_avg
    
    # SEÑAL 4: Margen de similitud (doc1 vs doc_k)
    sim_margin = (scores[0] - scores[-1]) if len(scores) >= 2 else (scores[0] if scores else 0.0)
    signal_margin = min(sim_margin / 0.5, 1.0) if sim_margin > 0 else 0.0
    
    # SEÑAL 5: Cobertura de n-gramas (query terms en docs)
    query_terms = set(re.findall(r"\b\w{3,}\b", query.lower()))
    if query_terms:
        term_coverage = []
        for txt in texts[:5]:  # Top 5 docs
            txt_lower = txt.lower()
            found = sum(1 for term in query_terms if term in txt_lower)
            term_coverage.append(found / len(query_terms))
        signal_ngram = sum(term_coverage) / len(term_coverage) if term_coverage else 0.0
    else:
        signal_ngram = 0.5  # Neutral si no hay términos
    
    # SEÑAL 6: Densidad de citas/referencias (artículos, números, fechas)
    citation_density = []
    for txt in texts[:3]:
        # Contar números, artículos (Art., Artículo), referencias
        citations = len(re.findall(r"\b(art[íi]culo?|art\.|num\.|n[úu]mero|ley|decreto|reglamento|acuerdo)\b", txt, re.IGNORECASE))
        citations += len(re.findall(r"\b\d+[-\/]\d+|\b\d{4}\b", txt))  # Fechas/números
        density = min(citations / max(len(txt.split()), 1) * 100, 1.0)  # Normalizado
        citation_density.append(density)
    signal_citations = sum(citation_density) / len(citation_density) if citation_density else 0.0
    
    # PESOS (ajustados para mejor balance)
    weights = {
        "coverage": 0.20,
        "length": 0.15,
        "similarity": 0.25,
        "margin": 0.10,
        "ngram": 0.20,
        "citations": 0.10
    }
    
    # Calcular confidence final
    confidence = (
        weights["coverage"] * signal_coverage +
        weights["length"] * signal_length +
        weights["similarity"] * signal_sim +
        weights["margin"] * signal_margin +
        weights["ngram"] * signal_ngram +
        weights["citations"] * signal_citations
    )
    confidence = max(0.0, min(confidence, 1.0))
    
    # Determinar verdict
    if confidence >= 0.70:
        verdict = "high"
    elif confidence >= 0.55:
        verdict = "borderline"  # Requiere LLM-judge
    elif confidence >= 0.40:
        verdict = "medium"
    else:
        verdict = "low"
    
    return {
        "confidence": confidence,
        "signals": {
            "coverage": signal_coverage,
            "length": signal_length,
            "similarity": signal_sim,
            "margin": signal_margin,
            "ngram": signal_ngram,
            "citations": signal_citations
        },
        "verdict": verdict,
        "non_empty_docs": n_docs,
        "total_chars": total_chars
    }


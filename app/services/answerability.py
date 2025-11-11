# app/services/answerability.py
"""Juez de respondibilidad híbrido: heurístico + LLM solo en borderline (V2)."""
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from .config import llm
from .heuristic_judge import heuristic_answerability_score


def answerability_score(intent_query: str, retr, k: int = 8, use_hybrid: bool = True) -> dict:
    """
    Calcula score de respondibilidad usando juez híbrido (V2):
    - Primero juez heurístico (rápido, sin LLM)
    - Solo invoca LLM-judge si verdict == "borderline" (0.55-0.70)
    
    Args:
        use_hybrid: Si True, usa juez híbrido. Si False, usa solo LLM (legacy).
    
    Devuelve dict con:
    - confidence: float [0,1]
    - non_empty_docs: int
    - total_chars: int
    - sim_avg: float
    - sim_margin: float
    - verdict: str ("yes"|"no"|"unknown")
    - method: str ("heuristic"|"hybrid"|"llm_only")
    """
    try:
        retrieved = retr.invoke(intent_query)
        docs = retrieved if isinstance(retrieved, list) else ([retrieved] if retrieved else [])
    except Exception:
        docs = []
    
    if not use_hybrid:
        # Legacy: usar solo LLM (comportamiento anterior)
        return _answerability_llm_only(intent_query, docs, k)
    
    # V2: Juez híbrido
    # Paso 1: Juez heurístico (sin LLM)
    heuristic_result = heuristic_answerability_score(intent_query, docs, k)
    verdict_heuristic = heuristic_result["verdict"]
    confidence_heuristic = heuristic_result["confidence"]
    
    # Paso 2: Solo invocar LLM si es "borderline"
    if verdict_heuristic == "borderline":
        # Caso borderline: necesitamos LLM para decidir
        texts = []
        for d in docs[:k]:
            txt = getattr(d, "page_content", None) or (d.get("page_content") if isinstance(d, dict) else str(d))
            txt = (txt or "").strip()
            if txt:
                texts.append(txt)
        
        if texts:
            judge_sys = (
                "Eres un juez que evalúa si el contexto permite responder una consulta académica/normativa.\n"
                "Criterios:\n"
                "- Si hay información relevante (artículos, procedimientos, plazos, requisitos), aunque sea parcial → YES\n"
                "- Solo di NO si el contexto es completamente irrelevante o vacío\n"
                "- Sé GENEROSO: si hay algo útil, di YES\n"
                "Devuelve SOLO 'yes' o 'no'."
            )
            sample = "\n\n".join(texts[:5])
            msgs = ChatPromptTemplate.from_messages([
                ("system", judge_sys),
                ("human", "Consulta:\n{q}\n\nContexto (extractos):\n{c}\n\n¿Se puede responder algo útil? (yes/no)")
            ]).format_messages(q=intent_query, c=sample[:6000])
            try:
                out = llm.invoke(msgs)
                verdict_raw = (getattr(out, "content", str(out)) or "").strip().lower()
                verdict_llm = "yes" if "yes" in verdict_raw else ("no" if "no" in verdict_raw else "unknown")
            except Exception:
                verdict_llm = "yes" if texts else "no"
            
            # Ajustar confidence basado en veredicto LLM
            if verdict_llm == "yes":
                confidence = min(confidence_heuristic + 0.10, 0.85)  # Boost si LLM dice yes
                verdict = "yes"
            elif verdict_llm == "no":
                confidence = max(confidence_heuristic - 0.15, 0.30)  # Penalizar si LLM dice no
                verdict = "no"
            else:
                confidence = confidence_heuristic
                verdict = "unknown"
            
            method = "hybrid"
        else:
            confidence = confidence_heuristic
            verdict = "no"
            method = "heuristic"
    else:
        # Caso claro: usar resultado heurístico directamente
        confidence = confidence_heuristic
        verdict = "yes" if verdict_heuristic == "high" else ("no" if verdict_heuristic == "low" else "unknown")
        method = "heuristic"
    
    # Extraer señales para compatibilidad
    non_empty = heuristic_result.get("non_empty_docs", 0)
    total_chars = heuristic_result.get("total_chars", 0)
    signals = heuristic_result.get("signals", {})
    sim_avg = signals.get("similarity", 0.0)
    sim_margin = signals.get("margin", 0.0)
    
    return {
        "confidence": confidence,
        "non_empty_docs": non_empty,
        "total_chars": total_chars,
        "sim_avg": sim_avg,
        "sim_margin": sim_margin,
        "verdict": verdict,
        "method": method
    }


def _answerability_llm_only(intent_query: str, docs: List, k: int) -> dict:
    """Versión legacy: solo LLM (sin heurística)."""
    texts, sims = [], []
    for d in docs[:k]:
        txt = getattr(d, "page_content", None)
        if not txt and isinstance(d, dict):
            txt = d.get("page_content")
        if not txt:
            txt = str(d)
        txt = (txt or "").strip()
        if not txt:
            continue
        texts.append(txt)
        
        s = 0.0
        try:
            md = getattr(d, "metadata", {})
            if not md and isinstance(d, dict):
                md = d.get("metadata", {})
            s = float(md.get("score", 0.0))
        except Exception:
            s = 0.0
        sims.append(s)

    non_empty = len(texts)
    total_chars = sum(len(t) for t in texts)
    sim_avg = sum(sims)/len(sims) if sims else 0.0
    sim_margin = (sims[0] - sims[-1]) if len(sims) >= 2 else (sims[0] if sims else 0.0)

    verdict = "unknown"
    if texts:
        judge_sys = (
            "Eres un juez que evalúa si el contexto permite responder una consulta académica/normativa.\n"
            "Criterios:\n"
            "- Si hay información relevante (artículos, procedimientos, plazos, requisitos), aunque sea parcial → YES\n"
            "- Solo di NO si el contexto es completamente irrelevante o vacío\n"
            "- Sé GENEROSO: si hay algo útil, di YES\n"
            "Devuelve SOLO 'yes' o 'no'."
        )
        sample = "\n\n".join(texts[:5])
        msgs = ChatPromptTemplate.from_messages([
            ("system", judge_sys),
            ("human", "Consulta:\n{q}\n\nContexto (extractos):\n{c}\n\n¿Se puede responder algo útil? (yes/no)")
        ]).format_messages(q=intent_query, c=sample[:6000])
        try:
            out = llm.invoke(msgs)
            verdict_raw = (getattr(out, "content", str(out)) or "").strip().lower()
            verdict = "yes" if "yes" in verdict_raw else ("no" if "no" in verdict_raw else "unknown")
        except Exception:
            verdict = "yes" if texts else "no"

    w_docs, w_chars, w_sim, w_margin, w_verdict = 0.15, 0.15, 0.25, 0.15, 0.30
    n_docs = min(non_empty/4.0, 1.0)
    n_chars = min(total_chars/2400.0, 1.0)
    n_sim = sim_avg
    n_margin = min(sim_margin/0.5, 1.0) if sim_margin > 0 else 0.0
    n_verdict = 1.0 if verdict == "yes" else (0.0 if verdict == "no" else 0.5)
    
    confidence = (
        w_docs * n_docs +
        w_chars * n_chars +
        w_sim * n_sim +
        w_margin * n_margin +
        w_verdict * n_verdict
    )
    confidence = max(0.0, min(confidence, 1.0))
    
    return {
        "confidence": confidence,
        "non_empty_docs": non_empty,
        "total_chars": total_chars,
        "sim_avg": sim_avg,
        "sim_margin": sim_margin,
        "verdict": verdict,
        "method": "llm_only"
    }


def gen_query_variants_llm(original_query: str, n: int = 4, use_llm: bool = False) -> list[str]:
    """
    Genera múltiples reformulaciones de la query.
    
    V2: Por defecto usa expansión sin LLM (más rápido).
    Solo usa LLM si use_llm=True explícitamente.
    """
    # V2: Expansión sin LLM por defecto
    if not use_llm:
        from .deterministic_router import expand_query_with_synonyms
        return expand_query_with_synonyms(original_query)[:n]
    
    # Legacy: Expansión con LLM (solo si se solicita explícitamente)
    sys = (
        "Eres un experto en reformular consultas académicas desde diferentes ángulos.\n\n"
        "EJEMPLO:\n"
        "Original: 'Solicitar cambio de paralelo'\n"
        "Variantes:\n"
        "- ¿Cuál es el procedimiento para cambiar de paralelo?\n"
        "- ¿Cómo gestionar el cambio de horario a otro grupo?\n"
        "- Requisitos para trasladarse a otra sección de la misma asignatura\n"
        "- ¿Quién autoriza el cambio de paralelo y en qué plazo?\n\n"
        f"TAREA: Genera EXACTAMENTE {n} reformulaciones DIFERENTES de la consulta que te daré.\n"
        "Varía enfoque, sinónimos, términos técnicos, y perspectiva.\n"
        "Formato: Una variante por línea, sin numeración, sin explicaciones."
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys),
        ("human", f"{original_query}")
    ])
    try:
        messages = prompt.format_messages()
        out = llm.invoke(messages)
        raw = getattr(out, "content", str(out)).strip()
        print(f"🔧 DEBUG gen_query_variants - Raw LLM output:\n{raw}")
        
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        variants = []
        for l in lines[:n]:
            # Limpiar numeración y guiones
            l = l.lstrip("0123456789.-) ")
            if l and l != original_query:  # Evitar duplicar la original
                variants.append(l)
        
        print(f"🔧 DEBUG gen_query_variants - Parsed variants: {variants}")
        
        # Si no generó suficientes variantes, agregar la original
        if not variants:
            variants = [original_query]
        
        return variants
    except Exception as e:
        print(f"🔧 DEBUG gen_query_variants - Error: {e}")
        return [original_query]


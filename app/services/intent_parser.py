# app/services/intent_parser.py
"""Interpretación de intención y manejo de confirmaciones."""
import json
import re
from langchain_core.prompts import ChatPromptTemplate
from .config import llm, guarded_invoke


INTENT_SYSTEM_V2 = """
Eres un extractor de intención. Devuelve SOLO un JSON válido con esta estructura mínima:

{
  "intent_short": "<12-16 palabras, concreta y accionable>",
  "accion": "<verbo principal en infinitivo: consultar, rectificar, recalificar, cambiar, inscribir, homologar, etc.>",
  "objeto": "<qué cosa sobre la que recae la acción: nota, actividad, paralelo, carrera, matrícula, práctica, etc.>",
  "asignatura": "<si aplica, nombre o siglas>",
  "unidad_o_actividad": "<si aplica: parcial 1, tarea 2, práctica, proyecto, examen, acta, etc.>",
  "periodo": "<si aplica: 2025-2, Oct-Feb 2025, etc.>",
  "carrera": "<si aplica>",
  "facultad": "<si aplica>",
  "modalidad": "<si aplica: en línea, presencial, híbrida>",
  "sistema": "<si aplica: SGA, plataforma, aula virtual, etc.>",
  "problema": "<si describe un fallo: no veo, no carga, error, bloqueado, etc.>",
  "detalle_libre": "<1 oración con detalles útiles literal/parafraseado con fidelidad>"
}

Reglas:
- No inventes: si un campo no está, pon "" (string vacío).
- intent_short debe ser una síntesis concreta (sin nombres propios sensibles).
- Usa el texto del usuario tal cual cuando aporte precisión (p. ej., "Parcial 1").
- Mantén tildes y mayúsculas de nombres de asignaturas si las dijo el usuario.
- NUNCA incluyas texto fuera del JSON.
"""


def interpretar_intencion_principal(texto_usuario: str) -> dict:
    """Devuelve un dict con slots de intención."""
    prompt = f"{INTENT_SYSTEM_V2}\n\nTEXTO:\n{texto_usuario}\n"
    out = guarded_invoke(llm, prompt)
    raw = getattr(out, "content", str(out)).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except Exception:
        data = {
            "intent_short": texto_usuario.strip()[:80],
            "accion": "",
            "objeto": "",
            "asignatura": "",
            "unidad_o_actividad": "",
            "periodo": "",
            "carrera": "",
            "facultad": "",
            "modalidad": "",
            "sistema": "",
            "problema": "",
            "detalle_libre": texto_usuario.strip()[:160]
        }
    keys = [
        "intent_short", "accion", "objeto", "asignatura", "unidad_o_actividad",
        "periodo", "carrera", "facultad", "modalidad", "sistema", "problema", "detalle_libre"
    ]
    for k in keys:
        data.setdefault(k, "")
        if not isinstance(data[k], str):
            data[k] = str(data[k] or "")
    return data


def _confirm_text_from_slots(sl: dict) -> str:
    """Genera una confirmación natural en español usando el LLM."""
    try:
        sys = (
            "Eres un asistente que redacta confirmaciones EN ESPAÑOL, naturales y breves, a partir de 'slots' de intención.\n"
            "Estilo OBLIGATORIO:\n"
            "- 1 a 2 oraciones, segunda persona, tono conversacional y empático.\n"
            "- Usa artículos y preposiciones correctas: 'la nota', 'la calificación', 'una falta', 'cambiar de paralelo', 'consultar la nota'.\n"
            "- Integra asignatura/actividad/período/sistema solo si están presentes.\n"
            "- Evita frases robóticas como 'Entendí lo siguiente' o 'Además comentas'.\n"
            "- No uses paréntesis, listas, ni comillas innecesarias. No repitas lo mismo.\n"
        )
        fewshot = (
            "EJEMPLOS:\n"
            "SLOTS:\n"
            "{'accion':'justificar','objeto':'falta','asignatura':'Matemática'}\n"
            "CONFIRMA:\n"
            "¿Quieres justificar una falta en Matemática? \n\n"
            "SLOTS:\n"
            "{'accion':'consultar','objeto':'nota','asignatura':'Biología','unidad_o_actividad':'Parcial 1','periodo':'2025-2','sistema':'SGA','problema':'no aparece'}\n"
            "CONFIRMA:\n"
            "¿Quieres consultar la nota de Parcial 1 en Biología, del período 2025-2, en SGA, donde indicas que no aparece?\n\n"
            "SLOTS:\n"
            "{'accion':'cambiar','objeto':'paralelo','carrera':'Ingeniería de Software','detalle_libre':'por razones laborales'}\n"
            "CONFIRMA:\n"
            "¿Quieres cambiar de paralelo en Ingeniería de Software por razones laborales?\n"
        )

        user = (
            "Estos son los slots de la intención del usuario. Redacta UNA confirmación siguiendo las reglas.\n"
            "Devuelve SOLO el texto final (sin etiquetas, sin JSON, sin comillas).\n"
            f"SLOTS:\n{json.dumps(sl, ensure_ascii=False)}"
        )

        msgs = ChatPromptTemplate.from_messages([
            ("system", sys + "\n\n" + fewshot),
            ("human", user),
        ]).format_messages()

        out = guarded_invoke(llm, msgs)
        text = getattr(out, "content", str(out)).strip()

        text = re.sub(r"\s+", " ", text)

        bad_prefixes = ["Entendí lo siguiente", "Entendi lo siguiente", "Entendido", "He entendido", "Comprendo"]
        for bp in bad_prefixes:
            if text.lower().startswith(bp.lower()):
                text = re.sub(rf"^{re.escape(bp)}[:,\s-]*\s*", "", text, flags=re.IGNORECASE)

        return text

    except Exception:
        intent_short = (sl.get("intent_short") or "tu solicitud").strip().lower()
        return f"¿Te refieres a {intent_short}?"


def es_confirmacion_positiva(txt: str) -> bool:
    """Detecta si el texto es una confirmación positiva."""
    txt = (txt or "").strip().lower()
    yes = {"si", "sí", "correcto", "así es", "de acuerdo", "ok", "okay", "vale", "yes", "confirmo"}
    return any(w == txt or w in txt for w in yes)


def es_confirmacion_negativa(txt: str) -> bool:
    """Detecta si el texto es una confirmación negativa."""
    txt = (txt or "").strip().lower()
    no = {"no", "negativo", "no es así", "no exactamente", "corrige", "cambia"}
    return any(w == txt or w in txt for w in no)


def es_greeting(text: str) -> bool:
    """Detecta si el texto es un saludo."""
    txt = text.strip().lower()
    greetings = {
        "hola", "buenas", "buenos dias", "buenos días", "buenas tardes", "buenas noches",
        "hello", "hi", "holi", "alo", "aló", "que tal", "qué tal", "ola"
    }
    t2 = re.sub(r"[^\wáéíóúñü\s]", " ", txt).strip()
    words = t2.split()
    if 1 <= len(words) <= 4:
        joined = " ".join(words)
        if any(joined == g for g in greetings) or any(w in greetings for w in words):
            return True
    return False


def obtener_primer_nombre(student_data: dict = None) -> str:
    """
    Extrae el primer nombre del estudiante desde los datos del estudiante.
    
    Args:
        student_data: Diccionario con datos del estudiante, debe contener
                     credenciales.nombre_completo o credenciales.nombre
    
    Returns:
        Primer nombre del estudiante o string vacío si no se encuentra
    """
    if not student_data:
        return ""
    try:
        credenciales = student_data.get("credenciales", {})
        nombre_completo = credenciales.get("nombre_completo") or credenciales.get("nombre") or ""
        if nombre_completo:
            return nombre_completo.split()[0]
    except Exception:
        pass
    return ""


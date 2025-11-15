# app/services/intent_parser.py
"""Interpretación de intención y manejo de confirmaciones."""
import json
import re
from langchain_core.prompts import ChatPromptTemplate
from .config import llm, guarded_invoke


INTENT_SYSTEM = """
Eres un extractor de intención. Devuelve SOLO un JSON válido con esta estructura mínima:

{
  "intent_short": "<12-16 palabras, concreta y accionable>",
  "intent_code": "<uno de: consultar_solicitudes_balcon | consultar_datos_personales | consultar_carrera_actual | consultar_roles_usuario | otro>",
  "accion": "<verbo principal en infinitivo: consultar, rectificar, recalificar, cambiar, inscribir, homologar, pagar, solicitar, etc.>",
  "objeto": "<qué cosa sobre la que recae la acción: nota, actividad, paralelo, carrera, matrícula, práctica, beca, certificado, etc.>",
  "asignatura": "<si aplica, nombre o siglas>",
  "unidad_o_actividad": "<si aplica: parcial 1, tarea 2, práctica, proyecto, examen, acta, etc.>",
  "periodo": "<si aplica: 2025-2, Oct-Feb 2025, etc.>",
  "carrera": "<si aplica>",
  "facultad": "<si aplica>",
  "modalidad": "<si aplica: en línea, presencial, híbrida>",
  "sistema": "<si aplica: SGA, plataforma, aula virtual, etc.>",
  "problema": "<si describe un fallo: no veo, no carga, error, bloqueado, etc.>",
  "detalle_libre": "<1 oración con detalles útiles literal/parafraseado con fidelidad>",
  "original_user_message": "<mensaje original del usuario tal cual>",
  "needs_confirmation": <true o false>,
  "confirm_text": "<texto corto de confirmación en español, listo para mostrar al usuario>",
  "answer_type": "<informativo o operativo>",
  "multi_intent": <true o false>,
  "intents": [
    {
      "id": "req_1",
      "intent_short": "<12-16 palabras, concreta y accionable>",
      "intent_code": "<uno de: consultar_solicitudes_balcon | consultar_datos_personales | consultar_carrera_actual | consultar_roles_usuario | otro>",
      "accion": "<verbo principal en infinitivo>",
      "objeto": "<qué cosa sobre la que recae la acción>",
      "asignatura": "<si aplica>",
      "unidad_o_actividad": "<si aplica>",
      "periodo": "<si aplica>",
      "carrera": "<si aplica>",
      "facultad": "<si aplica>",
      "modalidad": "<si aplica>",
      "sistema": "<si aplica>",
      "problema": "<si aplica>",
      "detalle_libre": "<detalles útiles>",
      "answer_type": "<informativo o operativo>",
      "needs_confirmation": <true o false>,
      "confirm_text": "<texto de confirmación>"
    }
  ]
}

Reglas para intent_code:
- "consultar_solicitudes_balcon": Si pregunta sobre sus solicitudes en el balcón (ej: "qué solicitudes tengo", "mis solicitudes", "estado de mis solicitudes")
- "consultar_carrera_actual": Si pregunta sobre su carrera actual (ej: "en qué carrera estoy", "qué carrera estudio", "mi carrera")
- "consultar_roles_usuario": Si pregunta sobre sus roles/perfiles (ej: "qué perfiles tengo", "soy estudiante o profesor")
- "consultar_datos_personales": Si pregunta sobre datos personales básicos (ej: "cuál es mi nombre", "mi email")
- "otro": Para cualquier otra consulta que no entre en las categorías anteriores

Reglas para needs_confirmation:
- Pon true si la intención no está 100% clara o si puede malinterpretarse.
- Pon false si la intención es completamente clara y no necesita confirmación (ej: saludos simples, consultas muy específicas).

Reglas para confirm_text:
- Frase amigable en español que le permita al usuario confirmar su intención.
- Usa artículos y preposiciones correctas: 'la nota', 'la calificación', 'una falta', 'cambiar de paralelo', 'consultar la nota'.
- Integra asignatura/actividad/período/sistema solo si están presentes.
- Evita frases robóticas como 'Entendí lo siguiente' o 'Además comentas'.
- No uses paréntesis, listas, ni comillas innecesarias.
- Ejemplos:
  * Para "consultar nota de Parcial 1": "¿Quieres consultar la nota de Parcial 1 en Matemática del período 2025-2?"
  * Para "cambiar de paralelo": "¿Quieres solicitar un cambio de paralelo?"
  * Para "beca estudiantil": "¿Quieres información sobre becas estudiantiles?"

Reglas para answer_type:
- "informativo": Preguntas de datos, requisitos, definiciones, horarios, pasos, instrucciones, "cómo hacer X", consultas que se pueden responder con información de documentos.
  Ejemplos: "¿Cuáles son los requisitos para matricularme?", "¿Qué horarios tiene la biblioteca?", "¿Cómo puedo ver mis notas?"
- "operativo": Cambios de estado o trámites que requieren acción humana: cambiar, anular, inscribir, homologar, recalificar, convalidar, pagar, solicitar certificados, etc.
  Ejemplos: "Quiero cambiar de paralelo", "Necesito anular mi matrícula", "Quiero solicitar una beca"

Reglas para multi_intent e intents:
- Además, debes detectar si el mensaje del usuario contiene MÁS DE UN requerimiento independiente.
- Considera requerimiento independiente cuando el usuario pide cosas que se tramitarían por separado.
  Ejemplos:
  - "Quiero un certificado de matrícula Y también cambiar de paralelo"
  - "Necesito saber los requisitos para la beca Y cómo puedo apelar una nota"
- Si hay varios, NUNCA mezcles todo en un solo intent_short.
- En ese caso:
  - Establece multi_intent = true.
  - Llena la lista "intents" con UN OBJETO POR CADA requerimiento.
  - El primer elemento de "intents" es el requerimiento principal (req_1).
  - Copia el requerimiento principal a los campos raíz (intent_short, accion, objeto, answer_type, etc.) para compatibilidad.
- Si solo hay un requerimiento:
  - multi_intent = false
  - "intents" tiene exactamente un elemento (req_1) con todos los campos completos.

Reglas generales:
- No inventes: si un campo no está, pon "" (string vacío) o false según corresponda.
- intent_short debe ser una síntesis concreta (sin nombres propios sensibles).
- Usa el texto del usuario tal cual cuando aporte precisión (p. ej., "Parcial 1").
- Mantén tildes y mayúsculas de nombres de asignaturas si las dijo el usuario.
- NUNCA incluyas texto fuera del JSON.
- original_user_message debe ser el mensaje exacto del usuario.
"""


def interpretar_intencion_principal(texto_usuario: str) -> dict:
    """
    Devuelve un dict con slots de intención incluyendo needs_confirmation, confirm_text y answer_type.
    
    Args:
        texto_usuario: Mensaje del usuario
    
    Returns:
        Dict con slots de intención, incluyendo needs_confirmation, confirm_text y answer_type
    """
    prompt = f"{INTENT_SYSTEM}\n\nTEXTO:\n{texto_usuario}\n"
    out = guarded_invoke(llm, prompt)
    raw = getattr(out, "content", str(out)).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    blob = m.group(0) if m else raw
    try:
        data = json.loads(blob)
    except Exception as e:
        # Loggear el error antes del fallback
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error parseando respuesta del LLM como JSON: {e}. Usando fallback.")
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
    
    # Normalizar multi_intent e intents
    multi_intent = bool(data.get("multi_intent", False))
    intents_list = data.get("intents") or []
    
    # Compatibilidad: si no hay "intents", creamos uno a partir del intent principal
    if not intents_list:
        intents_list = [{
            "id": "req_1",
            "intent_short": data.get("intent_short", ""),
            "intent_code": data.get("intent_code", ""),
            "accion": data.get("accion", ""),
            "objeto": data.get("objeto", ""),
            "asignatura": data.get("asignatura", ""),
            "unidad_o_actividad": data.get("unidad_o_actividad", ""),
            "periodo": data.get("periodo", ""),
            "carrera": data.get("carrera", ""),
            "facultad": data.get("facultad", ""),
            "modalidad": data.get("modalidad", ""),
            "sistema": data.get("sistema", ""),
            "problema": data.get("problema", ""),
            "detalle_libre": data.get("detalle_libre", ""),
            "answer_type": data.get("answer_type", "informativo"),
            "needs_confirmation": data.get("needs_confirmation", False),
            "confirm_text": data.get("confirm_text", "")
        }]
        multi_intent = False
    
    # Asegurar IDs y normalizar cada intent
    for i, r in enumerate(intents_list, start=1):
        r.setdefault("id", f"req_{i}")
        
        # Normalizar campos string en cada intent
        intent_keys = [
            "intent_short", "intent_code", "accion", "objeto", "asignatura", "unidad_o_actividad",
            "periodo", "carrera", "facultad", "modalidad", "sistema", "problema", "detalle_libre", "confirm_text"
        ]
        for k in intent_keys:
            r.setdefault(k, "")
            if not isinstance(r.get(k), str):
                r[k] = str(r.get(k) or "")
        
        # Normalizar needs_confirmation (bool)
        nc = str(r.get("needs_confirmation", "")).strip().lower()
        r["needs_confirmation"] = nc in ["true", "1", "sí", "si", "yes", "verdadero"]
        
        # Normalizar answer_type
        answer = r.get("answer_type", "").strip().lower()
        if answer not in ("informativo", "operativo"):
            accion_lower = r.get("accion", "").lower()
            if accion_lower in ["cambiar", "modificar", "anular", "inscribir", "homologar", "rectificar", "pagar", "solicitar", "recalificar", "convalidar"]:
                answer = "operativo"
            else:
                answer = "informativo"
        r["answer_type"] = answer
        
        # Si confirm_text está vacío pero needs_confirmation es True, generar uno básico
        if r.get("needs_confirmation") and not r.get("confirm_text", "").strip():
            intent_short = r.get("intent_short", "").strip()
            if intent_short:
                r["confirm_text"] = f"¿Te refieres a {intent_short.lower()}?"
            else:
                r["confirm_text"] = "¿Puedes confirmar tu solicitud?"
    
    # Actualizar data con multi_intent e intents normalizados
    data["multi_intent"] = multi_intent
    data["intents"] = intents_list
    
    # Lista completa de keys (siempre incluye los nuevos campos)
    keys_base = [
        "intent_short", "intent_code", "accion", "objeto", "asignatura", "unidad_o_actividad",
        "periodo", "carrera", "facultad", "modalidad", "sistema", "problema", "detalle_libre", 
        "original_user_message", "needs_confirmation", "confirm_text", "answer_type"
    ]
    
    # Normalizar campos string en el nivel raíz (compatibilidad)
    for k in keys_base:
        if k == "needs_confirmation":  # Este es bool, no string
            continue
        data.setdefault(k, "")
        if not isinstance(data[k], str):
            data[k] = str(data[k] or "")
    
    # Asegurar que original_user_message siempre tenga el texto original
    if not data.get("original_user_message"):
        data["original_user_message"] = texto_usuario.strip()
    
    # Si intent_code no está o es inválido, intentar inferirlo
    if not data.get("intent_code") or data["intent_code"] == "":
        data["intent_code"] = "otro"
    
    # Normalizar needs_confirmation (bool) en nivel raíz
    nc = str(data.get("needs_confirmation", "")).strip().lower()
    data["needs_confirmation"] = nc in ["true", "1", "sí", "si", "yes", "verdadero"]
    
    # Normalizar answer_type en nivel raíz
    answer = data.get("answer_type", "").strip().lower()
    if answer not in ("informativo", "operativo"):
        # Heurística: si la acción es operativa, es operativo
        accion_lower = data.get("accion", "").lower()
        if accion_lower in ["cambiar", "modificar", "anular", "inscribir", "homologar", "rectificar", "pagar", "solicitar", "recalificar", "convalidar"]:
            answer = "operativo"
        else:
            answer = "informativo"
    data["answer_type"] = answer
    
    # Si confirm_text está vacío pero needs_confirmation es True, generar uno básico
    if data.get("needs_confirmation") and not data.get("confirm_text", "").strip():
        intent_short = data.get("intent_short", "").strip()
        if intent_short:
            data["confirm_text"] = f"¿Te refieres a {intent_short.lower()}?"
        else:
            data["confirm_text"] = "¿Puedes confirmar tu solicitud?"
    
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


def _capitalize_name(name: str) -> str:
    """
    Capitaliza un nombre correctamente: solo la primera letra de cada palabra en mayúscula.

    Args:
        name: Nombre a capitalizar
    
    Returns:
        Nombre capitalizado correctamente
    """
    if not name:
        return ""
    
    # Dividir por espacios y capitalizar cada palabra
    palabras = name.strip().split()
    palabras_capitalizadas = []
    
    for palabra in palabras:
        if palabra:
            # Capitalizar: primera letra mayúscula, resto minúsculas
            palabra_capitalizada = palabra[0].upper() + palabra[1:].lower() if len(palabra) > 1 else palabra.upper()
            palabras_capitalizadas.append(palabra_capitalizada)
    
    return " ".join(palabras_capitalizadas)


def obtener_primer_nombre(student_data: dict = None) -> str:
    """
    Extrae el primer nombre del estudiante desde los datos del estudiante.
    Capitaliza correctamente usando la función general de capitalización.
    
    Args:
        student_data: Diccionario con datos del estudiante, debe contener
                     credenciales.nombre_completo o credenciales.nombre
    
    Returns:
        Primer nombre del estudiante capitalizado o string vacío si no se encuentra
    """
    if not student_data:
        return ""
    try:
        # Buscar en múltiples ubicaciones (igual que _get_student_name)
        nombre_completo = ""
        
        # Prioridad 1: contexto.credenciales.nombre_completo
        contexto = student_data.get("contexto", {})
        if contexto:
            credenciales = contexto.get("credenciales", {})
            if credenciales:
                nombre_completo = credenciales.get("nombre_completo") or credenciales.get("nombre") or ""
        
        # Prioridad 2: credenciales directo (sin contexto)
        if not nombre_completo:
            credenciales = student_data.get("credenciales", {})
            if credenciales:
                nombre_completo = credenciales.get("nombre_completo") or credenciales.get("nombre") or ""
        
        # Prioridad 3: datos_personales.nombres
        if not nombre_completo:
            datos_personales = contexto.get("datos_personales", {}) if contexto else {}
            if datos_personales:
                nombre_completo = datos_personales.get("nombres", "").strip()
        
        # Prioridad 4: persona.nombres
        if not nombre_completo:
            persona = student_data.get("persona", {})
            if persona:
                nombre_completo = persona.get("nombres", "").strip()
        
        if nombre_completo:
            # Capitalizar el nombre completo primero
            nombre_capitalizado = _capitalize_name(nombre_completo)
            # Obtener solo el primer nombre
            primer_nombre = nombre_capitalizado.split()[0] if nombre_capitalizado else ""
            return primer_nombre
    except Exception:
        pass
    return ""


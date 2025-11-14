# 📚 ANÁLISIS COMPLETO DEL SISTEMA BALCONDEMO + PRIVATEGPT

## 🏗️ ARQUITECTURA GENERAL

### Componentes Principales

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Svelte)                        │
│  - BalconServicios.svelte                                   │
│  - ChatbotInline.svelte                                     │
│  - Formulario.svelte                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP POST /api/chat/
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              BALCONDEMO (Django Backend)                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ views.py (chat_api)                                  │   │
│  │  - Recibe mensaje del usuario                        │   │
│  │  - Carga datos del estudiante (data_unemi.json)      │   │
│  │  - Llama a classify_with_privategpt()                │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ privategpt_chat_service.py                           │   │
│  │  - Maneja flujo de conversación                       │   │
│  │  - Interpreta intenciones                              │   │
│  │  - Maneja confirmaciones                              │   │
│  │  - Determina handoff                                  │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ intent_parser.py                                      │   │
│  │  - Extrae intención del mensaje                       │   │
│  │  - Genera confirm_text                                │   │
│  │  - Determina answer_type                              │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ privategpt_client.py                                  │   │
│  │  - Cliente HTTP para PrivateGPT                       │   │
│  │  - Construye mensajes con contexto de rol            │   │
│  │  - Envía a /v1/chat/completions                       │   │
│  └──────────────────┬───────────────────────────────────┘   │
└──────────────────────┼──────────────────────────────────────┘
                       │ HTTP POST
                       │ /v1/chat/completions
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              PRIVATEGPT (FastAPI + LlamaIndex)              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ chat_router.py                                       │   │
│  │  - Recibe request                                    │   │
│  │  - Parsea JSON response                              │   │
│  │  - Procesa fuentes                                   │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ chat_service.py                                      │   │
│  │  - Construye chat_engine                             │   │
│  │  - Combina system prompts                             │   │
│  │  - Expande consultas                                 │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ VectorStoreComponent                                  │   │
│  │  - Retriever con filtrado de archivos tmp            │   │
│  │  - Búsqueda semántica                                │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ LLM (Gemini)                                         │   │
│  │  - Genera respuesta con contexto                     │   │
│  │  - Retorna JSON con has_information                  │   │
│  └──────────────────┬───────────────────────────────────┘   │
└──────────────────────┼──────────────────────────────────────┘
                       │ JSON Response
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              BALCONDEMO (Procesamiento)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ privategpt_response_parser.py                        │   │
│  │  - Parsea respuesta JSON                             │   │
│  │  - Extrae has_information                            │   │
│  │  - Valida con heurísticas                           │   │
│  └──────────────────┬───────────────────────────────────┘   │
│                     │                                         │
│  ┌──────────────────▼───────────────────────────────────┐   │
│  │ privategpt_chat_service.py                           │   │
│  │  - Agrupa fuentes                                    │   │
│  │  - Determina handoff si necesario                    │   │
│  └──────────────────┬───────────────────────────────────┘   │
└──────────────────────┼──────────────────────────────────────┘
                       │ JSON Response
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND                                 │
│  - Muestra respuesta                                        │
│  - Muestra fuentes                                          │
│  - Maneja confirmaciones                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 FLUJO COMPLETO DE UNA CONSULTA

### Ejemplo: "necesito saber como cambiar de carrera"

#### **PASO 1: Frontend → Django (views.py)**

```python
# Frontend envía POST a /api/chat/
{
  "message": "necesito saber como cambiar de carrera",
  "conversation_history": [],
  "usuario_cedula": "1234567890",
  "perfil_id": "1"
}
```

**Archivo**: `views.py` → `chat_api()`
- Recibe el request
- Carga `student_data` desde `data_unemi.json`
- Llama a `classify_with_privategpt()`

---

#### **PASO 2: Detección de Stage y Saludo**

**Archivo**: `privategpt_chat_service.py` → `classify_with_privategpt()`

```python
# Detecta stage desde historial
stage = _detect_stage_from_history(conversation_history)
# Resultado: ConversationStage.AWAIT_INTENT

# Si es saludo → respuesta directa
if es_greeting(user_text):
    return {"summary": "Hola! 👋 Soy tu asistente..."}
```

---

#### **PASO 3: Interpretación de Intención (1ª LLM Call)**

**Archivo**: `intent_parser.py` → `interpretar_intencion_principal()`

**Prompt enviado al LLM**:
```
INTENT_SYSTEM:
Eres un extractor de intención. Devuelve SOLO un JSON válido con esta estructura mínima:

{
  "intent_short": "<12-16 palabras, concreta y accionable>",
  "intent_code": "<uno de: consultar_solicitudes_balcon | consultar_datos_personales | consultar_carrera_actual | consultar_roles_usuario | otro>",
  "accion": "<verbo principal en infinitivo: consultar, rectificar, recalificar, cambiar, inscribir, homologar, pagar, solicitar, etc.>",
  "objeto": "<qué cosa sobre la que recae la acción: nota, actividad, paralelo, carrera, matrícula, práctica, beca, certificado, etc.>",
  ...
  "needs_confirmation": <true o false>,
  "confirm_text": "<texto corto de confirmación en español, listo para mostrar al usuario>",
  "answer_type": "<informativo o operativo>"
}

TEXTO:
necesito saber como cambiar de carrera
```

**Respuesta del LLM**:
```json
{
  "intent_short": "consultar información sobre cambio de carrera",
  "intent_code": "otro",
  "accion": "consultar",
  "objeto": "carrera",
  "detalle_libre": "necesito saber como cambiar de carrera",
  "needs_confirmation": false,
  "confirm_text": "¿Quieres consultar información sobre cómo cambiar de carrera?",
  "answer_type": "informativo"
}
```

**Normalización**:
- `needs_confirmation`: `"false"` → `False` (bool)
- `answer_type`: `"informativo"` → `"informativo"` (validado)

---

#### **PASO 4: Verificación de Confirmación**

**Archivo**: `privategpt_chat_service.py` → `classify_with_privategpt()`

```python
needs_confirmation = intent_slots.get("needs_confirmation", True)

if not needs_confirmation:
    # Proceder directamente sin mostrar confirmación
    return _handle_confirmation_stage(...)
```

**Como `needs_confirmation = False`**, se procede directamente a la siguiente etapa.

---

#### **PASO 5: Clasificación Heurística (Sin LLM)**

**Archivo**: `handoff.py` → `classify_with_heuristics()`

```python
# Determina department y channel usando reglas heurísticas
intent_code = "otro"
accion = "consultar"
objeto = "carrera"

# Reglas heurísticas:
if "carrera" in objeto:
    # Buscar en handoff_config.json
    department = "académico"
    channel = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
```

**Resultado**:
```python
{
    "answer_type": "informativo",
    "department": "académico",
    "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "reasoning": "Clasificado por reglas heurísticas"
}
```

---

#### **PASO 6: Búsqueda de Solicitudes Relacionadas**

**Archivo**: `related_request_matcher.py` → `find_related_requests()`

- Busca solicitudes previas del estudiante relacionadas con "cambio de carrera"
- Si encuentra → muestra opción para relacionar
- Si no encuentra → continúa con PrivateGPT

**En este caso**: No hay solicitudes relacionadas → continúa.

---

#### **PASO 7: Construcción del Mensaje para PrivateGPT**

**Archivo**: `privategpt_chat_service.py` → `_build_role_context_message()`

**Extracción de rol**:
```python
rol = _extract_user_role(student_data, perfil_id)
# Resultado: "estudiante"
```

**Mensajes construidos**:
```python
messages = [
    {
        "role": "system",
        "content": """ROL DEL USUARIO: ESTUDIANTE

FILTRADO CRITICO:
- SOLO usa documentos para ESTUDIANTES (reglamentos estudiantiles, procesos académicos estudiantiles, servicios estudiantiles, becas estudiantiles)
- IGNORA documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente)
- IGNORA documentos para PERSONAL ADMINISTRATIVO
- Si el contexto contiene SOLO información para profesores/administrativos, establece has_information=false"""
    },
    {
        "role": "user",
        "content": "necesito saber como cambiar de carrera"
    }
]
```

**Session Context**:
```python
session_context = {
    "user_role": "estudiante",
    "profile_type": "ESTUDIANTE",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería"
}
```

---

#### **PASO 8: Envío a PrivateGPT**

**Archivo**: `privategpt_client.py` → `chat_completion()`

**Request HTTP POST**:
```http
POST http://localhost:8001/v1/chat/completions
Content-Type: application/json

{
  "messages": [
    {"role": "system", "content": "ROL DEL USUARIO: ESTUDIANTE\n\nFILTRADO CRITICO:..."},
    {"role": "user", "content": "necesito saber como cambiar de carrera"}
  ],
  "use_context": true,
  "include_sources": true,
  "stream": false,
  "session_context": {
    "user_role": "estudiante",
    ...
  }
}
```

---

#### **PASO 9: Procesamiento en PrivateGPT**

**Archivo**: `chat_service.py` → `_chat_engine()`

**1. Combinación de System Prompts**:

PrivateGPT combina automáticamente:
- `default_query_system_prompt` (de `settings-docker.yaml`)
- System message personalizado (de BalconDemo)

**Prompt final combinado**:
```
Eres un asistente RAG. Debes responder exclusivamente con un JSON válido en UTF-8,
sin texto adicional, sin backticks y sin bloques de código.

Formato de salida obligatorio:
- Un objeto JSON con las claves:
  - has_information: booleano (true o false)
  - response: string en español, claro y natural
  - fuentes: lista de objetos; cada objeto con la clave pagina (string)

---

ROL DEL USUARIO: ESTUDIANTE

FILTRADO CRITICO:
- SOLO usa documentos para ESTUDIANTES (reglamentos estudiantiles, procesos académicos estudiantiles, servicios estudiantiles, becas estudiantiles)
- IGNORA documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente)
- IGNORA documentos para PERSONAL ADMINISTRATIVO
- Si el contexto contiene SOLO información para profesores/administrativos, establece has_information=false
```

**2. Expansión de Consulta** (si está habilitada):

**Archivo**: `chat_service.py` → `_expand_query()`

**Prompt para expansión**:
```
Dada la siguiente consulta del usuario, genera 2-3 variaciones o reformulaciones que puedan ayudar a encontrar información relacionada en documentos.

Consulta original: necesito saber como cambiar de carrera

Genera solo las variaciones, una por línea, sin numeración ni explicaciones:
```

**Respuesta del LLM**:
```
cómo hacer una transición profesional
guía para reorientación laboral
pasos para cambiar de profesión
```

**3. Búsqueda en Vector Store**:

**Archivo**: `vector_store_component.py` → `get_retriever()`

- Busca con la consulta original
- Busca con cada variación expandida
- **Filtra archivos temporales** (que empiezan con "tmp")
- Combina resultados únicos
- Ordena por score (relevancia)

**4. Filtrado por Rol**:

**Archivo**: `role_based_postprocessor.py` (si user_role = "estudiante")

- Prioriza documentos que empiezan con `unemi_`
- Reordena resultados para estudiantes

**5. Reranking** (opcional, actualmente deshabilitado):

- Usa modelo cross-encoder para reordenar por relevancia

**6. Construcción del Contexto**:

LlamaIndex construye el contexto final con:
- Top 10 documentos más relevantes (similarity_top_k)
- Chunks de texto de cada documento
- Metadata (file_name, page_label)

**Contexto enviado al LLM**:
```
Use the context information below to assist the user.
--------------------
[Chunk 1 del documento más relevante]
[Chunk 2 del documento más relevante]
...
--------------------
ROL DEL USUARIO: ESTUDIANTE

FILTRADO CRITICO:
- SOLO usa documentos para ESTUDIANTES...
```

---

#### **PASO 10: Generación de Respuesta (2ª LLM Call)**

**Archivo**: `chat_service.py` → `chat()`

**Prompt completo al LLM**:
```
[System prompt combinado con instrucciones JSON + filtrado por rol]

[Contexto de documentos recuperados]

[User message: "necesito saber como cambiar de carrera"]
```

**Respuesta del LLM**:
```json
{
  "has_information": true,
  "response": "Para cambiar de carrera en la UNEMI, debes seguir los siguientes pasos:\n\n1. Presentar una solicitud formal al departamento académico correspondiente.\n2. Cumplir con los requisitos académicos establecidos.\n3. Obtener la aprobación del consejo académico.\n\nLos detalles específicos se encuentran en el Reglamento de Carreras.",
  "fuentes": [
    {"pagina": "15"},
    {"pagina": "16"}
  ]
}
```

**O si no encuentra información**:
```
has_information: false
Lo siento, la información proporcionada en el contexto no contiene detalles sobre cómo cambiar de carrera para estudiantes...
```

---

#### **PASO 11: Parseo de Respuesta en PrivateGPT**

**Archivo**: `chat_router.py` → `parse_json_response()`

**Proceso**:
1. Intenta parsear como JSON completo
2. Si falla, busca JSON parcial (`{"has_information": ...}`)
3. Si falla, busca patrón `has_information: false` en texto plano
4. Si falla, usa heurísticas (frases negativas, longitud)

**Resultado parseado**:
```python
{
    "has_information": True,
    "response": "Para cambiar de carrera...",
    "fuentes": [{"pagina": "15"}, {"pagina": "16"}]
}
```

**Reconstrucción del JSON**:
```python
# SIEMPRE reconstruye JSON con has_information (True o False)
response_json = json.dumps({
    "has_information": True,
    "response": "Para cambiar de carrera...",
    "fuentes": sources_list  # Con metadata completo
})
```

---

#### **PASO 12: Respuesta HTTP a BalconDemo**

**Response de PrivateGPT**:
```json
{
  "id": "uuid",
  "object": "completion",
  "created": 1234567890,
  "model": "private-gpt",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "{\"has_information\":true,\"response\":\"Para cambiar de carrera...\",\"fuentes\":[{\"pagina\":\"15\"}]}"
    },
    "sources": [
      {
        "doc_id": "...",
        "score": 0.85,
        "document": {
          "doc_metadata": {
            "file_name": "Reglamento-Carreras.pdf",
            "page_label": "15"
          }
        }
      }
    ]
  }]
}
```

---

#### **PASO 13: Parseo en BalconDemo**

**Archivo**: `privategpt_response_parser.py` → `parse()`

**Proceso**:
1. Extrae `content` del message
2. Intenta parsear como JSON
3. Si falla, busca patrón `has_information: false`
4. Extrae `response` y `has_information`
5. Extrae `fuentes` desde `sources` del response

**Resultado**:
```python
{
    "has_information": True,
    "response": "Para cambiar de carrera...",
    "fuentes": [
        {"archivo": "Reglamento-Carreras.pdf", "pagina": "15"},
        {"archivo": "Reglamento-Carreras.pdf", "pagina": "16"}
    ]
}
```

**Validación con Heurísticas**:
```python
if has_information_from_json is not None:
    # Validar que si viene true, realmente haya información útil
    has_information = _validate_has_information(
        has_information_from_json, response_text, fuentes
    )
```

**Heurísticas de validación**:
- Si `has_information = False` → devolver `False`
- Si `has_information = True` pero:
  - No hay fuentes → `False`
  - Respuesta muy corta (< 50 chars) → `False`
  - Contiene patrones de disculpa → `False`
- Si pasa todas las validaciones → `True`

---

#### **PASO 14: Agrupación de Fuentes**

**Archivo**: `privategpt_chat_service.py` → `_agrupar_fuentes_por_archivo()`

**Entrada**:
```python
[
    {"archivo": "Reglamento-Carreras.pdf", "pagina": "15"},
    {"archivo": "Reglamento-Carreras.pdf", "pagina": "16"},
    {"archivo": "Reglamento-Carreras.pdf", "pagina": "15"}  # Duplicado
]
```

**Salida**:
```python
[
    {
        "archivo": "Reglamento-Carreras.pdf",
        "paginas": ["15", "16"]  # Ordenadas y sin duplicados
    }
]
```

---

#### **PASO 15: Construcción de Respuesta Final**

**Archivo**: `privategpt_chat_service.py` → `_handle_confirmation_stage()`

**Si `has_information = True`**:
```python
return {
    "summary": "Para cambiar de carrera...",
    "has_information": True,
    "fuentes": [
        {"archivo": "Reglamento-Carreras.pdf", "paginas": ["15", "16"]}
    ],
    "source_pdfs": ["Reglamento-Carreras.pdf"],
    "needs_confirmation": False,
    "confirmed": True,
    ...
}
```

**Si `has_information = False`**:
```python
# Determinar departamento para handoff
depto = _determinar_departamento_handoff(...)
# Resultado: "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"

return {
    "summary": "Este caso necesita ser revisado por mis compañeros humanos...",
    "has_information": False,
    "handoff": True,
    "handoff_channel": depto,
    "needs_handoff_details": True,
    ...
}
```

---

#### **PASO 16: Respuesta al Frontend**

**Archivo**: `views.py` → `chat_api()`

**JSON Response**:
```json
{
  "message": "Para cambiar de carrera...",
  "response": "Para cambiar de carrera...",
  "has_information": true,
  "fuentes": [
    {
      "archivo": "Reglamento-Carreras.pdf",
      "paginas": ["15", "16"]
    }
  ],
  "source_pdfs": ["Reglamento-Carreras.pdf"],
  "needs_confirmation": false,
  "confirmed": true,
  "intent_slots": {
    "intent_short": "consultar información sobre cambio de carrera",
    "answer_type": "informativo",
    ...
  },
  ...
}
```

---

## 📝 SISTEMA DE PROMPTS

### 1. Prompt de Intención (BalconDemo → LLM)

**Archivo**: `intent_parser.py` → `INTENT_SYSTEM`

**Propósito**: Extraer intención estructurada del mensaje del usuario

**Estructura del JSON esperado**:
```json
{
  "intent_short": "string",
  "intent_code": "string",
  "accion": "string",
  "objeto": "string",
  "needs_confirmation": boolean,
  "confirm_text": "string",
  "answer_type": "informativo" | "operativo"
}
```

**Reglas clave**:
- `needs_confirmation`: `true` si la intención no está 100% clara
- `answer_type`: 
  - `"informativo"`: preguntas, consultas, "cómo hacer X"
  - `"operativo"`: cambios de estado, trámites que requieren acción humana
- `confirm_text`: frase amigable en español para confirmar

---

### 2. Prompt del Sistema en PrivateGPT

**Archivo**: `settings-docker.yaml` → `default_query_system_prompt`

**Propósito**: Instruir al LLM a retornar JSON con formato específico

**Contenido**:
```
Eres un asistente RAG. Debes responder exclusivamente con un JSON válido en UTF-8,
sin texto adicional, sin backticks y sin bloques de código.

Formato de salida obligatorio:
- Un objeto JSON con las claves:
  - has_information: booleano (true o false)
  - response: string en español, claro y natural
  - fuentes: lista de objetos; cada objeto con la clave pagina (string)
```

**Combinación con prompt personalizado**:
- PrivateGPT combina automáticamente `default_query_system_prompt` + system message de BalconDemo
- El system message de BalconDemo contiene solo instrucciones de filtrado por rol
- El formato JSON viene del `default_query_system_prompt`

---

### 3. Prompt de Filtrado por Rol

**Archivo**: `privategpt_chat_service.py` → `_build_role_context_message()`

**Para ESTUDIANTE**:
```
ROL DEL USUARIO: ESTUDIANTE

FILTRADO CRITICO:
- SOLO usa documentos para ESTUDIANTES (reglamentos estudiantiles, procesos académicos estudiantiles, servicios estudiantiles, becas estudiantiles)
- IGNORA documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente)
- IGNORA documentos para PERSONAL ADMINISTRATIVO
- Si el contexto contiene SOLO información para profesores/administrativos, establece has_information=false
```

**Para PROFESOR**:
```
ROL DEL USUARIO: PROFESOR

FILTRADO CRITICO:
- SOLO usa documentos para PROFESORES (reglamento docente, escalafón docente, evaluación docente, procesos académicos para profesores)
- IGNORA documentos para ESTUDIANTES (procesos de matrícula estudiantil, servicios estudiantiles)
- IGNORA documentos para PERSONAL ADMINISTRATIVO
- Si el contexto contiene SOLO información para estudiantes/administrativos, establece has_information=false
```

**Para EXTERNO**:
```
ROL DEL USUARIO: EXTERNO

FILTRADO:
- Prioriza información general de la universidad
- Evita información muy específica de procesos internos
- Si el contexto contiene información muy específica de procesos internos, establece has_information=false
```

---

## 🔍 SISTEMA DE DETECCIÓN DE `has_information`

### Flujo Completo

#### **1. Generación en PrivateGPT (LLM)**

El LLM genera la respuesta y decide `has_information` basándose en:
- Si encontró información relevante en el contexto
- Si el contexto contiene solo información para otros roles
- Si la respuesta es una disculpa

**Formato esperado**:
```json
{
  "has_information": true,
  "response": "...",
  "fuentes": [...]
}
```

**O**:
```
has_information: false
Lo siento, no encontré información...
```

---

#### **2. Parseo en PrivateGPT (`chat_router.py`)**

**Función**: `parse_json_response()`

**Proceso**:
1. **Intenta parsear JSON completo**: Busca `{...}` balanceado
2. **Intenta parsear JSON parcial**: Busca `{"has_information": ...}` embebido
3. **Busca patrón en texto plano**: `has_information: false` o `has_information=false`
4. **Fallback heurístico**: 
   - Busca frases negativas ("no tengo información", "lo siento", etc.)
   - Verifica longitud mínima (< 50 chars → `false`)
   - Si no hay fuentes y es disculpa → `false`

**Patrones detectados**:
- `has_information: false`
- `has_information=false`
- `has_information = false`
- `"has_information": false`

**Reconstrucción del JSON**:
```python
# SIEMPRE reconstruye JSON con has_information (True o False)
response_json = json.dumps({
    "has_information": has_info,  # True o False
    "response": clean_response,
    "fuentes": sources_list
})
```

---

#### **3. Parseo en BalconDemo (`privategpt_response_parser.py`)**

**Función**: `_extract_response_and_has_info()`

**Proceso similar**:
1. Intenta parsear JSON completo
2. Intenta parsear JSON parcial
3. Busca patrón `has_information: false` en texto plano
4. Si no encuentra → `has_information = None`

**Validación con Heurísticas**:
```python
if has_information_from_json is not None:
    # Validar que si viene true, realmente haya información útil
    has_information = _validate_has_information(
        has_information_from_json, response_text, fuentes
    )
```

**Heurísticas de `_validate_has_information()`**:
- Si `has_information = False` → devolver `False`
- Si `has_information = True` pero:
  - No hay fuentes → `False`
  - Respuesta muy corta (< 50 chars) → `False`
  - Contiene patrones de disculpa → `False`
- Si pasa todas → `True`

**Patrones de disculpa** (`DISCULPA_PATTERNS`):
```python
[
    "no tengo información",
    "no encuentro información",
    "no puedo ayudarte",
    "te sugiero que te pongas en contacto",
    "lo siento, no",
    "lamentablemente no encontré",
    ...
]
```

---

## 🎯 SISTEMA DE INTENCIONES

### Extracción de Intención

**Archivo**: `intent_parser.py` → `interpretar_intencion_principal()`

**LLM Call**: 1 llamada al LLM (Gemini)

**Input**:
```
INTENT_SYSTEM + "\n\nTEXTO:\n" + user_text
```

**Output JSON**:
```json
{
  "intent_short": "consultar información sobre cambio de carrera",
  "intent_code": "otro",
  "accion": "consultar",
  "objeto": "carrera",
  "asignatura": "",
  "unidad_o_actividad": "",
  "periodo": "",
  "detalle_libre": "necesito saber como cambiar de carrera",
  "original_user_message": "necesito saber como cambiar de carrera",
  "needs_confirmation": false,
  "confirm_text": "¿Quieres consultar información sobre cómo cambiar de carrera?",
  "answer_type": "informativo"
}
```

**Normalización**:
- `needs_confirmation`: Convierte string a bool
- `answer_type`: Valida que sea "informativo" o "operativo"
- Si `confirm_text` está vacío pero `needs_confirmation = True` → genera uno básico

---

### Clasificación Heurística (Sin LLM)

**Archivo**: `handoff.py` → `classify_with_heuristics()`

**Input**: `intent_slots` (del paso anterior)

**Proceso**:
1. Extrae `intent_code`, `accion`, `objeto`, `detalle_libre`
2. Aplica reglas heurísticas basadas en `handoff_config.json`
3. Determina `answer_type`, `department`, `channel`

**Reglas de ejemplo**:
```python
# Cambio de paralelo
if "paralelo" in texto or "paralelo" in objeto:
    department = "académico"
    channel = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"

# Beca estudiantil
elif "beca" in texto or "beca" in objeto:
    department = "bienestar"
    channel = "DIRECCIÓN DE BIENESTAR UNIVERSITARIO"

# Biblioteca
elif "biblioteca" in texto or "libro" in texto:
    department = "general"
    channel = "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN"
```

**Output**:
```python
{
    "answer_type": "informativo",
    "department": "académico",
    "channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "reasoning": "Clasificado por reglas heurísticas"
}
```

---

## 🔀 SISTEMA DE HANDOFF

### Determinación de Departamento

**Archivo**: `privategpt_chat_service.py` → `_determinar_departamento_handoff()`

**Prioridad**:
1. **Desde categoría/subcategoría** (si están disponibles):
   ```python
   if category and subcategory:
       depto = get_departamento_real(category, subcategory)
   ```

2. **Desde heurísticas** (si hay `intent_slots`):
   ```python
   if intent_slots:
       heuristic_classification = classify_with_heuristics(intent_slots)
       depto = heuristic_classification.get("channel")
   ```

3. **Por defecto**:
   ```python
   default_depto = "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
   ```

---

### Mapeo de Categorías

**Archivo**: `handoff_config.json`

**Estructura**:
```json
{
  "mapeo_categoria_subcategoria": {
    "Academico": {
      "Cambio de paralelo": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
      "Cambio de carrera": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
      ...
    },
    "Bienestar estudiantil": {
      "Beca estudiantil": "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
      ...
    }
  },
  "mapeo_por_intencion": {
    "beca": "DIRECCIÓN DE BIENESTAR UNIVERSITARIO",
    "biblioteca": "CENTRO DE RECURSOS PARA EL APRENDIZAJE Y LA INVESTIGACIÓN",
    ...
  }
}
```

---

## 🔄 FLUJO DE ESTADOS (Stages)

### Estados Posibles

```python
class ConversationStage(Enum):
    GREETING = "greeting"                    # Saludo inicial
    AWAIT_INTENT = "await_intent"            # Esperando interpretar intención
    AWAIT_CONFIRM = "await_confirm"          # Esperando confirmación del usuario
    AWAIT_RELATED_REQUEST = "await_related_request"  # Esperando selección de solicitud relacionada
    AWAIT_HANDOFF_DETAILS = "await_handoff_details"  # Esperando detalles para handoff
```

### Detección de Stage

**Archivo**: `privategpt_chat_service.py` → `_detect_stage_from_history()`

**Lógica**:
1. Busca en el historial el último mensaje con `needs_confirmation: true`
2. Si encuentra → `AWAIT_CONFIRM`
3. Busca mensaje con `needs_related_request_selection: true`
4. Si encuentra → `AWAIT_RELATED_REQUEST`
5. Busca mensaje con `handoff: true` y `needs_handoff_details: true`
6. Si encuentra → `AWAIT_HANDOFF_DETAILS`
7. Por defecto → `AWAIT_INTENT`

---

## 📊 CONTEO DE LLAMADAS AL LLM

### Por Consulta Informativa Normal

1. **`interpretar_intencion_principal()`** → **1 LLM call**
   - Extrae intención, `needs_confirmation`, `confirm_text`, `answer_type`

2. **PrivateGPT RAG** → **1 LLM call**
   - Expansión de consulta (opcional, si está habilitada) → **+1 LLM call**
   - Generación de respuesta con contexto → **1 LLM call**

**Total**: **2-3 LLM calls** (dependiendo de si la expansión está habilitada)

---

### Por Consulta Operativa

1. **`interpretar_intencion_principal()`** → **1 LLM call**

**Total**: **1 LLM call**

---

### Por Reinterpretación

Si el usuario dice "no, eso no era":
- Otra vez `interpretar_intencion_principal()` → **+1 LLM call**
- (Opcionalmente) PrivateGPT RAG → **+1 LLM call**

**Total adicional**: **1-2 LLM calls**

---

## 🧹 SISTEMA DE LIMPIEZA DE ARCHIVOS TEMPORALES

### Limpieza Automática

**1. Al iniciar PrivateGPT** (`ingest_service.py`):
```python
def __init__(self, ...):
    ...
    self._cleanup_tmp_files_on_startup()
```

**2. Después de cada ingestión** (`privategpt_client.py`):
```python
def ingest_file(self, file_path: str):
    result = response.json()
    self._cleanup_tmp_files()  # Automático
    return result
```

**3. Al iniciar Django** (`apps.py`):
```python
def ready(self):
    client.cleanup_all_tmp_files()
```

---

### Filtrado en Búsquedas RAG

**Archivo**: `vector_store_component.py` → `get_retriever()`

**Wrapper `FilteredRetriever`**:
```python
def retrieve(self, query_bundle):
    nodes = self.base_retriever.retrieve(query_bundle)
    # Filtrar nodos de archivos temporales
    filtered_nodes = [
        node for node in nodes
        if not node_metadata.get('file_name', '').lower().startswith('tmp')
    ]
    return filtered_nodes
```

**También en expansión de consultas** (`chat_service.py`):
```python
# Filtrar archivos que empiezan con "tmp"
if file_name.lower().startswith('tmp'):
    continue
```

---

## 🔐 SISTEMA DE ROLES Y FILTRADO

### Extracción de Rol

**Archivo**: `privategpt_chat_service.py` → `_extract_user_role()`

**Fuente**: `student_data` desde `data_unemi.json`

**Estructura**:
```json
{
  "perfiles": [
    {
      "id": "1",
      "es_estudiante": true,
      "es_profesor": false,
      "status": true,
      "inscripcionprincipal": true,
      ...
    }
  ]
}
```

**Lógica**:
1. Busca perfil por `perfil_id` (si se proporciona)
2. Si no, busca perfil con `inscripcionprincipal: true`
3. Si no, usa el primer perfil activo
4. Determina rol según flags: `es_estudiante`, `es_profesor`, etc.

---

### Filtrado por Rol en PrivateGPT

**Archivo**: `role_based_postprocessor.py`

**Para estudiantes**:
- Prioriza documentos que empiezan con `unemi_`
- Reordena resultados para que documentos estudiantiles aparezcan primero

**Archivo**: `chat_service.py` → `_chat_engine()`

```python
if user_role == "estudiante":
    role_postprocessor = RoleBasedPostprocessor(user_role=user_role)
    node_postprocessors.append(role_postprocessor)
```

---

## 📡 COMUNICACIÓN HTTP

### Request de BalconDemo a PrivateGPT

**Endpoint**: `POST http://localhost:8001/v1/chat/completions`

**Headers**:
```http
Content-Type: application/json
Connection: close
```

**Body**:
```json
{
  "messages": [
    {"role": "system", "content": "ROL DEL USUARIO: ESTUDIANTE\n\nFILTRADO CRITICO:..."},
    {"role": "user", "content": "necesito saber como cambiar de carrera"}
  ],
  "use_context": true,
  "include_sources": true,
  "stream": false,
  "session_context": {
    "user_role": "estudiante",
    "profile_type": "ESTUDIANTE",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería"
  }
}
```

---

### Response de PrivateGPT a BalconDemo

**Status**: `200 OK`

**Body**:
```json
{
  "id": "uuid",
  "object": "completion",
  "created": 1234567890,
  "model": "private-gpt",
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "{\"has_information\":true,\"response\":\"Para cambiar de carrera...\",\"fuentes\":[{\"pagina\":\"15\"}]}"
    },
    "sources": [
      {
        "doc_id": "...",
        "score": 0.85,
        "document": {
          "doc_metadata": {
            "file_name": "Reglamento-Carreras.pdf",
            "page_label": "15"
          }
        }
      }
    ]
  }]
}
```

---

## 🎨 FLUJO DE CONFIRMACIONES

### Cuando `needs_confirmation = True`

**Flujo**:
1. Usuario envía mensaje
2. `interpretar_intencion_principal()` retorna `needs_confirmation: true`
3. Sistema muestra `confirm_text` al usuario
4. Usuario confirma ("sí", "correcto", etc.)
5. Sistema procede con la intención confirmada

**Ejemplo**:
```
Usuario: "quiero cambiar"
LLM: needs_confirmation=true, confirm_text="¿Quieres solicitar un cambio de paralelo?"
Sistema muestra: "¿Quieres solicitar un cambio de paralelo?"
Usuario: "sí"
Sistema procede con cambio de paralelo
```

---

### Cuando `needs_confirmation = False`

**Flujo**:
1. Usuario envía mensaje
2. `interpretar_intencion_principal()` retorna `needs_confirmation: false`
3. Sistema procede directamente sin mostrar confirmación

**Ejemplo**:
```
Usuario: "necesito saber como cambiar de carrera"
LLM: needs_confirmation=false, answer_type="informativo"
Sistema procede directamente a PrivateGPT
```

---

## 🔄 FLUJO DE SOLICITUDES RELACIONADAS

### Búsqueda de Solicitudes Relacionadas

**Archivo**: `related_request_matcher.py` → `find_related_requests()`

**Proceso**:
1. Carga solicitudes previas del estudiante
2. Compara con la intención actual usando embeddings o texto
3. Retorna solicitudes relacionadas (máximo 3)

**Si encuentra solicitudes relacionadas**:
- Muestra opción para relacionar
- Usuario puede seleccionar una o continuar sin relacionar

**Si no encuentra**:
- Continúa con el flujo normal (PrivateGPT o handoff)

---

## 📋 RESUMEN DE LLAMADAS AL LLM

### Escenario 1: Consulta Informativa Simple

```
Usuario: "¿Cómo cambio de carrera?"
```

**LLM Calls**:
1. `interpretar_intencion_principal()` → 1 call
2. PrivateGPT RAG → 1 call
   - (Opcional) Expansión de consulta → +1 call

**Total**: **2-3 calls**

---

### Escenario 2: Consulta Operativa

```
Usuario: "Quiero cambiar de paralelo"
```

**LLM Calls**:
1. `interpretar_intencion_principal()` → 1 call

**Total**: **1 call**

---

### Escenario 3: Consulta con Confirmación

```
Usuario: "quiero cambiar"
LLM: needs_confirmation=true
Usuario: "sí, paralelo"
```

**LLM Calls**:
1. `interpretar_intencion_principal()` → 1 call (primera vez)
2. `interpretar_intencion_principal()` → 1 call (después de confirmar)

**Total**: **2 calls**

---

## 🛠️ CONFIGURACIÓN Y ARCHIVOS CLAVE

### Archivos de Configuración

1. **`handoff_config.json`**: Mapeo de categorías → departamentos
2. **`data_unemi.json`**: Datos de estudiantes y perfiles
3. **`settings-docker.yaml`**: Configuración de PrivateGPT (prompts, RAG)
4. **`settings-gemini.yaml`**: Configuración específica de Gemini

---

### Variables de Entorno

- `PRIVATEGPT_API_URL`: URL de PrivateGPT (default: `http://localhost:8001`)
- `GOOGLE_API_KEY`: API key de Gemini
- `PGPT_MODE`: Modo del LLM (`gemini`, `ollama`, etc.)

---

## 🎯 PUNTOS CLAVE DEL SISTEMA

### 1. Reducción de LLM Calls

- **Antes**: 5-7 LLM calls por consulta
- **Ahora**: 2-3 LLM calls por consulta
- **Optimización**: Fusionar intención + confirmación + answer_type en 1 call

### 2. Clasificación Sin LLM

- `classify_with_heuristics()` usa solo reglas y `handoff_config.json`
- No requiere LLM para determinar department/channel

### 3. Filtrado Automático

- Archivos temporales se filtran automáticamente en búsquedas RAG
- Limpieza automática al iniciar servicios

### 4. Validación Robusta

- Múltiples capas de validación de `has_information`
- Heurísticas como fallback si el LLM falla

### 5. Filtrado por Rol

- Priorización de documentos según rol del usuario
- Filtrado crítico en el prompt del sistema

---

## 📝 NOTAS TÉCNICAS

### Normalización de Texto

**Archivo**: `privategpt_chat_service.py` → `_normalize_text_for_llm()`

- Quita tildes y caracteres especiales antes de enviar al LLM
- Mejora la compatibilidad con modelos que tienen problemas con caracteres especiales

### Manejo de Errores

- Si PrivateGPT no está disponible → retorna mensaje de error amigable
- Si el LLM falla → usa fallbacks heurísticos
- Si el parseo falla → usa heurísticas de texto

### Timeouts

- Health check: 5 segundos
- Chat completion: 60 segundos
- File ingestion: 60 segundos (timeout * 2)

---

Este documento cubre el funcionamiento completo del sistema. ¿Hay algún aspecto específico que quieras que profundice más?


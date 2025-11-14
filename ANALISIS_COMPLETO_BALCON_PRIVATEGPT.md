# Análisis Completo: BalconDemo y PrivateGPT

## Tabla de Contenidos
1. [Arquitectura General](#arquitectura-general)
2. [BalconDemo - Sistema Completo](#balcondemo---sistema-completo)
3. [PrivateGPT - Sistema Completo](#privategpt---sistema-completo)
4. [Comunicación Entre Sistemas](#comunicación-entre-sistemas)
5. [Flujo Completo de una Consulta](#flujo-completo-de-una-consulta)
6. [Prompts y Llamadas LLM](#prompts-y-llamadas-llm)
7. [Archivos y Estructura](#archivos-y-estructura)

---

## Arquitectura General

### Componentes Principales

```
┌─────────────────┐         ┌──────────────────┐
│   Frontend      │         │   BalconDemo     │
│   (Svelte)      │◄───────►│   (Django)       │
│                 │         │                  │
└─────────────────┘         └────────┬─────────┘
                                     │
                                     │ HTTP REST API
                                     │
                            ┌────────▼─────────┐
                            │   PrivateGPT     │
                            │   (FastAPI)      │
                            │                  │
                            └────────┬─────────┘
                                     │
                            ┌────────▼─────────┐
                            │   Vector Store   │
                            │   (Qdrant)       │
                            │                  │
                            └──────────────────┘
```

### Tecnologías Utilizadas

**BalconDemo:**
- Django (Backend)
- Svelte 4 (Frontend)
- LangChain (LLM Client)
- Google Gemini 2.5 Flash (LLM)

**PrivateGPT:**
- FastAPI (Backend)
- LlamaIndex (RAG Framework)
- Google Gemini 2.5 Flash (LLM)
- Qdrant (Vector Store)
- Sentence Transformers (Embeddings)

---

## BalconDemo - Sistema Completo

### 1. Estructura de Archivos Principales

```
app/
├── services/
│   ├── privategpt_chat_service.py    # Orquestador principal
│   ├── intent_parser.py               # Extracción de intención
│   ├── privategpt_client.py          # Cliente HTTP para PrivateGPT
│   ├── privategpt_response_parser.py # Parser de respuestas
│   ├── handoff.py                    # Lógica de derivación
│   ├── config.py                     # Configuración LLM y rate limiting
│   ├── conversation_types.py         # Enums de estados
│   ├── related_request_matcher.py   # Matching de solicitudes
│   └── solicitud_service.py          # Gestión de solicitudes
├── views.py                          # Endpoints Django
└── data/
    ├── handoff_config.json           # Configuración de handoff
    └── data_unemi.json              # Datos de estudiantes
```

### 2. Flujo Principal: `classify_with_privategpt()`

**Ubicación:** `app/services/privategpt_chat_service.py`

#### 2.1. Entrada

```python
def classify_with_privategpt(
    user_text: str,
    conversation_history: List[Dict],
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    student_data: Optional[Dict] = None,
    perfil_id: Optional[str] = None,
    uploaded_file: Any = None
) -> Dict[str, Any]
```

**Parámetros:**
- `user_text`: Mensaje del usuario
- `conversation_history`: Historial de conversación
- `category/subcategory`: Categorías seleccionadas (opcional)
- `student_data`: Datos completos del estudiante desde `data_unemi.json`
- `perfil_id`: ID del perfil activo
- `uploaded_file`: Archivo subido (PDF/imagen)

#### 2.2. Procesamiento de Archivos

Si hay un archivo subido:
1. Guarda temporalmente el archivo
2. Llama a `client.ingest_file(tmp_path)` para ingestionarlo en PrivateGPT
3. Elimina el archivo temporal

#### 2.3. Detección de Confirmaciones

**ANTES** de detectar el stage, verifica si el mensaje es una confirmación:

```python
is_confirmation_positive = es_confirmacion_positiva(user_text)  # "si", "sí", "correcto"
is_confirmation_negative = es_confirmacion_negativa(user_text)  # "no", "negativo"
```

Si es confirmación positiva:
- Busca en el historial el último mensaje del bot con `needs_confirmation=True`
- Recupera `pending_slots` desde ese mensaje
- Llama a `_handle_confirmation_stage()` con esos slots

Si es confirmación negativa:
- Retorna mensaje pidiendo que reformule la solicitud

#### 2.4. Detección de Stage

```python
stage, pending_slots, handoff_channel = _detect_stage_from_history(conversation_history)
```

**Stages posibles:**
- `GREETING`: Saludo inicial
- `AWAIT_INTENT`: Esperando intención del usuario
- `AWAIT_CONFIRM`: Esperando confirmación de detalles
- `AWAIT_RELATED_REQUEST`: Esperando selección de solicitud relacionada
- `AWAIT_HANDOFF_DETAILS`: Esperando detalles para handoff
- `ANSWER_READY`: Respuesta lista para mostrar

#### 2.5. Manejo por Stage

**A) GREETING:**
```python
if es_greeting(user_text):
    nombre = obtener_primer_nombre(student_data)  # Capitalizado correctamente
    saludo = f"Hola{' ' + nombre if nombre else ''}! 👋 Soy tu asistente..."
    return _build_frontend_response(...)
```

**B) AWAIT_CONFIRM:**
- Si es confirmación positiva → `_handle_confirmation_stage()`
- Si es confirmación negativa → Mensaje de reformulación
- Si no es confirmación → Reinterpretar intención con `interpretar_intencion_principal()`

**C) AWAIT_RELATED_REQUEST:**
- Detecta si el usuario seleccionó una solicitud o dijo "no hay"
- Recupera `intent_slots` y `original_user_request`
- Si seleccionó solicitud → Usa esa solicitud como contexto
- Si dijo "no hay" → Continúa sin relacionar
- Procede con el flujo informativo/operativo

**D) AWAIT_HANDOFF_DETAILS:**
- Usuario está proporcionando detalles para handoff
- Crea solicitud en el sistema usando `crear_solicitud()`
- Retorna mensaje de confirmación de envío

**E) AWAIT_INTENT (Default):**
- Flujo principal de interpretación y respuesta

### 3. Interpretación de Intención: `interpretar_intencion_principal()`

**Ubicación:** `app/services/intent_parser.py`

#### 3.1. Prompt del Sistema (INTENT_SYSTEM)

```python
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
  "answer_type": "<informativo o operativo>"
}
...
"""
```

#### 3.2. Llamada al LLM

```python
prompt = f"{INTENT_SYSTEM}\n\nTEXTO:\n{texto_usuario}\n"
out = guarded_invoke(llm, prompt)  # Rate-limited (9 RPM)
raw = getattr(out, "content", str(out)).strip()
```

**Rate Limiting:**
- Token bucket: 9 tokens por minuto
- Implementado en `config.py` con `guarded_invoke()`
- Respeta límites de Google Gemini API

#### 3.3. Parsing de Respuesta

```python
m = re.search(r"\{[\s\S]*\}", raw)  # Extraer JSON
blob = m.group(0) if m else raw
data = json.loads(blob)
```

**Normalización:**
- `needs_confirmation`: Convierte a bool
- `answer_type`: Valida que sea "informativo" o "operativo"
- Si `confirm_text` está vacío pero `needs_confirmation=True`, genera uno básico

### 4. Clasificación Heurística: `classify_with_heuristics()`

**Ubicación:** `app/services/handoff.py`

**NO usa LLM**, solo reglas deterministas:

```python
def classify_with_heuristics(intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clasificación determinista usando heurísticas.
    Usa intent_code, accion, objeto y texto libre para mapear a department/channel.
    """
    # 1) Determinar answer_type (ya viene del LLM, pero validamos)
    answer_type = intent.get("answer_type", "informativo")
    
    # 2) Determinar department/channel desde handoff_config.json
    texto_completo = f"{texto} {objeto} {accion}".lower()
    
    # Mapeo por keywords del mapeo_por_intencion
    mapeo_intencion = get_handoff_config().get("mapeo_por_intencion", {})
    for keyword, dept_real in mapeo_intencion.items():
        if keyword.lower() in texto_completo:
            channel = dept_real
            department = get_department_from_channel(channel)
            return {...}
    
    # Casos comunes: cambio de paralelo, beca, pago, biblioteca, etc.
    # ...
```

**Mapeos desde `handoff_config.json`:**
- `mapeo_categoria_subcategoria`: Mapeo exacto por categoría/subcategoría
- `mapeo_por_intencion`: Mapeo por keywords en el texto

### 5. Respuestas con Datos del Estudiante

**Intenciones que NO requieren LLM ni PrivateGPT:**

```python
DATA_INTENTS = {
    "consultar_solicitudes_balcon",
    "consultar_carrera_actual",
    "consultar_roles_usuario",
    "consultar_datos_personales",
}
```

Se responden directamente desde `student_data` (JSON).

### 6. Llamada a PrivateGPT: `_call_privategpt_rag()`

**Ubicación:** `app/services/privategpt_chat_service.py`

#### 6.1. Construcción de Mensajes

```python
def _build_role_context_message(user_text: str, rol: str) -> List[Dict[str, str]]:
    """
    Construye mensajes con contexto de rol para PrivateGPT.
    """
    # Mensaje system con filtrado por rol
    system_content = f"""
    IMPORTANTE: El usuario es un {rol}.
    Si recibes contexto de documentos, SOLO usa documentos relevantes para {rol}.
    IGNORA documentos que sean para otros roles (profesor, administrativo, etc.).
    """
    
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_text}
    ]
```

#### 6.2. Session Context

```python
session_context = {
    "user_role": rol,  # "estudiante", "profesor", etc.
    "profile_type": perfil_principal.get("tipo", ""),
    "carrera": perfil_principal.get("carrera_nombre", ""),
    "facultad": perfil_principal.get("facultad_nombre", "")
}
```

#### 6.3. Llamada HTTP

```python
response = client.chat_completion(
    messages=messages,
    use_context=True,  # Habilita RAG
    include_sources=True,  # Incluye fuentes
    stream=False,
    session_context=session_context
)
```

**Endpoint:** `POST http://localhost:8001/v1/chat/completions`

### 7. Parsing de Respuesta de PrivateGPT

**Ubicación:** `app/services/privategpt_response_parser.py`

#### 7.1. Formato Esperado

PrivateGPT retorna JSON en `choices[0].message.content`:

```json
{
  "has_information": true/false,
  "response": "Texto de respuesta...",
  "fuentes": [
    {"archivo": "documento.pdf", "pagina": "5"}
  ]
}
```

#### 7.2. Parsing Robusto

```python
def _extract_response_and_has_info(content_raw: str) -> Dict[str, Any]:
    """
    Maneja múltiples formatos:
    1. JSON válido: {"has_information": false, "response": "..."}
    2. Texto plano con has_information: "has_information: false\n..."
    3. Texto plano sin has_information
    """
    # 1. Intentar parsear como JSON completo
    if content_raw.startswith("{"):
        try:
            content_parsed = json.loads(content_raw)
            return {
                "response": content_parsed.get("response", content_raw),
                "has_information": content_parsed.get("has_information")
            }
        except:
            pass
    
    # 2. Buscar JSON parcial
    json_match = re.search(r'\{[^{}]*"has_information"[^{}]*\}', content_raw)
    if json_match:
        # Parsear JSON parcial
        ...
    
    # 3. Detectar patrón "has_information: false" en texto plano
    has_info_patterns = [
        r'has_information\s*:\s*(true|false)',
        r'has_information\s*=\s*(true|false)',
        ...
    ]
    for pattern in has_info_patterns:
        match = re.search(pattern, content_raw, re.IGNORECASE)
        if match:
            # Extraer valor y texto de respuesta
            ...
```

#### 7.3. Validación Suave

```python
# Confiar principalmente en PrivateGPT
has_info_final = bool(has_info_pgpt) if has_info_pgpt is not None else None

# Solo corregir si PrivateGPT dijo True pero la respuesta es muy corta
if has_info_final and len(response_text.strip()) < 20:
    has_info_final = False
```

### 8. Construcción de Respuesta al Frontend

**Ubicación:** `app/services/privategpt_chat_service.py`

#### 8.1. Builder Centralizado

```python
def _build_frontend_response(
    *,
    stage: ConversationStage,
    mode: ConversationMode,
    status: ConversationStatus,
    message: str,
    response: str | None = None,
    has_information: bool | None = None,
    fuentes: list | None = None,
    source_pdfs: list | None = None,
    intent_slots: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Construye la respuesta estándar hacia el frontend.
    """
    base = {
        "stage": stage.value,
        "mode": mode.value,
        "status": status.value,
        "message": message,
        "response": response or message,
        "has_information": has_information,
        "fuentes": fuentes or [],
        "source_pdfs": source_pdfs or [],
        "intent_slots": intent_slots or {},
    }
    
    # Campos legacy para compatibilidad
    base.setdefault("needs_confirmation", False)
    base.setdefault("confirmed", True)
    base.setdefault("handoff", False)
    ...
    
    return base
```

#### 8.2. Builders Específicos

- `_build_informative_answer_response()`: Respuesta informativa con fuentes
- `_build_need_confirm_response()`: Necesita confirmación
- `_build_handoff_response_new()`: Derivación a humano
- `_build_error_response()`: Error técnico

---

## PrivateGPT - Sistema Completo

### 1. Estructura de Archivos Principales

```
private_gpt/
├── server/
│   ├── chat/
│   │   ├── chat_router.py        # Endpoint /v1/chat/completions
│   │   └── chat_service.py       # Lógica de RAG
│   └── ingest/
│       └── ingest_service.py     # Ingestion de documentos
├── components/
│   ├── llm/
│   │   └── llm_component.py      # Cliente LLM (Gemini)
│   ├── embedding/
│   │   └── embedding_component.py # Modelo de embeddings
│   ├── vector_store/
│   │   └── vector_store_component.py # Qdrant
│   └── node_store/
│       └── node_store_component.py # DocStore
└── settings.yaml                  # Configuración
```

### 2. Endpoint Principal: `/v1/chat/completions`

**Ubicación:** `private_gpt/server/chat/chat_router.py`

#### 2.1. Request Body

```python
class ChatBody(BaseModel):
    messages: list[OpenAIMessage]  # [{"role": "system", "content": "..."}, ...]
    use_context: bool = False      # Habilita RAG
    context_filter: ContextFilter | None = None
    include_sources: bool = True   # Incluye fuentes
    stream: bool = False           # Streaming
    session_context: dict | None = None  # Contexto de sesión
```

#### 2.2. Procesamiento

```python
def chat_completion(request: Request, body: ChatBody):
    service = request.state.injector.get(ChatService)
    all_messages = [
        ChatMessage(content=m.content, role=MessageRole(m.role))
        for m in body.messages
    ]
    
    # Extraer user_role del session_context
    user_role = body.session_context.get("user_role") if body.session_context else None
    
    # Llamar al servicio
    completion = service.chat(
        messages=all_messages,
        use_context=body.use_context,
        context_filter=body.context_filter,
        user_role=user_role,
    )
    
    # Parsear respuesta JSON
    response_text = completion.response
    parsed_response = parse_json_response(response_text)
    clean_response = parsed_response.get("response", response_text)
    has_info = parsed_response.get("has_information_final", False)
    
    # Procesar fuentes
    sources_list = []
    if completion.sources and body.include_sources:
        # Ordenar por score y tomar top 5
        sorted_sources = sorted(completion.sources, key=lambda s: s.score, reverse=True)
        top_sources = sorted_sources[:5]
        
        for source in top_sources:
            file_name = source.document.doc_metadata.get("file_name")
            page_label = source.document.doc_metadata.get("page_label")
            sources_list.append({
                "archivo": file_name,
                "pagina": str(page_label)
            })
    
    # SIEMPRE reconstruir JSON
    response_json = json.dumps({
        "has_information": has_info,
        "response": clean_response,
        "fuentes": sources_list
    }, ensure_ascii=False)
    
    return to_openai_response(response_json, completion.sources)
```

### 3. Servicio de Chat: `ChatService.chat()`

**Ubicación:** `private_gpt/server/chat/chat_service.py`

#### 3.1. Construcción del Chat Engine

```python
def _chat_engine(
    self,
    system_prompt: str | None = None,
    use_context: bool = False,
    context_filter: ContextFilter | None = None,
    user_role: str | None = None,
) -> BaseChatEngine:
    if use_context:
        # Crear retriever base
        base_retriever = self.vector_store_component.get_retriever(
            index=self.index,
            context_filter=context_filter,
            similarity_top_k=self.settings.rag.similarity_top_k,  # 10
        )
        
        # Retriever con expansión de consulta (si está habilitado)
        if settings.rag.query_expansion:
            vector_index_retriever = QueryExpansionRetriever(
                base_retriever,
                self._expand_query,  # Función que expande consultas
                self.llm_component.llm
            )
        
        # Postprocessors
        node_postprocessors = [
            MetadataReplacementPostProcessor(target_metadata_key="window"),
        ]
        
        # Postprocessor basado en rol (para estudiantes)
        if user_role == "estudiante":
            role_postprocessor = RoleBasedPostprocessor(user_role=user_role)
            node_postprocessors.append(role_postprocessor)
            # Prioriza documentos que empiezan con "unemi_"
        
        # Filtro de similitud (si está habilitado)
        if settings.rag.similarity_value:
            node_postprocessors.append(
                SimilarityPostprocessor(similarity_cutoff=settings.rag.similarity_value)
            )
        
        # Reranking (si está habilitado)
        if settings.rag.rerank.enabled:
            rerank_postprocessor = SentenceTransformerRerank(
                model=settings.rag.rerank.model,
                top_n=settings.rag.rerank.top_n
            )
            node_postprocessors.append(rerank_postprocessor)
        
        # Crear ContextChatEngine
        return ContextChatEngine.from_defaults(
            system_prompt=system_prompt,  # Combina con default_query_system_prompt
            retriever=vector_index_retriever,
            llm=self.llm_component.llm,
            node_postprocessors=node_postprocessors,
        )
    else:
        # Sin contexto, solo LLM
        return SimpleChatEngine.from_defaults(
            system_prompt=system_prompt,
            llm=self.llm_component.llm,
        )
```

#### 3.2. Expansión de Consulta

```python
def _expand_query(self, query: str) -> list[str]:
    """
    Expande la consulta usando el LLM para generar variaciones y sinónimos.
    """
    expansion_prompt = f"""Dada la siguiente consulta del usuario, genera 2-3 variaciones o reformulaciones que puedan ayudar a encontrar información relacionada en documentos. 
Incluye sinónimos, términos relacionados, y formas alternativas de expresar lo mismo.

Consulta original: {query}

Genera solo las variaciones, una por línea, sin numeración ni explicaciones:"""
    
    # Usar el LLM para generar variaciones
    response = self.llm_component.llm.complete(expansion_prompt)
    variations = [query]  # Incluir la consulta original
    
    if response and response.text:
        for line in response.text.strip().split('\n'):
            line = line.strip()
            # Limpiar prefijos comunes
            for prefix in ['-', '•', '1.', '2.', '3.', '*']:
                if line.startswith(prefix):
                    line = line[len(prefix):].strip()
            if line and len(line) > 5:
                variations.append(line)
    
    # Limitar a máximo 4 variaciones
    return variations[:4]
```

**Ejemplo:**
- Consulta original: "cómo cambiar de paralelo"
- Variaciones generadas:
  - "cómo cambiar de paralelo"
  - "procedimiento para cambiar de paralelo"
  - "solicitar cambio de paralelo"
  - "cómo solicitar cambio de grupo"

#### 3.3. QueryExpansionRetriever

```python
class QueryExpansionRetriever:
    """Retriever que expande la consulta usando el LLM antes de buscar."""
    
    def retrieve(self, query_bundle):
        # Expandir la consulta
        expanded_queries = self.expand_query(query_str)
        
        # Hacer búsquedas con todas las variaciones
        all_nodes = []
        seen_node_ids = set()
        
        for expanded_query in expanded_queries:
            nodes = self.base_retriever.retrieve(query_bundle_expanded)
            
            # Filtrar archivos temporales (tmp)
            for node in nodes:
                file_name = node_metadata.get('file_name', '')
                if file_name.lower().startswith('tmp'):
                    continue  # Filtrar archivos temporales
                
                if node_id not in seen_node_ids:
                    all_nodes.append(node)
                    seen_node_ids.add(node_id)
        
        # Ordenar por score y limitar
        all_nodes.sort(key=lambda x: x.score, reverse=True)
        return all_nodes[:top_k]
```

### 4. Prompt del Sistema

**Ubicación:** `settings-docker.yaml`

```yaml
default_query_system_prompt: >
  Eres un asistente RAG. Debes responder exclusivamente con un JSON válido en UTF-8,
  sin texto adicional, sin backticks y sin bloques de código.

  Formato de salida obligatorio (descripción, no imprimirla):
  - Un objeto JSON con las claves:
    - has_information: booleano (true o false)
    - response: string en español, claro y natural
    - fuentes: lista de objetos; cada objeto con la clave pagina (string)
  - Si no hay información relevante en el contexto:
    - imprime únicamente un objeto JSON con la clave has_information en false
    - no incluyas las claves response ni fuentes en ese caso

  FILTRADO CRITICO DE DOCUMENTOS (APLICAR ANTES DE GENERAR JSON):
  - Si recibes un contexto del sistema que especifica un ROL del usuario (estudiante, profesor, administrativo, etc.):
    - SOLO usa documentos que sean relevantes para ese ROL específico
    - IGNORA COMPLETAMENTE documentos que sean para otros roles
    - Si el contexto recuperado contiene SOLO información para otros roles, establece has_information=false
    - Si encuentras información mixta, SOLO menciona la parte relevante para el rol especificado en el campo response
  - Si NO recibes información de rol, usa todos los documentos disponibles

  Reglas:
  - No imprimas nada fuera del JSON.
  - No inventes datos ni páginas.
  - Si no es posible identificar páginas, imprime fuentes como lista vacía.
  - Ordena las páginas de menor a mayor y sin duplicados.
  - Sé tolerante con errores ortográficos en la consulta; si hay información relacionada en el contexto, has_information debe ser true.

  Tu salida debe ser un JSON válido que cumpla exactamente con las claves indicadas.
  
  IMPRIME SOLO EL JSON; cualquier texto fuera del JSON se considera error.
```

#### 4.1. Combinación de Prompts

**Ubicación:** `private_gpt/server/chat/chat_service.py`

```python
# Cuando BalconDemo envía un mensaje system, PrivateGPT lo combina con default_query_system_prompt
# El system_prompt de BalconDemo contiene filtrado por rol
# El default_query_system_prompt contiene formato JSON

# LlamaIndex combina ambos automáticamente en el ContextChatEngine
chat_engine = ContextChatEngine.from_defaults(
    system_prompt=system_prompt,  # Combina ambos prompts
    retriever=vector_index_retriever,
    llm=self.llm_component.llm,
    node_postprocessors=node_postprocessors,
)
```

### 5. Procesamiento RAG

#### 5.1. Flujo Completo

```
1. Usuario envía mensaje
   ↓
2. Extraer último mensaje del usuario
   ↓
3. Expandir consulta (si query_expansion=True)
   - Genera 2-3 variaciones usando LLM
   ↓
4. Buscar en vector store con todas las variaciones
   - Retriever busca top 10 chunks por variación
   - Filtra archivos temporales (tmp*)
   ↓
5. Postprocessors:
   a) MetadataReplacementPostProcessor: Reemplaza metadata con contexto completo
   b) RoleBasedPostprocessor (si user_role="estudiante"): Prioriza documentos "unemi_*"
   c) SimilarityPostprocessor (si similarity_value configurado): Filtra por umbral
   d) SentenceTransformerRerank (si rerank.enabled): Reordena por relevancia
   ↓
6. Construir contexto con chunks recuperados
   ↓
7. Enviar a LLM con:
   - system_prompt (combinado: filtrado por rol + formato JSON)
   - contexto de documentos
   - mensaje del usuario
   ↓
8. LLM genera respuesta JSON
   ↓
9. Parsear respuesta JSON
   ↓
10. Extraer has_information, response, fuentes
    ↓
11. Reconstruir JSON homogéneo
    ↓
12. Retornar a BalconDemo
```

#### 5.2. Filtrado por Rol

**Ubicación:** `private_gpt/components/node_store/role_based_postprocessor.py`

```python
class RoleBasedPostprocessor:
    """
    Postprocessor que prioriza documentos relevantes para el rol del usuario.
    Para estudiantes, prioriza documentos que empiezan con "unemi_".
    """
    
    def postprocess_nodes(self, nodes, query_bundle):
        if self.user_role == "estudiante":
            # Separar documentos por relevancia
            unemi_docs = []
            other_docs = []
            
            for node in nodes:
                file_name = node.node.metadata.get('file_name', '')
                if file_name.lower().startswith('unemi_'):
                    unemi_docs.append(node)
                else:
                    other_docs.append(node)
            
            # Priorizar documentos unemi_*
            return unemi_docs + other_docs
        
        return nodes
```

### 6. Parsing de Respuesta JSON

**Ubicación:** `private_gpt/server/chat/chat_router.py`

```python
def parse_json_response(response_text: str) -> dict[str, any]:
    """
    Intenta parsear una respuesta JSON del modelo.
    
    Maneja múltiples formatos:
    1. JSON válido: {"has_information": true/false, "response": "..."}
    2. Texto plano con has_information: "has_information: false\n..."
    3. Texto plano sin has_information
    """
    # 1. Intentar parsear JSON completo
    try:
        data = json.loads(response_text)
        if "has_information" in data:
            has_info_llm = data.get("has_information", False)
            response_text = data.get("response", "")
            fuentes_from_json = data.get("fuentes", []) or []
            
            has_info_final = bool(has_info_llm)
            return {
                "has_information_llm": has_info_llm,
                "has_information_final": has_info_final,
                "response": response_text,
                "fuentes_from_json": fuentes_from_json
            }
    except:
        pass
    
    # 2. Buscar JSON parcial
    json_match = re.search(r'\{[^{}]*"has_information"[^{}]*\}', response_text)
    if json_match:
        # Parsear JSON parcial
        ...
    
    # 3. Detectar patrón "has_information: false" en texto plano
    has_info_patterns = [
        r'has_information\s*:\s*(true|false)',
        r'has_information\s*=\s*(true|false)',
        ...
    ]
    for pattern in has_info_patterns:
        match = re.search(pattern, response_text, re.IGNORECASE)
        if match:
            value_str = match.group(1).lower()
            has_information = value_str in ["true", "1", "yes"]
            # Extraer texto de respuesta
            ...
            return {
                "has_information_llm": None,
                "has_information_final": has_information,
                "response": response_text,
                "fuentes_from_json": []
            }
    
    # 4. Heurística de fallback
    lowered = response_text.lower()
    has_no_info_phrase = any(phrase in lowered for phrase in [
        "no tengo información",
        "no encontré información",
        "no puedo ayudarte",
        ...
    ])
    is_too_short = len(response_text.strip()) < 50
    
    has_info_final = not (has_no_info_phrase or is_too_short)
    
    return {
        "has_information_llm": None,
        "has_information_final": has_info_final,
        "response": response_text,
        "fuentes_from_json": []
    }
```

### 7. Ingestion de Documentos

**Ubicación:** `private_gpt/server/ingest/ingest_service.py`

#### 7.1. Proceso de Ingestion

```
1. Recibir archivo (PDF, TXT, etc.)
   ↓
2. Parsear documento
   - PDF → Extraer texto por páginas
   - TXT → Dividir en chunks
   ↓
3. Crear chunks
   - Tamaño: ~512 tokens
   - Overlap: ~50 tokens
   ↓
4. Generar embeddings
   - Modelo: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
   - Dimensión: 384
   ↓
5. Almacenar en Qdrant
   - Vector: embedding
   - Metadata: file_name, page_label, doc_id, etc.
   ↓
6. Almacenar en DocStore
   - Documento completo con metadata
   ↓
7. Limpiar archivos temporales (tmp*)
   - Se ejecuta automáticamente al inicio del servicio
```

#### 7.2. Limpieza Automática de Archivos Temporales

```python
def _cleanup_tmp_files_on_startup(self):
    """
    Limpia archivos temporales (tmp*) al iniciar el servicio.
    """
    try:
        documents = self.list_documents()
        tmp_docs = [
            doc for doc in documents
            if doc.get("doc_metadata", {}).get("file_name", "").lower().startswith("tmp")
        ]
        
        for doc in tmp_docs:
            self.delete_document(doc.get("doc_id"))
    except Exception as e:
        logger.warning(f"Error en limpieza automática: {e}")
```

---

## Comunicación Entre Sistemas

### 1. Protocolo HTTP REST

**BalconDemo → PrivateGPT:**

```
POST http://localhost:8001/v1/chat/completions
Content-Type: application/json

{
  "messages": [
    {"role": "system", "content": "IMPORTANTE: El usuario es un estudiante..."},
    {"role": "user", "content": "¿Cómo cambio de paralelo?"}
  ],
  "use_context": true,
  "include_sources": true,
  "stream": false,
  "session_context": {
    "user_role": "estudiante",
    "profile_type": "estudiante",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería"
  }
}
```

**PrivateGPT → BalconDemo:**

```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "chatcmpl-123",
  "object": "completion",
  "created": 1694268190,
  "model": "private-gpt",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"has_information\": true, \"response\": \"Para cambiar de paralelo...\", \"fuentes\": [{\"archivo\": \"Reglamento.pdf\", \"pagina\": \"15\"}]}"
      },
      "sources": [
        {
          "document": {
            "doc_metadata": {
              "file_name": "Reglamento.pdf",
              "page_label": "15"
            }
          },
          "score": 0.85
        }
      ]
    }
  ]
}
```

### 2. Formato de Mensajes

**BalconDemo envía:**
- `role: "system"`: Instrucciones de filtrado por rol
- `role: "user"`: Mensaje del usuario

**PrivateGPT combina:**
- System prompt de BalconDemo (filtrado por rol)
- `default_query_system_prompt` (formato JSON)
- Contexto de documentos recuperados
- Mensaje del usuario

### 3. Manejo de Errores

**BalconDemo:**
- Timeout: 60 segundos
- Reintentos: No (manejado por rate limiting)
- Fallback: Mensaje de error amigable

**PrivateGPT:**
- Timeout: Configurado en settings
- Reintentos: No
- Fallback: Respuesta con `has_information: false`

---

## Flujo Completo de una Consulta

### Escenario 1: Consulta Informativa Simple

```
1. Usuario: "¿Cuáles son los requisitos para cambiar de paralelo?"
   ↓
2. BalconDemo: classify_with_privategpt()
   - Stage: AWAIT_INTENT
   - No es confirmación
   ↓
3. interpretar_intencion_principal()
   - LLM Call #1: Extrae intención
   - Retorna: {
       "intent_short": "consultar requisitos cambio paralelo",
       "accion": "consultar",
       "objeto": "requisitos",
       "answer_type": "informativo",
       "needs_confirmation": false
     }
   ↓
4. classify_with_heuristics()
   - NO usa LLM
   - Determina: department="académico", channel="DIRECCIÓN DE GESTIÓN..."
   ↓
5. answer_type == "informativo" → Llamar a PrivateGPT
   ↓
6. _call_privategpt_rag()
   - Construye mensajes con rol
   - Envía a PrivateGPT API
   ↓
7. PrivateGPT: chat_completion()
   - Expande consulta (LLM Call #2): ["requisitos cambio paralelo", "requisitos para cambiar grupo", ...]
   - Busca en vector store con todas las variaciones
   - Recupera top 10 chunks
   - Filtra por rol (estudiante) → Prioriza documentos "unemi_*"
   - Construye contexto
   ↓
8. PrivateGPT: Envía a LLM (LLM Call #3)
   - System prompt: Filtrado por rol + Formato JSON
   - Contexto: Chunks recuperados
   - User message: "¿Cuáles son los requisitos para cambiar de paralelo?"
   ↓
9. LLM genera respuesta JSON:
   {
     "has_information": true,
     "response": "Para cambiar de paralelo necesitas...",
     "fuentes": [{"archivo": "Reglamento.pdf", "pagina": "15"}]
   }
   ↓
10. PrivateGPT: parse_json_response()
    - Parsea JSON
    - Extrae has_information, response, fuentes
    - Retorna a BalconDemo
    ↓
11. BalconDemo: PrivateGPTResponseParser.parse()
    - Confía en has_information de PrivateGPT
    - Agrupa fuentes por archivo
    - Formatea respuesta
    ↓
12. _build_informative_answer_response()
    - Construye respuesta estándar
    - Retorna al frontend
    ↓
13. Frontend: Muestra respuesta con fuentes
```

**Total de LLM Calls: 3**
- 1: Extracción de intención (BalconDemo)
- 2: Expansión de consulta (PrivateGPT)
- 3: Generación de respuesta RAG (PrivateGPT)

### Escenario 2: Solicitud Operativa

```
1. Usuario: "Quiero cambiar de paralelo"
   ↓
2. BalconDemo: classify_with_privategpt()
   - Stage: AWAIT_INTENT
   ↓
3. interpretar_intencion_principal()
   - LLM Call #1: Extrae intención
   - Retorna: {
       "intent_short": "solicitar cambio paralelo",
       "accion": "cambiar",
       "objeto": "paralelo",
       "answer_type": "operativo",
       "needs_confirmation": true,
       "confirm_text": "¿Quieres solicitar un cambio de paralelo?"
     }
   ↓
4. classify_with_heuristics()
   - Determina: department="académico", channel="DIRECCIÓN DE GESTIÓN..."
   ↓
5. answer_type == "operativo" → NO llamar a PrivateGPT
   ↓
6. needs_confirmation == true → Mostrar confirmación
   ↓
7. _build_need_confirm_response()
   - Retorna mensaje de confirmación
   ↓
8. Usuario: "Sí"
   ↓
9. BalconDemo: Detecta confirmación positiva
   - Recupera pending_slots
   - Llama a _handle_confirmation_stage()
   ↓
10. Buscar solicitudes relacionadas
    - find_related_requests()
    - Compara con solicitudes previas del estudiante
    ↓
11. Si hay solicitudes relacionadas:
    - Muestra opciones al usuario
    - Espera selección
    ↓
12. Usuario selecciona o dice "no hay"
    ↓
13. _build_handoff_response_new()
    - Construye mensaje de handoff
    - Pide detalles y archivo
    ↓
14. Usuario proporciona detalles y archivo
    ↓
15. crear_solicitud()
    - Crea solicitud en el sistema
    - Retorna código de solicitud
    ↓
16. Mensaje final: "Tu solicitud ha sido enviada exitosamente..."
```

**Total de LLM Calls: 1**
- 1: Extracción de intención (BalconDemo)

### Escenario 3: Consulta con Confirmación

```
1. Usuario: "nota parcial matemática"
   ↓
2. interpretar_intencion_principal()
   - LLM Call #1: Extrae intención
   - Retorna: {
       "intent_short": "consultar nota parcial matemática",
       "asignatura": "matemática",
       "unidad_o_actividad": "parcial",
       "answer_type": "informativo",
       "needs_confirmation": true,
       "confirm_text": "¿Quieres consultar la nota del parcial en Matemática?"
     }
   ↓
3. needs_confirmation == true → Mostrar confirmación
   ↓
4. Usuario: "Sí"
   ↓
5. _handle_confirmation_stage()
   - Usa intent_slots confirmados
   - answer_type == "informativo" → Llamar a PrivateGPT
   ↓
6. _call_privategpt_rag()
   - Construye mensaje confirmado: "Quiero consultar la nota del parcial en Matemática"
   - Envía a PrivateGPT
   ↓
7. PrivateGPT procesa (igual que Escenario 1)
   ↓
8. Retorna respuesta con fuentes
```

**Total de LLM Calls: 3**
- 1: Extracción de intención (BalconDemo)
- 2: Expansión de consulta (PrivateGPT)
- 3: Generación de respuesta RAG (PrivateGPT)

---

## Prompts y Llamadas LLM

### Resumen de Llamadas LLM

#### BalconDemo

1. **Extracción de Intención** (`interpretar_intencion_principal`)
   - **Cuándo:** En cada mensaje nuevo del usuario (excepto confirmaciones)
   - **Modelo:** Gemini 2.5 Flash
   - **Rate Limit:** 9 RPM (token bucket)
   - **Prompt:** `INTENT_SYSTEM` + texto del usuario
   - **Output:** JSON con slots de intención

2. **Generación de Confirmación** (`_confirm_text_from_slots`) - OPCIONAL
   - **Cuándo:** Solo si `confirm_text` está vacío pero `needs_confirmation=True`
   - **Modelo:** Gemini 2.5 Flash
   - **Rate Limit:** 9 RPM
   - **Prompt:** Sistema de confirmaciones + slots
   - **Output:** Texto de confirmación en español

#### PrivateGPT

1. **Expansión de Consulta** (`_expand_query`)
   - **Cuándo:** Si `query_expansion=True` en settings
   - **Modelo:** Gemini 2.5 Flash
   - **Rate Limit:** Sin límite específico (usa el mismo modelo)
   - **Prompt:** Instrucciones de expansión + consulta original
   - **Output:** 2-3 variaciones de la consulta

2. **Generación de Respuesta RAG** (`ContextChatEngine`)
   - **Cuándo:** Siempre que `use_context=True`
   - **Modelo:** Gemini 2.5 Flash
   - **Rate Limit:** Sin límite específico
   - **Prompt:** 
     - System: `default_query_system_prompt` + system prompt de BalconDemo
     - Context: Chunks recuperados del vector store
     - User: Mensaje del usuario
   - **Output:** JSON con `has_information`, `response`, `fuentes`

### Prompts Completos

#### 1. INTENT_SYSTEM (BalconDemo)

Ver sección 3.1 de BalconDemo.

#### 2. default_query_system_prompt (PrivateGPT)

Ver sección 4 de PrivateGPT.

#### 3. System Prompt de Rol (BalconDemo → PrivateGPT)

```python
system_content = f"""
IMPORTANTE: El usuario es un {rol}.
Si recibes contexto de documentos, SOLO usa documentos relevantes para {rol}.
IGNORA documentos que sean para otros roles (profesor, administrativo, etc.).
"""
```

---

## Archivos y Estructura

### Archivos de Configuración

#### BalconDemo

1. **`app/data/handoff_config.json`**
   - Mapeo de categorías/subcategorías a departamentos
   - Mapeo por keywords de intención
   - Lista de departamentos reales

2. **`app/data/data_unemi.json`**
   - Datos completos de estudiantes
   - Estructura: `{cedula: {persona, perfiles, solicitudes_balcon, contexto}}`

3. **`app/services/config.py`**
   - Configuración de LLM
   - Rate limiting (9 RPM)
   - Umbrales de confianza

#### PrivateGPT

1. **`settings-docker.yaml`**
   - Configuración de LLM (Gemini)
   - Configuración de embeddings
   - Configuración de RAG (similarity_top_k, query_expansion, rerank)
   - Prompts del sistema

### Archivos de Datos

#### Vector Store (Qdrant)

- **Ubicación:** `local_data/private_gpt/qdrant/`
- **Contenido:** Vectores de embeddings de documentos
- **Metadata:** file_name, page_label, doc_id, etc.

#### DocStore (LlamaIndex)

- **Ubicación:** `local_data/private_gpt/docstore/`
- **Contenido:** Documentos completos con metadata
- **Formato:** LlamaIndex DocStore

### Archivos Temporales

- **Filtrado:** Archivos que empiezan con "tmp" se filtran automáticamente
- **Limpieza:** Se ejecuta al inicio del servicio y después de cada ingestión

---

## Conclusión

Este documento describe completamente cómo funcionan BalconDemo y PrivateGPT, incluyendo:

1. **Arquitectura completa** de ambos sistemas
2. **Flujos detallados** de procesamiento
3. **Prompts exactos** utilizados
4. **Llamadas LLM** y cuándo se ejecutan
5. **Comunicación** entre sistemas
6. **Archivos y estructura** de datos

**Puntos Clave:**

- **BalconDemo** orquesta el flujo de conversación y extrae intenciones
- **PrivateGPT** maneja RAG y generación de respuestas con contexto
- **Total de LLM calls:** 1-3 por consulta (dependiendo del tipo)
- **Rate limiting:** 9 RPM en BalconDemo para evitar límites de API
- **Filtrado por rol:** Los estudiantes solo ven documentos relevantes para estudiantes
- **Handoff:** Las solicitudes operativas se derivan a humanos sin usar RAG


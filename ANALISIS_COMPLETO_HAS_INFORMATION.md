# Análisis Completo: Detección de `has_information` en PrivateGPT

## 🔍 Flujo Completo de Detección

### 1. **Generación del Prompt del Sistema** (`chat_service.py`)

**Ubicación**: `private_gpt/server/chat/chat_service.py` - Método `_chat_engine()`

```python
def _chat_engine(self, system_prompt: str | None = None, use_context: bool = False, ...):
    # Si se proporciona un system_prompt personalizado Y use_context=True,
    # combinarlo con default_query_system_prompt
    if use_context and system_prompt:
        default_query_prompt = settings.ui.default_query_system_prompt
        if default_query_prompt:
            combined_prompt = f"""{default_query_prompt}

INSTRUCCIONES ADICIONALES DEL SISTEMA:
{system_prompt}
"""
            system_prompt = combined_prompt
```

**Qué hace**:
- Combina el `default_query_system_prompt` de `settings-docker.yaml` con el `system_prompt` personalizado
- El `default_query_system_prompt` contiene las instrucciones de formato JSON
- El `system_prompt` personalizado contiene el filtrado por rol

**Prompt final que recibe el LLM**:
```
Eres un asistente RAG. Debes responder exclusivamente con un JSON válido...

Formato de salida obligatorio:
- Un objeto JSON con las claves:
  - has_information: booleano (true o false)
  - response: string en español, claro y natural
  - fuentes: lista de objetos

FILTRADO CRITICO DE DOCUMENTOS:
[Instrucciones de filtrado por rol del system_prompt personalizado]
```

---

### 2. **Recuperación de Documentos (RAG)** (`chat_service.py`)

**Ubicación**: `private_gpt/server/chat/chat_service.py` - Método `_chat_engine()`

**Proceso**:
1. **Query Expansion** (si está habilitado):
   - Expande la consulta usando el LLM para generar variaciones
   - Busca con todas las variaciones
   - Combina resultados únicos

2. **Vector Search**:
   - Busca en el vector store usando embeddings
   - Retorna top K documentos más similares (`similarity_top_k`)

3. **Post-processors**:
   - `MetadataReplacementPostProcessor`: Reemplaza metadatos con ventana de contexto
   - `RoleBasedPostprocessor` (si es estudiante): Prioriza documentos "unemi_"
   - `SimilarityPostprocessor` (si está habilitado): Filtra por score mínimo
   - `SentenceTransformerRerank` (si está habilitado): Reordena por relevancia

**Resultado**: Lista de nodos con contexto relevante para la pregunta

---

### 3. **Generación de Respuesta por el LLM** (`chat_service.py`)

**Ubicación**: `private_gpt/server/chat/chat_service.py` - Método `chat()`

```python
def chat(self, messages: list[ChatMessage], use_context: bool = False, ...):
    chat_engine = self._chat_engine(...)
    wrapped_response = chat_engine.chat(message=last_message, chat_history=chat_history)
    sources = [Chunk.from_node(node) for node in wrapped_response.source_nodes]
    completion = Completion(response=wrapped_response.response, sources=sources)
    return completion
```

**Qué hace LlamaIndex `ContextChatEngine`**:
1. Toma el `system_prompt` combinado
2. Inyecta los documentos recuperados como contexto
3. Envía todo al LLM con el formato del prompt style (llama2, llama3, etc.)
4. El LLM genera la respuesta basándose en:
   - El `system_prompt` (instrucciones de formato JSON)
   - Los documentos recuperados (contexto)
   - La pregunta del usuario

**El LLM decide `has_information` basándose en**:
- ✅ Si encontró información relevante en los documentos recuperados
- ✅ Si el contexto recuperado responde la pregunta del usuario
- ✅ Si el contexto contiene SOLO información para otros roles (según filtrado) → `false`
- ✅ Si no hay documentos recuperados o son irrelevantes → `false`

**Ejemplo de respuesta del LLM**:
```json
{
  "has_information": false,
  "response": "La información proporcionada describe el sistema interno de evaluación estudiantil..."
}
```

**O si no sigue el formato JSON**:
```
has_information=false
La información proporcionada describe...
```

---

### 4. **Parsing de la Respuesta** (`chat_router.py`)

**Ubicación**: `private_gpt/server/chat/chat_router.py` - Función `parse_json_response()`

```python
def parse_json_response(response_text: str) -> dict[str, any]:
    try:
        # 1. Buscar inicio del JSON (primer {)
        start_idx = response_text.find('{')
        
        # 2. Buscar final balanceando llaves
        # ... (lógica de balanceo)
        
        # 3. Parsear JSON
        json_str = response_text[start_idx:end_idx]
        parsed = json.loads(json_str)
        
        # 4. Extraer has_information (default: False si no existe)
        has_information = parsed.get("has_information", False)
        
        # 5. Extraer response
        response = parsed.get("response")
        
        return {
            "has_information": has_information,
            "response": response or "",
            "fuentes": parsed.get("fuentes", [])
        }
    except (json.JSONDecodeError, ValueError, AttributeError):
        # FALLBACK: Si no puede parsear JSON
        no_info_phrases = [
            "no se encuentra", "no hay información",
            "no contiene información", "no está disponible"
        ]
        response_lower = response_text.lower()
        has_no_info_phrase = any(phrase in response_lower for phrase in no_info_phrases)
        
        return {
            "has_information": not has_no_info_phrase,  # Si contiene frases negativas → False
            "response": response_text
        }
```

**Casos manejados**:
1. ✅ **JSON válido con `has_information`**: Se extrae directamente
2. ✅ **JSON válido sin `has_information`**: Se asume `False`
3. ⚠️ **No es JSON válido**: Se usa fallback con 4 frases negativas básicas

**Problema identificado**: El fallback solo detecta 4 frases negativas, pero hay muchas más variantes.

---

### 5. **Procesamiento Final** (`chat_router.py`)

**Ubicación**: `private_gpt/server/chat/chat_router.py` - Endpoint `chat_completion()`

```python
def chat_completion(request: Request, body: ChatBody):
    completion = service.chat(...)
    
    # Procesar la respuesta JSON
    response_text = completion.response if completion.response else ""
    parsed_response = parse_json_response(response_text)
    clean_response = parsed_response.get("response", response_text)
    
    # Procesar fuentes desde completion.sources
    if completion.sources and body.include_sources:
        # Ordenar por score y tomar top 5
        sorted_sources = sorted(completion.sources, key=lambda s: s.score, reverse=True)
        top_sources = sorted_sources[:5]
        
        # Extraer metadata correcto
        sources_list = []
        for source in top_sources:
            file_name = source.document.doc_metadata.get("file_name", "Unknown")
            page_label = source.document.doc_metadata.get("page_label", "Unknown")
            sources_list.append({"archivo": file_name, "pagina": str(page_label)})
        
        # Reemplazar fuentes del JSON con las correctas del metadata
        parsed_response["fuentes"] = sources_list
        
        # Si el modelo generó JSON, reconstruirlo con las fuentes correctas
        if parsed_response.get("has_information", False):
            response_with_sources = json.dumps({
                "has_information": parsed_response.get("has_information", True),
                "response": clean_response,
                "fuentes": sources_list
            }, ensure_ascii=False)
            clean_response = response_with_sources
    
    return to_openai_response(clean_response, completion.sources)
```

**Qué hace**:
- Parsea la respuesta JSON del LLM
- Extrae `has_information` y `response`
- Reemplaza las fuentes del JSON con las correctas del metadata
- Reconstruye el JSON con las fuentes correctas si `has_information=True`

---

### 6. **Validación en BalconDemo** (`privategpt_response_parser.py`)

**Ubicación**: `app/services/privategpt_response_parser.py`

**Proceso**:
1. Recibe la respuesta de PrivateGPT (ya parseada o raw)
2. Intenta extraer `has_information` del JSON
3. Valida con heurísticas (31 patrones de disculpa)
4. Verifica longitud mínima y presencia de fuentes

**Heurísticas aplicadas**:
- 31 patrones de disculpa detectados
- Longitud mínima: 50 con fuentes, 100 sin fuentes
- Presencia de fuentes válidas

---

## 🐛 Problemas Identificados

### Problema 1: LLM retorna texto plano en lugar de JSON

**Síntoma**: 
```
has_information=false
La información proporcionada describe...
```

**Causa**: El LLM no está siguiendo el formato JSON del `default_query_system_prompt`

**Posibles causas**:
1. El `system_prompt` personalizado está sobrescribiendo las instrucciones de formato JSON
2. El LLM (Gemini) no está respetando las instrucciones de formato JSON
3. El prompt combinado no es lo suficientemente claro

**Solución**: Verificar que el prompt combinado incluya claramente las instrucciones de formato JSON

---

### Problema 2: `has_information=false` cuando debería ser `true`

**Síntoma**: El LLM retorna `has_information=false` pero hay información relevante en los documentos

**Posibles causas**:
1. **Filtrado por rol demasiado estricto**: El filtrado está eliminando documentos relevantes
2. **Query expansion no encuentra variaciones**: La consulta no coincide con los documentos
3. **Similarity threshold muy alto**: Los documentos relevantes tienen score bajo
4. **El LLM interpreta mal el contexto**: No entiende que los documentos son relevantes

**Solución**: Revisar:
- Los documentos recuperados (`completion.sources`)
- Los scores de similitud
- El contexto que recibe el LLM

---

### Problema 3: `has_information=true` cuando debería ser `false`

**Síntoma**: El LLM retorna `has_information=true` pero la respuesta es una disculpa

**Causa**: El LLM no está detectando correctamente cuando no hay información

**Solución**: Las heurísticas en BalconDemo deberían detectar esto, pero pueden fallar si:
- El patrón de disculpa no está en la lista
- La respuesta es muy larga pero sigue siendo una disculpa

---

## 🔧 Soluciones Propuestas

### Solución 1: Mejorar el Fallback en `parse_json_response`

**Archivo**: `private_gpt/server/chat/chat_router.py`

**Cambio**: Expandir la lista de frases negativas para detectar más casos:

```python
no_info_phrases = [
    "no se encuentra", "no hay información",
    "no contiene información", "no está disponible",
    "no tengo información",  # ← Agregar
    "no encuentro información",  # ← Agregar
    "no puedo ayudarte",  # ← Agregar
    "no puedo proporcionar",  # ← Agregar
    "te sugiero que te pongas en contacto",  # ← Agregar
    "contacta directamente",  # ← Agregar
    # ... más patrones
]
```

---

### Solución 2: Forzar Formato JSON en el Prompt

**Archivo**: `private_gpt/server/chat/chat_service.py`

**Cambio**: Hacer más explícito el formato JSON en el prompt combinado:

```python
combined_prompt = f"""{default_query_prompt}

INSTRUCCIONES ADICIONALES DEL SISTEMA:
{system_prompt}

RECUERDA: Debes responder SOLO con un JSON válido. No incluyas texto antes o después del JSON.
El formato debe ser exactamente:
{{"has_information": true/false, "response": "...", "fuentes": [...]}}
"""
```

---

### Solución 3: Validar `has_information` basándose en Sources

**Archivo**: `private_gpt/server/chat/chat_router.py`

**Cambio**: Si `has_information=true` pero no hay sources, validar con heurísticas:

```python
parsed_response = parse_json_response(response_text)
has_information = parsed_response.get("has_information", False)

# Validar: si dice true pero no hay sources, puede ser falso positivo
if has_information and (not completion.sources or len(completion.sources) == 0):
    # Validar con heurísticas
    response_lower = clean_response.lower()
    no_info_phrases = [...]
    has_no_info_phrase = any(phrase in response_lower for phrase in no_info_phrases)
    if has_no_info_phrase:
        has_information = False
        parsed_response["has_information"] = False
```

---

## 📊 Flujo de Datos Completo

```
1. Usuario envía mensaje
   ↓
2. BalconDemo construye system_prompt con filtrado por rol
   ↓
3. PrivateGPT combina con default_query_system_prompt
   ↓
4. LlamaIndex ContextChatEngine:
   - Expande query (si está habilitado)
   - Busca en vector store
   - Aplica post-processors
   - Inyecta contexto en el prompt
   ↓
5. LLM genera respuesta:
   - Decide has_information basándose en contexto
   - Genera JSON con has_information, response, fuentes
   ↓
6. PrivateGPT parsea respuesta:
   - parse_json_response() extrae has_information
   - Si falla, usa fallback con frases negativas
   ↓
7. PrivateGPT procesa fuentes:
   - Extrae metadata correcto
   - Reconstruye JSON con fuentes correctas
   ↓
8. BalconDemo recibe respuesta:
   - PrivateGPTResponseParser.parse()
   - Valida has_information con heurísticas
   - Detecta disculpas, verifica longitud, fuentes
   ↓
9. Resultado final
```

---

## 🎯 Puntos Críticos

1. **El LLM es la fuente primaria** de `has_information`, pero puede fallar
2. **El fallback en PrivateGPT es básico** (solo 4 frases negativas)
3. **Las heurísticas en BalconDemo son más robustas** (31 patrones)
4. **Las fuentes son un indicador fuerte**: Si hay sources válidas, probablemente hay información
5. **El filtrado por rol puede eliminar documentos relevantes** si es demasiado estricto

---

## 🔍 Debugging

Para debuggear problemas de `has_information`:

1. **Verificar documentos recuperados**:
   ```python
   print(f"Sources recuperados: {len(completion.sources)}")
   for source in completion.sources:
       print(f"  - {source.document.doc_metadata.get('file_name')} (score: {source.score})")
   ```

2. **Verificar respuesta raw del LLM**:
   ```python
   print(f"Respuesta raw: {completion.response}")
   ```

3. **Verificar parsing**:
   ```python
   parsed = parse_json_response(completion.response)
   print(f"has_information parseado: {parsed.get('has_information')}")
   ```

4. **Verificar prompt combinado**:
   ```python
   # En chat_service.py, agregar logging
   logger.debug(f"Prompt combinado: {combined_prompt[:500]}...")
   ```


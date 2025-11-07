# 🤖 MAPA DETALLADO DE TODAS LAS LLAMADAS AL LLM

## 📊 RESUMEN EJECUTIVO

| Métrica | Valor |
|---------|-------|
| **Total módulos que usan LLM** | 7 |
| **Total funciones que llaman LLM** | 11 |
| **Llamadas por consulta (min)** | 3 |
| **Llamadas por consulta (max)** | 10 |
| **Llamadas por consulta (promedio)** | 5-6 |
| **Tiempo por llamada LLM** | 1-2 segundos |
| **Modelo usado** | Gemini 2.5 Flash |
| **Temperatura** | 0 (determinista) |
| **Max retries** | 2 |

---

## 🗺️ MAPA COMPLETO POR MÓDULO

### 1️⃣ `intent_parser.py` - 2 llamadas LLM

#### LLM Call #1: `interpretar_intencion_principal()`

```python
def interpretar_intencion_principal(texto_usuario: str) -> dict:
    prompt = f"{INTENT_SYSTEM_V2}\n\nTEXTO:\n{texto_usuario}\n"
    out = llm.invoke(prompt)  # ← LLM CALL #1
```

**Propósito**: Extraer slots de intención estructurada en JSON
**Input**: Texto del usuario
**Output**: JSON con intent_short, acción, objeto, asignatura, etc.
**Ejemplo**:
```json
{
  "intent_short": "Solicitar cambio de paralelo para una asignatura",
  "accion": "cambiar",
  "objeto": "paralelo",
  "asignatura": "Matemática",
  "detalle_libre": "por razones laborales"
}
```

**Cuándo se ejecuta**:
- Stage "ready" (primera interacción)
- Después de enriquecer query con contexto (si aplica)

---

#### LLM Call #2: `_confirm_text_from_slots()`

```python
def _confirm_text_from_slots(sl: dict) -> str:
    msgs = ChatPromptTemplate.from_messages([
        ("system", sys + "\n\n" + fewshot),
        ("human", user),
    ]).format_messages()
    
    out = llm.invoke(msgs)  # ← LLM CALL #2
```

**Propósito**: Generar pregunta de confirmación natural
**Input**: Slots de intención (JSON)
**Output**: Pregunta en español natural
**Ejemplo**:
- Input: `{"accion": "cambiar", "objeto": "paralelo"}`
- Output: "¿Quieres cambiar de paralelo?"

**Cuándo se ejecuta**:
- Stage "ready" después de interpretar intención
- Para confirmar con el usuario antes de buscar

---

### 2️⃣ `conversation_context.py` - 2 llamadas LLM

#### LLM Call #3: `needs_context()` (JSON Evaluation)

```python
def needs_context(user_text: str, conversation_history: List[Dict]) -> Dict:
    prompt = f"""Analiza si esta pregunta necesita contexto de la conversación previa...
    
    Responde ESTRICTAMENTE en formato JSON:
    {{
      "needs_context": true/false,
      "confidence": "high/medium/low",
      "reason": "explicación breve"
    }}
    """
    
    response = llm.invoke(prompt)  # ← LLM CALL #3
```

**Propósito**: Detectar si la pregunta necesita contexto conversacional
**Input**: Pregunta actual + historial (últimos 2 turnos)
**Output**: JSON con evaluación
**Ejemplo**:
```json
{
  "needs_context": true,
  "confidence": "high",
  "reason": "Usa pronombre 'eso' que se refiere a respuesta anterior"
}
```

**Cuándo se ejecuta**:
- Stage "await_confirm" antes de buscar
- Solo si hay historial (≥2 mensajes)

---

#### LLM Call #4: `enrich_query_with_context()`

```python
def enrich_query_with_context(user_text: str, conversation_history: List[Dict]) -> str:
    prompt = f"""Reformula la pregunta para que sea COMPLETA y AUTO-CONTENIDA...
    
    CONVERSACIÓN PREVIA:
    {context_summary}
    
    PREGUNTA ACTUAL:
    "{user_text}"
    
    PREGUNTA REFORMULADA:"""
    
    enriched_query = llm.invoke(prompt)  # ← LLM CALL #4
```

**Propósito**: Enriquecer query con contexto para hacerla auto-contenida
**Input**: Pregunta actual + resumen de conversación
**Output**: Pregunta reformulada
**Ejemplo**:
- Input: "¿Y si falto más de eso?"
- Context: "La asistencia mínima es 60%"
- Output: "¿Qué pasa si falto más del 60% de asistencia?"

**Cuándo se ejecuta**:
- Solo si `needs_context = true`
- Antes de re-interpretar la intención

---

### 3️⃣ `answerability.py` - 2 llamadas LLM

#### LLM Call #5: `answerability_score()` - Veredicto del Juez

```python
def answerability_score(intent_query: str, retr, k: int = 8) -> dict:
    judge_sys = (
        "Eres un juez que evalúa si el contexto permite responder una consulta...\n"
        "Devuelve SOLO 'yes' o 'no'."
    )
    
    msgs = ChatPromptTemplate.from_messages([
        ("system", judge_sys),
        ("human", "Consulta:\n{q}\n\nContexto (extractos):\n{c}\n\n¿Se puede responder algo útil? (yes/no)")
    ]).format_messages(q=intent_query, c=sample[:6000])
    
    out = llm.invoke(msgs)  # ← LLM CALL #5
```

**Propósito**: Juez LLM que evalúa si el contexto recuperado puede responder
**Input**: Query + extractos de documentos recuperados (top 5)
**Output**: "yes" o "no"
**Ejemplo**:
- Query: "¿Cuál es la asistencia mínima?"
- Context: "...se establece que el estudiante tiene permitido ausentarse en un máximo del 40%..."
- Output: "yes"

**Cuándo se ejecuta**:
- Por cada `planned_query` (hasta 3 veces)
- Es parte del cálculo de confidence score

---

#### LLM Call #6: `gen_query_variants_llm()`

```python
def gen_query_variants_llm(original_query: str, n: int = 4) -> list[str]:
    sys = (
        "Eres un experto en reformular consultas académicas desde diferentes ángulos.\n"
        f"TAREA: Genera EXACTAMENTE {n} reformulaciones DIFERENTES..."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys),
        ("human", f"{original_query}")
    ])
    
    out = llm.invoke(messages)  # ← LLM CALL #6
```

**Propósito**: Generar variantes de la query para mejorar recall
**Input**: Query original
**Output**: Lista de 4 reformulaciones
**Ejemplo**:
- Input: "Solicitar cambio de paralelo"
- Output:
  1. "¿Cuál es el procedimiento para cambiar de paralelo?"
  2. "¿Cómo gestionar el cambio de horario a otro grupo?"
  3. "Requisitos para trasladarse a otra sección"
  4. "¿Quién autoriza el cambio de paralelo?"

**Cuándo se ejecuta**:
- Solo si `confidence < 0.65` en answerability inicial
- Una vez por consulta (no por cada variante)

---

### 4️⃣ `pdf_responder.py` - 1 llamada LLM

#### LLM Call #7/#8: `responder_desde_pdfs()` - Generación de Respuesta

```python
def responder_desde_pdfs(intent_text: str, incluir_fuente: bool = False, docs_override: list = None) -> dict:
    template = """
    Eres un asistente académico experto...
    
    Responde ESTRICTAMENTE en formato JSON con esta estructura:
    {{
      "has_information": true/false,
      "confidence": "high/medium/low",
      "answer": "tu respuesta aquí"
    }}
    """
    
    prompt = ChatPromptTemplate.from_template(template)
    rag_chain = (
        {"context": lambda x: format_docs(docs), "question": RunnablePassthrough()}
        | prompt
        | llm  # ← LLM CALL #7 o #8
        | StrOutputParser()
    )
    
    respuesta_raw = rag_chain.invoke(intent_text)
    respuesta_json = json.loads(respuesta_raw)
```

**Propósito**: Generar respuesta final usando RAG + auto-evaluación
**Input**: Query + documentos recuperados (contexto)
**Output**: JSON con respuesta y auto-evaluación
**Ejemplo**:
```json
{
  "has_information": true,
  "confidence": "high",
  "answer": "La asistencia mínima es del 60%. No se aceptan justificaciones de faltas."
}
```

**Cuándo se ejecuta**:
- **LLM #7**: Nivel 1 (confidence ≥ 0.70)
- **LLM #8**: Nivel 3 (0.42 ≤ confidence < 0.70)

**Auto-evaluación incorporada**:
- `has_information`: El LLM decide si tiene info útil
- `confidence`: El LLM evalúa su propia confianza
- ✅ **Zero keywords** - todo evaluación semántica

---

### 5️⃣ `handoff.py` - 1 llamada LLM

#### LLM Call #9: `classify_with_llm()` (Departamento/Canal)

```python
def classify_with_llm(
    user_text: str,
    intent_short: str,
    category: Optional[str],
    subcategory: Optional[str],
    slots: Dict[str, Any]
) -> Dict[str, Any]:
    
    prompt = f"""Analiza esta solicitud de un estudiante universitario y clasifícala:
    
    SOLICITUD DEL USUARIO: "{user_text}"
    INTENCIÓN DETECTADA: "{intent_short}"
    CATEGORÍA: "{category}"
    
    Clasifica la solicitud en JSON:
    {{
      "answer_type": "informativo | procedimental | operativo",
      "department": "académico | financiero | bienestar | administrativo | tic | biblioteca | general",
      "channel": "nombre del departamento específico",
      "reasoning": "explicación breve"
    }}
    
    CRITERIOS:
    - académico → "Mesa de Ayuda Académica"
    - financiero → "Departamento Financiero"
    - tic → "Soporte TIC"
    ...
    
    Responde SOLO con el JSON:"""
    
    response = llm.invoke(prompt)  # ← LLM CALL #9
```

**Propósito**: Clasificar solicitud para determinar canal de derivación correcto
**Input**: Texto original + intención + categoría + slots
**Output**: JSON con departamento y canal
**Ejemplo**:
```json
{
  "answer_type": "operativo",
  "department": "académico",
  "channel": "Mesa de Ayuda Académica",
  "reasoning": "Solicitud de cambio académico requiere validación administrativa"
}
```

**Cuándo se ejecuta**:
- Nivel 4 (sin información o intención crítica)
- Antes de crear el ticket automático

---

### 6️⃣ `taxonomy.py` - 1 llamada LLM

#### LLM Call #10: `map_to_taxonomy()`

```python
def map_to_taxonomy(user_text: str) -> dict:
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
    
    out = llm.invoke(prompt)  # ← LLM CALL #10
```

**Propósito**: Mapear intención a taxonomía de categorías
**Input**: Texto del usuario + lista de opciones de taxonomía
**Output**: JSON con ruta seleccionada
**Ejemplo**:
- Input: "Cambio de paralelo"
- Opciones: ["Académico › Matriculación", "Académico › Cambios", ...]
- Output: `{"ruta": "Académico › Cambios"}`

**Cuándo se ejecuta**:
- Nivel 4 (derivación al agente)
- Para categorizar el ticket correctamente

---

### 7️⃣ `retriever.py` - ⚠️ NO usa LLM directamente

**IMPORTANTE**: El retriever usa **embeddings pre-calculados**, NO llama al LLM en tiempo real.

```python
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# ← Usa modelo local de embeddings, NO Gemini LLM
```

**Componentes del Retriever**:
1. **Dense (FAISS)**: Búsqueda por embeddings (0 LLM calls)
2. **Sparse (BM25)**: Búsqueda por keywords (0 LLM calls)
3. **Ensemble**: Combina ambos (0 LLM calls)
4. **Cross-Encoder**: Desactivado (muy lento)

**MultiQueryRetriever** (EXCEPCIÓN):
```python
if MultiQueryRetriever is not None:
    mq_dense = MultiQueryRetriever.from_llm(
        retriever=dense,
        llm=llm,  # ← USA LLM para generar query variants
        prompt=ChatPromptTemplate.from_template(
            "Genera 2 reformulaciones específicas para buscar en el reglamento:\n{question}"
        )
    )
```

**Nota**: Este componente genera variantes pero **está dentro del retriever**, no se cuenta por separado porque las variantes ya están contadas en `gen_query_variants_llm()`.

---

## 📈 TABLA DE LLAMADAS POR ESCENARIO

### Escenario 1: Consulta Simple con Info Clara (Best Case)

| # | Función | Módulo | Etapa |
|---|---------|--------|-------|
| 1 | interpretar_intencion_principal() | intent_parser | Stage ready |
| 2 | _confirm_text_from_slots() | intent_parser | Stage ready |
| 3 | answerability_score() (1x) | answerability | Retrieval |
| 4 | responder_desde_pdfs() | pdf_responder | Nivel 1 |

**TOTAL: 4 llamadas LLM**
**Tiempo estimado: 4-6 segundos**

---

### Escenario 2: Consulta con Contexto Conversacional

| # | Función | Módulo | Etapa |
|---|---------|--------|-------|
| 1 | interpretar_intencion_principal() | intent_parser | Stage ready |
| 2 | _confirm_text_from_slots() | intent_parser | Stage ready |
| 3 | needs_context() | conversation_context | Pre-retrieval |
| 4 | enrich_query_with_context() | conversation_context | Pre-retrieval |
| 5 | interpretar_intencion_principal() | intent_parser | Re-interpretación |
| 6 | answerability_score() (1x) | answerability | Retrieval |
| 7 | responder_desde_pdfs() | pdf_responder | Nivel 1 |

**TOTAL: 7 llamadas LLM**
**Tiempo estimado: 10-14 segundos**

---

### Escenario 3: Consulta Compleja con Query Expansion

| # | Función | Módulo | Etapa |
|---|---------|--------|-------|
| 1 | interpretar_intencion_principal() | intent_parser | Stage ready |
| 2 | _confirm_text_from_slots() | intent_parser | Stage ready |
| 3 | answerability_score() (3x) | answerability | Multi-stage retrieval |
| 4 | gen_query_variants_llm() | answerability | Query expansion |
| 5 | responder_desde_pdfs() | pdf_responder | Nivel 3 |

**TOTAL: 6 llamadas LLM** (1+1+3+1=6)
**Tiempo estimado: 8-12 segundos**

---

### Escenario 4: Sin Información - Handoff Automático (Worst Case)

| # | Función | Módulo | Etapa |
|---|---------|--------|-------|
| 1 | interpretar_intencion_principal() | intent_parser | Stage ready |
| 2 | _confirm_text_from_slots() | intent_parser | Stage ready |
| 3 | needs_context() | conversation_context | Pre-retrieval |
| 4 | enrich_query_with_context() | conversation_context | Pre-retrieval |
| 5 | interpretar_intencion_principal() | intent_parser | Re-interpretación |
| 6 | answerability_score() (3x) | answerability | Multi-stage (3 queries) |
| 7 | gen_query_variants_llm() | answerability | Query expansion |
| 8 | responder_desde_pdfs() | pdf_responder | Nivel 3 (rechazado) |
| 9 | classify_with_llm() | handoff | Clasificación canal |
| 10 | map_to_taxonomy() | taxonomy | Clasificación categoría |

**TOTAL: 10 llamadas LLM** (peor caso)
**Tiempo estimado: 15-20 segundos**

---

## 🎯 OPTIMIZACIONES IMPLEMENTADAS

### 1. Caché de Embeddings
```python
# Los embeddings de los PDFs se calculan UNA VEZ y se guardan
vectorstore.save_local(str(ruta_indice))  # Guarda embeddings en disco
# Cargas posteriores: instantáneas
vectorstore = FAISS.load_local(str(ruta_indice), embeddings)
```

**Ahorro**: ~5-10 segundos por consulta (sin re-calcular embeddings)

### 2. Límite de Query Variants
```python
variants = gen_query_variants_llm(query, n=4)  # ← Solo 4 variantes, no más
```

**Ahorro**: 1 LLM call genera 4 variantes (vs 4 LLM calls)

### 3. Límite de Planned Queries
```python
for i, pq in enumerate(planned_queries[:3], 1):  # ← Máximo 3, no 5
```

**Ahorro**: 2 menos llamadas de answerability

### 4. Cross-Encoder Desactivado
```python
FEATURE_FLAGS = {
    "cross_encoder_rerank": False,  # ← OFF (agrega 3-5 segundos)
}
```

**Ahorro**: 3-5 segundos por consulta

### 5. Auto-Evaluación en Respuesta
```python
# Antes: 2 LLM calls (respuesta + evaluación separada)
# Ahora: 1 LLM call (respuesta con JSON que incluye evaluación)
{
  "has_information": true,  # ← Evaluación incorporada
  "answer": "..."
}
```

**Ahorro**: 1 LLM call menos por respuesta

---

## 💰 COSTOS Y QUOTAS

### Gemini 2.5 Flash (Free Tier)

| Métrica | Valor |
|---------|-------|
| **Requests por minuto** | 10 RPM |
| **Tokens por minuto** | 1,000,000 TPM |
| **Requests por día** | 1,500 RPD |

### Cálculo de Throughput

**Por consulta**:
- Best case: 4 LLM calls
- Worst case: 10 LLM calls
- Promedio: 6 LLM calls

**Throughput teórico**:
- Con 10 RPM limit → ~1-2 consultas por minuto
- Con 6 calls promedio → 10/6 = 1.66 consultas/minuto
- Por hora: ~100 consultas/hora
- Por día: ~2,400 consultas/día (pero limit es 1,500 RPD)

**Límite real**: ~250 consultas/día (con 6 calls/consulta)

---

## 🚀 MEJORAS FUTURAS

### 1. Parallel LLM Calls (donde sea posible)

```python
# Actual: Sequential
result1 = llm.invoke(prompt1)  # 1.5s
result2 = llm.invoke(prompt2)  # 1.5s
# Total: 3 segundos

# Mejorado: Async parallel
results = await asyncio.gather(
    llm.ainvoke(prompt1),  # 1.5s
    llm.ainvoke(prompt2),  # 1.5s
)
# Total: 1.5 segundos (paralelo)
```

**Ahorro potencial**: ~40-50% del tiempo total

### 2. Caché de Respuestas Frecuentes

```python
# Redis cache para preguntas comunes
cache_key = hash(query)
if cached := redis.get(cache_key):
    return cached  # ← 0 LLM calls
```

**Ahorro**: 100% para queries repetidas (e.g., "¿Cuál es la asistencia mínima?")

### 3. Reduce Confirmation Step (Opcional)

```python
# Si la confianza en la interpretación es muy alta (>0.95)
# Skip confirmación y proceder directo
if interpretation_confidence > 0.95:
    # Ahorrar 2 LLM calls (confirmar + re-interpretar)
```

**Ahorro**: 2 LLM calls en ~30% de casos

### 4. Batch Processing

```python
# Procesar múltiples consultas en un solo batch
batch_results = llm.batch([prompt1, prompt2, prompt3])
```

**Ahorro**: Reduce overhead de network/auth

---



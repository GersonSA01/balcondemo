# 📊 ANÁLISIS EXHAUSTIVO DEL PROYECTO CHATBOT RAG UNEMI

## 🏗️ ARQUITECTURA GENERAL

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (Svelte)                     │
│  - ChatbotInline.svelte (UI principal)                       │
│  - Gestión de estado, historial, formularios                 │
│  - WebSocket/Fetch API → Backend Django                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼ HTTP POST /api/chat/
┌─────────────────────────────────────────────────────────────┐
│                     BACKEND (Django + Python)                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  views.py → chat_api()                              │    │
│  │  ├─ Recibe: message, history, category, student_data│    │
│  │  └─ Llama: classify_with_rag()                      │    │
│  └─────────────┬───────────────────────────────────────┘    │
│                │                                              │
│                ▼                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  rag_chat_service.py (ORQUESTADOR PRINCIPAL)       │    │
│  │  ├─ Maneja 4 stages: ready → await_confirm → RAG   │    │
│  │  ├─ 4 Niveles de confianza para responder          │    │
│  │  └─ Handoff automático si no hay info              │    │
│  └─────────────┬───────────────────────────────────────┘    │
│                │                                              │
│                ├──→ intent_parser.py (Interpreta intención)  │
│                ├──→ conversation_context.py (Contexto)       │
│                ├──→ hierarchical_router.py (Router)          │
│                ├──→ pdf_responder.py (Genera respuesta)      │
│                ├──→ answerability.py (Score confianza)       │
│                ├──→ handoff.py (Decisión de derivación)      │
│                └──→ taxonomy.py (Clasificación)              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 ESTRUCTURA DE ARCHIVOS

### Backend (Django)

```
app/
├── services/                    # Lógica de negocio (8 módulos)
│   ├── config.py               # Cliente LLM, umbrales, feature flags
│   ├── rag_chat_service.py     # ORQUESTADOR PRINCIPAL (691 líneas)
│   ├── intent_parser.py        # Parser de intenciones con LLM
│   ├── conversation_context.py # Contexto conversacional (234 líneas)
│   ├── pdf_responder.py        # Generación de respuestas RAG (208 líneas)
│   ├── answerability.py        # Juez de respondibilidad (155 líneas)
│   ├── handoff.py              # Lógica de derivación (403 líneas)
│   ├── taxonomy.py             # Mapeo a categorías (78 líneas)
│   ├── retriever.py            # Retriever híbrido (319 líneas)
│   ├── query_planner.py        # Query understanding (274 líneas)
│   ├── hierarchical_router.py  # Router jerárquico (197 líneas)
│   └── title_lexicon.py        # Índice de títulos (243 líneas)
│
├── views.py                    # Endpoints API (343 líneas)
├── urls.py                     # Routing de URLs
└── data/                       # Base de conocimiento
    ├── unemi_interno/          # PDFs internos UNEMI
    │   ├── estudiantes/        # Reglamentos estudiantes
    │   └── tic/                # Gestión SGA, políticas TIC
    ├── legal_nacional/         # Leyes y códigos
    └── epunemi/                # Certificados EPUNEMI
```

### Frontend (Svelte)

```
frontend/src/
├── lib/
│   ├── ChatbotInline.svelte    # Componente principal (600 líneas)
│   ├── stores/                 # State management
│   └── balcon/                 # Otros servicios
└── main.js                     # Entry point
```

---

## 🔄 FLUJO COMPLETO DE UNA CONSULTA

### Paso 1: Usuario envía mensaje

```javascript
// ChatbotInline.svelte
async function processMessage(text) {
  const requestBody = { 
    message: text,
    history: formatHistoryForBackend(),
    category: currentCategory,
    subcategory: currentSubcategory,
    student_data: studentData
  };
  
  fetch('/api/chat/', { method: 'POST', body: JSON.stringify(requestBody) })
}
```

### Paso 2: Backend recibe y procesa

```python
# views.py → chat_api()
def chat_api(request):
    text = payload.get("message")
    conversation_history = payload.get("history", [])
    category = payload.get("category")
    student_data = payload.get("student_data")
    
    # Llamar al orquestador principal
    result = classify_with_rag(text, conversation_history, category, subcategory, student_data)
```

### Paso 3: Orquestador RAG (rag_chat_service.py)

El orquestador maneja **3 stages** y **4 niveles de confianza**:

#### **Stage 1: ready** (Primera interacción)

```python
if stage == "ready":
    # Interpretar intención del usuario
    intent_slots = interpretar_intencion_principal(user_text)  # LLM #1
    
    # Pedir confirmación
    return {
        "needs_confirmation": True,
        "summary": "¿Confirmas que quieres solicitar X?",
        "intent_slots": intent_slots
    }
```

**Llamadas LLM: 1**

---

#### **Stage 2: await_confirm** (Usuario confirma)

```python
if stage == "await_confirm":
    if es_confirmacion_positiva(user_text):
        # ===== AQUÍ EMPIEZA EL ANÁLISIS COMPLETO =====
        
        # 1. CONTEXTO CONVERSACIONAL (si aplica)
        context_evaluation = should_use_conversational_mode(user_text, history)  # LLM #2
        
        if context_evaluation["needs_context"]:
            enriched_text = enrich_query_with_context(user_text, history)  # LLM #3
            intent_slots = interpretar_intencion_principal(enriched_text)  # LLM #4
        
        # 2. ROUTING JERÁRQUICO
        hierarchical_cands = hierarchical_candidates(user_text)
        # → Carpetas: ['unemi_interno/estudiantes', 'unemi_interno/tic']
        # → Files: 4 PDFs candidatos
        
        # 3. QUERY UNDERSTANDING
        canon_q = _canonicalize_query(intent_query)
        entities = detect_entities(user_text)
        
        # 4. QUERY PLANNER
        planned_queries = plan_queries(intent_slots, canon_q, user_text)
        # → ["Solicitar cambio de paralelo...", "cambio paralelo"]
        
        # 5. MULTI-STAGE RETRIEVAL (ITERATIVO)
        for query in planned_queries[:3]:  # Máximo 3 queries
            
            # 5.1 Answerability Score
            ascore = answerability_score(query, retriever, k=12)  # LLM #5 (veredicto)
            # → {confidence: 0.600, verdict: "yes", non_empty_docs: 8}
            
            # 5.2 Si confianza baja, intentar variantes LLM
            if ascore["confidence"] < 0.65:
                variants = gen_query_variants_llm(query, n=4)  # LLM #6
                # → ["¿Cómo puedo solicitar cambio de sección?", ...]
                
                for variant in variants:
                    variant_score = answerability_score(variant, retriever)
                    # Usar la mejor variante
        
        # 5.3 RRF Fusion de documentos
        fused_docs = rrf_fuse([docs_q1, docs_q2, docs_q3])
        
        # 6. DECISIÓN SEGÚN CONFIANZA
        
        # === NIVEL 1: Alta confianza (≥ 0.70) ===
        if ascore["confidence"] >= TAU_NORMA:
            result = responder_desde_pdfs(intent_query, docs=fused_docs)  # LLM #7
            # → Respuesta con JSON: {has_information, confidence, answer}
            
            return {
                "summary": result["respuesta"],
                "confidence": ascore["confidence"],
                "handoff": False
            }
        
        # === NIVEL 3: Confianza media (0.42-0.70) ===
        if ascore["confidence"] >= TAU_MIN:
            result = responder_desde_pdfs(intent_query, docs=fused_docs)  # LLM #8
            
            # Auto-evaluación del LLM
            if result["has_information"]:  # LLM dice que SÍ tiene info
                
                # Verificar si es intención crítica OBLIGATORIA
                if intent_short in INTENCIONES_CRITICAS_OBLIGATORIAS:
                    # → Ir a Nivel 4 (derivar)
                    pass
                else:
                    # → Responder con la info
                    return {
                        "summary": result["respuesta"],
                        "confidence": 0.5,
                        "handoff": False
                    }
        
        # === NIVEL 4: No hay info (< 0.42 O intención crítica) ===
        
        # Recuperar texto ORIGINAL de la consulta (no el "sí")
        original_query = <recuperar del historial>
        
        # Evaluar handoff con clasificación LLM
        handoff_decision = should_handoff(
            confidence=ascore["confidence"],
            intent_short=intent_short,
            user_text=original_query  # LLM #9 (classify_with_llm)
        )
        # → {handoff: True, channel: "Mesa de Ayuda Académica", department: "académico"}
        
        # Clasificar con taxonomía LLM
        mapping = map_to_taxonomy(intent_query)  # LLM #10
        # → {categoria: "Académico", subcategoria: "Cambios"}
        
        # Mensaje de derivación
        respuesta_final = (
            f"{nombre}, no encontré información específica...\n\n"
            f"✅ He derivado tu solicitud a {channel} {emoji}\n\n"
            f"📧 Mantente atento a tu correo..."
        )
        
        return {
            "summary": respuesta_final,
            "handoff": True,
            "handoff_auto": True,  # ← Bloquea input
            "handoff_channel": channel,
            "handoff_department": department
        }
```

**Llamadas LLM en Nivel 4: 10 TOTAL**

---

## 🤖 CONTEO DE LLAMADAS AL LLM

### Por Consulta Completa (Worst Case - Nivel 4)

| # | Módulo | Función | Propósito | Cuándo |
|---|--------|---------|-----------|--------|
| 1 | intent_parser | interpretar_intencion_principal() | Extraer intención inicial | Stage ready |
| 2 | conversation_context | needs_context() | Detectar si necesita contexto | Si hay historial |
| 3 | conversation_context | enrich_query_with_context() | Enriquecer query con contexto | Si needs_context=true |
| 4 | intent_parser | interpretar_intencion_principal() | Re-interpretar query enriquecida | Si hubo enrichment |
| 5 | answerability | answerability_score() veredicto | Juez: ¿se puede responder? | Por cada planned_query |
| 6 | answerability | gen_query_variants_llm() | Generar variantes de query | Si confidence < 0.65 |
| 7 | pdf_responder | responder_desde_pdfs() | Generar respuesta Nivel 1 | Si confidence ≥ 0.70 |
| 8 | pdf_responder | responder_desde_pdfs() | Generar respuesta Nivel 3 | Si 0.42 ≤ conf < 0.70 |
| 9 | handoff | classify_with_llm() | Clasificar departamento/canal | Nivel 4 (no info) |
| 10 | taxonomy | map_to_taxonomy() | Mapear a taxonomía | Nivel 4 |

**TOTAL WORST CASE: 10 llamadas al LLM**

### Por Consulta Optimizada (Best Case - Nivel 1)

| # | Módulo | Función | Cuándo |
|---|--------|---------|--------|
| 1 | intent_parser | interpretar_intencion_principal() | Stage ready |
| 2 | answerability | answerability_score() veredicto | Nivel 1 |
| 3 | pdf_responder | responder_desde_pdfs() | Nivel 1 |

**TOTAL BEST CASE: 3 llamadas al LLM**

### Promedio Realista

- **Consulta simple con info clara**: ~3-5 llamadas
- **Consulta compleja sin info**: ~8-10 llamadas
- **Promedio general**: ~5-6 llamadas por consulta completa

---

## 🔍 ITERACIONES Y LOOPS

### 1. Multi-Stage Retrieval (3 iteraciones máx)

```python
for i, pq in enumerate(planned_queries[:3], 1):  # ← 3 ITERACIONES
    ascore = answerability_score(pq, retriever, k=12)  # LLM llamada por iteración
    
    if best_ascore is None or ascore["confidence"] > best_ascore["confidence"]:
        best_ascore = ascore
```

**Iteraciones: 3 máximo**
**LLM por iteración: 1 (veredicto)**

### 2. Query Variants Expansion (4 variantes)

```python
if ascore["confidence"] < 0.65:
    variants = gen_query_variants_llm(original_query, n=4)  # ← 1 LLM call genera 4 variantes
    
    for variant in variants:  # ← 4 ITERACIONES
        variant_score = answerability_score(variant, retriever)  # Sin LLM, solo metrics
```

**Iteraciones: 4 máximo**
**LLM: 1 para generar, 0 por variante (solo usa embeddings)**

### 3. Retrieval Interno (FAISS + BM25)

```python
# Dentro del retriever
docs = retriever.invoke(query)  # ← NO usa LLM, solo embeddings
# - Dense: MMR sobre FAISS (embeddings precalculados)
# - Sparse: BM25 (term frequency)
# - Ensemble: Combina ambos
```

**Iteraciones: 0 (búsqueda vectorial)**
**LLM: 0**

### 4. RRF Fusion

```python
fused_docs = rrf_fuse([docs_q1, docs_q2, docs_q3])  # ← Matemática pura, no LLM
```

**Iteraciones: 1**
**LLM: 0**

---

## 🎯 FEATURE FLAGS Y OPTIMIZACIONES

```python
# config.py
FEATURE_FLAGS = {
    "query_planner": True,          # ✅ Planner con subconsultas (aumenta recall)
    "rrf_fusion": True,             # ✅ RRF para combinar resultados
    "fuzzy_safety_net": False,      # ❌ OFF (usa RapidFuzz, lento)
    "entity_router": True,          # ✅ Router por entidades (EPUNEMI, SGA)
    "neutral_response": False,      # ❌ Respuesta sin "Según..."
    "cross_encoder_rerank": False,  # ❌ OFF (agrega 3-5 segundos)
}
```

### Optimizaciones Implementadas

1. **Caché de Índices FAISS**: No reconstruye si PDFs no cambian
2. **Caché de Retriever**: Reutiliza retriever entre consultas
3. **Límite de Queries**: Máximo 3 planned queries (no 5)
4. **Límite de Variantes**: Máximo 4 variantes LLM (no más)
5. **Cross-Encoder OFF**: Demasiado lento (3-5 seg), precision gain marginal
6. **Fuzzy Safety Net OFF**: RapidFuzz ralentiza sin beneficio claro

---

## 📊 TIEMPOS DE RESPUESTA

### Desglose por Componente (estimado)

| Componente | Tiempo | LLM Calls |
|------------|--------|-----------|
| Interpretación inicial | ~1-2s | 1 |
| Contexto conversacional | ~1-2s | 2 (si aplica) |
| Hierarchical routing | ~50-100ms | 0 |
| Query planning | ~10ms | 0 |
| Answerability (3 queries) | ~3-4s | 3 |
| Query variants LLM | ~2-3s | 1 |
| PDF respuesta | ~2-3s | 1 |
| Handoff classification | ~1-2s | 1 |
| Taxonomy mapping | ~1s | 1 |

**TOTAL WORST CASE: ~12-18 segundos**
**TOTAL BEST CASE: ~4-6 segundos**
**PROMEDIO: ~8-10 segundos**

### Bottlenecks Identificados

1. **LLM Calls**: ~1-2 segundos por llamada (quota rate limited)
2. **Embeddings FAISS**: ~100-300ms por query
3. **Multi-stage retrieval**: 3x las llamadas = 3x el tiempo

---

## 🗄️ BASE DE DATOS Y PERSISTENCIA

### Vectorstore (FAISS)

```python
# app/data/unemi_interno/estudiantes/
combined_index_<hash>/
├── index.faiss         # Índice vectorial
├── index.pkl           # Metadata
└── .index_metadata_<hash>.json  # Info de PDFs incluidos
```

**56 PDFs** en total:
- 4 PDFs en `unemi_interno/estudiantes/`
- 2 PDFs en `unemi_interno/tic/`
- 1 PDF en `epunemi/`
- 49 PDFs en `legal_nacional/` (leyes, códigos, reglamentos)

### Índice FAISS

```python
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
# Dimensión: 384
# Chunks: 1500 caracteres, overlap 300
# Total documentos: ~200-300 chunks
```

### ChromaDB

```
chroma_db/
└── chroma.sqlite3  # Base de datos SQLite de Chroma
```

**Nota**: Actualmente no se usa Chroma, solo FAISS.

### Django DB

```python
db.sqlite3  # Base de datos de Django (usuarios, sesiones)
```

---

## 🎨 FRONTEND (Svelte)

### ChatbotInline.svelte (600 líneas)

**Responsabilidades:**

1. **UI del Chatbot**: Input, burbujas de mensajes, formularios
2. **State Management**: 
   - `messages`: Array de mensajes del chat
   - `conversationBlocked`: Flag de input bloqueado tras handoff
   - `currentCategory`, `currentSubcategory`: Contexto de la conversación
   - `studentData`: Datos del estudiante logueado
3. **Comunicación con Backend**:
   - `processMessage()`: Envía mensaje al backend
   - `formatHistoryForBackend()`: Formatea historial para el API
4. **Manejo de Handoff Automático**:
   - Detecta `handoff_auto: true` en respuesta
   - Bloquea input automáticamente
   - Muestra mensaje de derivación

```javascript
// Detección de handoff automático
if (data.handoff_auto) {
  conversationBlocked = true;  // ← Bloquea input
}

// UI bloqueada
{#if conversationBlocked}
  <textarea disabled placeholder="Conversación derivada a agente..."></textarea>
  <button disabled>Derivado</button>
  <div class="blocked-notice">
    📧 Un agente se pondrá en contacto contigo por correo electrónico
  </div>
{/if}
```

---

## 🚀 DEPLOYMENT Y EJECUCIÓN

### Backend (Django)

```bash
# Activar entorno virtual
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Crear/aplicar migraciones
python manage.py makemigrations
python manage.py migrate

# Iniciar servidor
python manage.py runserver
```

**Puerto**: http://localhost:8000

### Frontend (Svelte + Vite)

```bash
cd frontend

# Instalar dependencias
npm install

# Iniciar dev server
npm run dev
```

**Puerto**: http://localhost:5173

### Scripts de Inicio

```batch
:: iniciar-vite.bat
@echo off
cd frontend
npm run dev
```

```powershell
# iniciar-vite.ps1
Set-Location -Path "frontend"
npm run dev
```

---

## 🔐 CONFIGURACIÓN

### Variables de Entorno

```python
# .env (en la raíz del proyecto)
GOOGLE_API_KEY=<tu-api-key-de-gemini>
```

### Configuración LLM

```python
# app/services/config.py
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # Modelo experimental
    temperature=0,              # Determinista
    api_key=GOOGLE_API_KEY,
    max_retries=2,
)
```

**Límites de Quota (Free Tier)**:
- 10 requests/minuto
- Con 8-10 LLM calls por consulta → ~1 consulta por minuto
- Solución: Implementar rate limiting o upgrade a paid tier

---

## 📈 MÉTRICAS Y LOGGING

### Logs del Sistema

```python
print(f"🎯 Entidades detectadas: {entities}")
print(f"📈 Términos boosteados: {routing_info['boosts'][:3]}")
print(f"📂 Routing: {method} - {len(files)} files, {len(folders)} folders")
print(f"🔎 [{i}] '{query[:60]}...' → conf: {ascore['confidence']:.3f}")
print(f"📊 RESULTADO FINAL:")
print(f"   Confidence: {ascore.get('confidence', 0):.3f}")
print(f"   Docs recuperados: {ascore.get('non_empty_docs', 0)}")
print(f"   Verdict: {ascore.get('verdict', 'N/A')}")
```

### Telemetría Implementada

- ✅ Confianza por query
- ✅ Número de documentos recuperados
- ✅ Veredicto del juez LLM
- ✅ Método de routing usado
- ✅ Entidades detectadas
- ✅ Variantes generadas
- ✅ Decisiones de handoff

---

## 🎯 RESUMEN EJECUTIVO

### Componentes Clave

1. **8 servicios backend** (3,163 líneas total)
2. **1 orquestador principal** (rag_chat_service.py - 691 líneas)
3. **10 llamadas LLM** (worst case) por consulta
4. **3 stages** de conversación (ready → confirm → RAG)
5. **4 niveles** de confianza (≥0.70, 0.42-0.70, <0.42, críticas)
6. **56 PDFs** en la base de conocimiento
7. **~200-300 chunks** indexados en FAISS
8. **3 iteraciones** multi-stage retrieval
9. **4 variantes** query expansion
10. **0 keywords** - todo evaluación LLM con JSON

### Flujo Completo Simplificado

```
Usuario escribe → Frontend envía →
Backend interpreta (LLM #1) → Pide confirmación →
Usuario confirma → 
  ├─ Detecta contexto (LLM #2, #3, #4)
  ├─ Router jerárquico (0 LLM)
  ├─ Multi-stage retrieval (LLM #5, #6)
  ├─ Genera respuesta (LLM #7, #8)
  ├─ Auto-evaluación (en JSON de #7, #8)
  └─ Si no hay info → Handoff (LLM #9, #10)
→ Frontend muestra respuesta
→ Si handoff_auto → Bloquea input
```

### Performance

- ⏱️ **4-18 segundos** por consulta (promedio 8-10s)
- 🤖 **3-10 LLM calls** (promedio 5-6)
- 🔄 **3 iteraciones** multi-stage máximo
- 📊 **Quota limit**: ~1 consulta/minuto (free tier)

### Optimizaciones Futuras

1. **Caché de respuestas frecuentes** (Redis)
2. **Parallel LLM calls** (async donde sea posible)
3. **Reduce query variants** de 4 a 2
4. **Upgrade Gemini paid tier** para más quota
5. **Pre-compute embeddings** offline
6. **Streaming responses** para UX más rápida

---



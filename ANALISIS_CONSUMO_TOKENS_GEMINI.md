# Análisis de Consumo de Tokens de Gemini en BalconDemo

## Resumen Ejecutivo

Este documento analiza cuántos tokens de Gemini se consumen en un flujo completo de conversación en BalconDemo, desde el saludo inicial hasta la respuesta final.

---

## Llamadas al LLM en el Sistema

### 1. Llamadas Directas desde BalconDemo

#### 1.1. `interpretar_intención_principal()` 
**Ubicación:** `app/services/intent_parser.py`

**Cuándo se llama:**
- Cuando el usuario envía un mensaje nuevo (no es confirmación)
- Cuando el usuario rechaza una confirmación y se reinterpreta
- Cuando se detecta un nuevo intento después de completar un requerimiento

**Frecuencia:** 1 llamada por mensaje nuevo del usuario

**Prompt:**
```
INTENT_SYSTEM (aprox. 1,200 tokens)
+ 
TEXTO: {mensaje_usuario} (aprox. 20-100 tokens)
```

**Respuesta esperada:**
```json
{
  "intent_short": "...",
  "intent_code": "...",
  "accion": "...",
  "objeto": "...",
  "needs_confirmation": true/false,
  "confirm_text": "...",
  "answer_type": "informativo/operativo",
  "multi_intent": true/false,
  "intents": [...]
}
```

**Tokens aproximados:**
- **Input:** ~1,200-1,300 tokens (prompt del sistema + mensaje del usuario)
- **Output:** ~200-400 tokens (JSON con slots de intención)
- **Total por llamada:** ~1,400-1,700 tokens

---

### 2. Llamadas desde PrivateGPT

#### 2.1. Query Expansion (Opcional)
**Ubicación:** `private_gpt/server/chat/chat_service.py` → `_expand_query()`

**Cuándo se llama:**
- Cuando `use_context=True` y query expansion está habilitado
- Antes de hacer la búsqueda RAG

**Frecuencia:** 1 llamada por consulta RAG (solo si está habilitado)

**Prompt:**
```
Dada la siguiente consulta del usuario, genera 2-3 variaciones o reformulaciones que puedan ayudar a encontrar información relacionada en documentos. 
Incluye sinónimos, términos relacionados, y formas alternativas de expresar lo mismo.

Consulta original: {query}

Genera solo las variaciones, una por línea, sin numeración ni explicaciones:
```

**Respuesta esperada:**
```
Variación 1
Variación 2
Variación 3
```

**Tokens aproximados:**
- **Input:** ~100-150 tokens (prompt + consulta original)
- **Output:** ~50-100 tokens (2-3 variaciones)
- **Total por llamada:** ~150-250 tokens

#### 2.2. RAG Generation (Principal)
**Ubicación:** `private_gpt/server/chat/chat_service.py` → `ContextChatEngine`

**Cuándo se llama:**
- Cuando `use_context=True` y se necesita generar una respuesta informativa
- Después de recuperar chunks relevantes del vector store

**Frecuencia:** 1 llamada por consulta RAG

**Prompt combinado:**
```
[SYSTEM PROMPT - default_query_system_prompt]
Eres un asistente RAG. Debes responder exclusivamente con un JSON válido...
(aprox. 500 tokens)

[SYSTEM PROMPT - Filtrado por rol desde BalconDemo]
ROL DEL USUARIO: ESTUDIANTE
FILTRADO CRITICO:
- SOLO usa documentos para ESTUDIANTES...
(aprox. 100 tokens)

[CONTEXTO - Chunks recuperados]
Chunk 1: {texto del documento 1} (aprox. 500 tokens)
Chunk 2: {texto del documento 2} (aprox. 500 tokens)
...
Chunk N: {texto del documento N} (aprox. 500 tokens)
(Total contexto: ~3,000-8,000 tokens dependiendo de top_k y tamaño de chunks)

[USER MESSAGE]
{mensaje del usuario} (aprox. 20-100 tokens)
```

**Respuesta esperada:**
```json
{
  "has_information": true/false,
  "response": "Respuesta completa del asistente...",
  "fuentes": [
    {"archivo": "...", "pagina": "..."}
  ]
}
```

**Tokens aproximados:**
- **Input:** ~3,700-8,700 tokens (prompts + contexto + mensaje)
- **Output:** ~200-1,500 tokens (respuesta JSON con texto completo)
- **Total por llamada:** ~3,900-10,200 tokens

---

## Flujo Completo Típico

### Escenario 1: Consulta Informativa Simple (Sin Confirmación)

```
1. Usuario: "¿Cómo cambio de paralelo?"
   ↓
2. BalconDemo: interpretar_intención_principal()
   → LLM Call #1: ~1,500 tokens
   → Resultado: needs_confirmation=false, answer_type="operativo"
   ↓
3. BalconDemo: Como es operativo, va directo a handoff
   → NO llama a PrivateGPT
   ↓
Total: 1 llamada LLM = ~1,500 tokens
```

### Escenario 2: Consulta Informativa con Confirmación

```
1. Usuario: "quiero información sobre becas"
   ↓
2. BalconDemo: interpretar_intención_principal()
   → LLM Call #1: ~1,500 tokens
   → Resultado: needs_confirmation=true, answer_type="informativo"
   ↓
3. Bot: "¿Quieres información sobre cómo obtener una beca para estudiar?"
   ↓
4. Usuario: "sí"
   ↓
5. BalconDemo: Detecta confirmación positiva
   → NO llama al LLM (usa slots guardados)
   ↓
6. BalconDemo: Llama a PrivateGPT
   ↓
7. PrivateGPT: Query Expansion (si está habilitado)
   → LLM Call #2: ~200 tokens
   ↓
8. PrivateGPT: RAG Generation
   → LLM Call #3: ~6,000 tokens (promedio)
   ↓
Total: 3 llamadas LLM = ~7,700 tokens
```

### Escenario 3: Consulta Informativa Completa (Con Solicitudes Relacionadas)

```
1. Usuario: "quiero información sobre becas"
   ↓
2. BalconDemo: interpretar_intención_principal()
   → LLM Call #1: ~1,500 tokens
   → Resultado: needs_confirmation=true, answer_type="informativo"
   ↓
3. Bot: "¿Quieres información sobre cómo obtener una beca para estudiar?"
   ↓
4. Usuario: "sí"
   ↓
5. BalconDemo: Detecta confirmación positiva
   → Busca solicitudes relacionadas (sin LLM, usa embeddings)
   ↓
6. Bot: "He encontrado algunas solicitudes previas relacionadas..."
   ↓
7. Usuario: "no hay solicitud relacionada"
   ↓
8. BalconDemo: Llama a PrivateGPT
   ↓
9. PrivateGPT: Query Expansion (si está habilitado)
   → LLM Call #2: ~200 tokens
   ↓
10. PrivateGPT: RAG Generation
    → LLM Call #3: ~6,000 tokens
    ↓
Total: 3 llamadas LLM = ~7,700 tokens
```

### Escenario 4: Consulta con Reinterpretación

```
1. Usuario: "quiero información sobre becas"
   ↓
2. BalconDemo: interpretar_intención_principal()
   → LLM Call #1: ~1,500 tokens
   ↓
3. Bot: "¿Quieres información sobre cómo obtener una beca para estudiar?"
   ↓
4. Usuario: "no"
   ↓
5. BalconDemo: Detecta confirmación negativa
   → Pide reformulación
   ↓
6. Usuario: "quiero saber los requisitos para cambiar de carrera"
   ↓
7. BalconDemo: interpretar_intención_principal()
   → LLM Call #2: ~1,500 tokens
   ↓
8. Bot: "¿Quieres información sobre los requisitos para cambiar de carrera?"
   ↓
9. Usuario: "sí"
   ↓
10. BalconDemo: Llama a PrivateGPT
    ↓
11. PrivateGPT: Query Expansion
    → LLM Call #3: ~200 tokens
    ↓
12. PrivateGPT: RAG Generation
    → LLM Call #4: ~6,000 tokens
    ↓
Total: 4 llamadas LLM = ~9,200 tokens
```

### Escenario 5: Multi-Requirement (Dos Requerimientos)

```
1. Usuario: "quiero información sobre becas y también cambiar de paralelo"
   ↓
2. BalconDemo: interpretar_intención_principal()
   → LLM Call #1: ~1,500 tokens
   → Resultado: multi_intent=true, intents=[req1, req2]
   ↓
3. Bot: "He detectado que estás pidiendo 2 cosas distintas... ¿te parece?"
   ↓
4. Usuario: "sí"
   ↓
5. BalconDemo: Muestra confirmación del primer requerimiento
   ↓
6. Usuario: "sí"
   ↓
7. BalconDemo: Llama a PrivateGPT para req1
   ↓
8. PrivateGPT: Query Expansion + RAG Generation
   → LLM Call #2: ~200 tokens (expansion)
   → LLM Call #3: ~6,000 tokens (RAG)
   ↓
9. Bot: Respuesta informativa para req1
   ↓
10. Bot: "Además, en tu mensaje también mencionaste otro requerimiento..."
    ↓
11. Usuario: Selecciona "Pasar al siguiente requerimiento"
    ↓
12. BalconDemo: Llama a PrivateGPT para req2
    ↓
13. PrivateGPT: Query Expansion + RAG Generation
    → LLM Call #4: ~200 tokens (expansion)
    → LLM Call #5: ~6,000 tokens (RAG)
    ↓
Total: 5 llamadas LLM = ~13,900 tokens
```

---

## Resumen de Tokens por Tipo de Flujo

| Escenario | Llamadas LLM | Tokens Aproximados |
|-----------|--------------|-------------------|
| **Operativo simple** (sin confirmación) | 1 | ~1,500 |
| **Informativo simple** (sin confirmación) | 3 | ~7,700 |
| **Informativo con confirmación** | 3 | ~7,700 |
| **Informativo con solicitudes relacionadas** | 3 | ~7,700 |
| **Con reinterpretación** | 4 | ~9,200 |
| **Multi-requirement (2 requerimientos)** | 5 | ~13,900 |
| **Multi-requirement (3 requerimientos)** | 7 | ~20,600 |

---

## Desglose Detallado de Tokens

### Por Componente

#### 1. `interpretar_intención_principal()`
- **Prompt del sistema (INTENT_SYSTEM):** ~1,200 tokens
- **Mensaje del usuario:** ~20-100 tokens
- **Total input:** ~1,220-1,300 tokens
- **Respuesta JSON:** ~200-400 tokens
- **Total:** ~1,420-1,700 tokens por llamada

#### 2. Query Expansion (PrivateGPT)
- **Prompt:** ~100 tokens
- **Consulta original:** ~20-50 tokens
- **Total input:** ~120-150 tokens
- **Variaciones generadas:** ~50-100 tokens
- **Total:** ~170-250 tokens por llamada

#### 3. RAG Generation (PrivateGPT)
- **System prompt (default_query_system_prompt):** ~500 tokens
- **System prompt (filtrado por rol):** ~100 tokens
- **Contexto (chunks recuperados):** ~3,000-8,000 tokens
  - Top-K chunks: 10-20
  - Tamaño promedio por chunk: ~300-500 tokens
- **Mensaje del usuario:** ~20-100 tokens
- **Total input:** ~3,620-8,700 tokens
- **Respuesta JSON:** ~200-1,500 tokens
- **Total:** ~3,820-10,200 tokens por llamada

---

## Factores que Afectan el Consumo

### 1. Tamaño del Contexto RAG
- **Más documentos ingestionados** → Más chunks potenciales → Más tokens en contexto
- **Top-K más alto** → Más chunks recuperados → Más tokens
- **Chunks más grandes** → Más tokens por chunk

### 2. Longitud de la Respuesta
- **Respuestas informativas largas** → Más tokens de output
- **Respuestas cortas o disculpas** → Menos tokens de output

### 3. Complejidad de la Consulta
- **Consultas simples** → Menos tokens en mensaje del usuario
- **Consultas complejas** → Más tokens en mensaje del usuario

### 4. Multi-Requirement
- **Cada requerimiento adicional** → +2 llamadas LLM (expansion + RAG)
- **Total:** ~6,200 tokens adicionales por requerimiento extra

---

## Optimizaciones Implementadas

### 1. Rate Limiting
- **Límite:** 9 RPM (Requests Per Minute)
- **Implementación:** Token bucket en `config.py`
- **Efecto:** Previene exceder límites de API de Gemini

### 2. Eliminación de Llamadas Redundantes
- **Antes:** `classify_with_llm()` llamaba al LLM para determinar `answer_type`
- **Ahora:** `answer_type` viene directamente de `interpretar_intención_principal()`
- **Ahorro:** ~1,500 tokens por consulta

### 3. Heurísticas en lugar de LLM
- **Handoff classification:** Usa `handoff_config.json` en lugar de LLM
- **Related request matching:** Usa embeddings en lugar de LLM
- **Ahorro:** ~2,000-3,000 tokens por consulta

### 4. Query Expansion Opcional
- **Configuración:** Puede deshabilitarse en PrivateGPT
- **Ahorro potencial:** ~200 tokens por consulta RAG

---

## Estimación de Costos (Gemini 2.5 Flash)

**Precios aproximados (a noviembre 2024):**
- **Input:** $0.075 por 1M tokens
- **Output:** $0.30 por 1M tokens

### Costo por Flujo Típico

**Escenario Informativo Simple (3 llamadas):**
- Input: ~7,700 tokens × $0.075/1M = **$0.00058**
- Output: ~1,700 tokens × $0.30/1M = **$0.00051**
- **Total:** **~$0.0011 por consulta**

**Escenario Multi-Requirement (2 requerimientos, 5 llamadas):**
- Input: ~13,900 tokens × $0.075/1M = **$0.00104**
- Output: ~2,900 tokens × $0.30/1M = **$0.00087**
- **Total:** **~$0.0019 por consulta**

---

## Recomendaciones para Reducir Tokens

### 1. Deshabilitar Query Expansion
- **Ahorro:** ~200 tokens por consulta RAG
- **Trade-off:** Posiblemente menor precisión en búsqueda

### 2. Reducir Top-K de Chunks
- **Actual:** 10-20 chunks
- **Recomendado:** 5-10 chunks
- **Ahorro:** ~1,500-3,000 tokens por consulta RAG

### 3. Reducir Tamaño de Chunks
- **Actual:** ~300-500 tokens por chunk
- **Recomendado:** ~200-300 tokens por chunk
- **Ahorro:** ~1,000-2,000 tokens por consulta RAG

### 4. Optimizar Prompts
- **INTENT_SYSTEM:** Reducir de ~1,200 a ~800 tokens
- **default_query_system_prompt:** Reducir de ~500 a ~300 tokens
- **Ahorro total:** ~600 tokens por consulta

---

## Conclusión

En un flujo típico de consulta informativa:
- **Llamadas LLM:** 3 (1 en BalconDemo + 2 en PrivateGPT)
- **Tokens totales:** ~7,700 tokens
- **Costo aproximado:** ~$0.0011 por consulta

El sistema está optimizado para minimizar llamadas al LLM, usando heurísticas y embeddings donde es posible, manteniendo solo las llamadas esenciales para la calidad de la experiencia del usuario.



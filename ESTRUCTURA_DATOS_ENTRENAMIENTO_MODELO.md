# Estructura de Datos para Entrenamiento de Modelo - Balcón de Servicios

## Introducción

Este documento describe la estructura de datos en formato JSON necesaria para entrenar un modelo que responda las solicitudes del Balcón de Servicios. La estructura está diseñada para capturar todos los aspectos relevantes de las conversaciones y respuestas del sistema.

---

## Estructura Principal: Conversación Completa

### Formato JSON para una Conversación

```json
{
  "conversation_id": "conv_2024_001",
  "timestamp": "2024-11-15T10:30:00Z",
  "student_context": {
    "student_id": 12345,
    "cedula": "1234567890",
    "nombre": "Juan Pérez",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería",
    "modalidad": "Presencial",
    "periodo_actual": "2024-2"
  },
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "message": "¿Cuáles son los requisitos para matricularme?",
      "timestamp": "2024-11-15T10:30:00Z"
    },
    {
      "turn": 2,
      "role": "assistant",
      "message": "Los requisitos para matricularse son:\n\n1. Haber aprobado el proceso de admisión\n2. Presentar documentos de identidad\n3. Realizar el pago de matrícula\n4. Completar el formulario de inscripción",
      "timestamp": "2024-11-15T10:30:05Z",
      "intent_slots": {
        "intent_short": "consultar requisitos de matrícula",
        "intent_code": "otro",
        "accion": "consultar",
        "objeto": "requisitos",
        "asignatura": "",
        "unidad_o_actividad": "",
        "periodo": "",
        "carrera": "",
        "facultad": "",
        "modalidad": "",
        "sistema": "",
        "problema": "",
        "detalle_libre": "requisitos para matricularme",
        "original_user_message": "¿Cuáles son los requisitos para matricularme?",
        "needs_confirmation": false,
        "confirm_text": "",
        "answer_type": "informativo",
        "multi_intent": false,
        "intents": []
      },
      "response_metadata": {
        "stage": "answer_ready",
        "mode": "informativo",
        "status": "answer",
        "has_information": true,
        "confidence": 0.9,
        "category": "Academico",
        "subcategory": "Matriculación",
        "department": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
      },
      "sources": [
        {
          "archivo": "Reglamento_de_Matricula.pdf",
          "pagina": "5",
          "relevance_score": 0.85
        },
        {
          "archivo": "Guia_del_Estudiante.pdf",
          "pagina": "12",
          "relevance_score": 0.78
        }
      ],
      "llm_calls": {
        "intent_interpretation": {
          "model": "gemini-2.5-flash",
          "tokens_input": 1320,
          "tokens_output": 280,
          "response_time_ms": 1200
        },
        "rag_generation": {
          "model": "gemini-2.5-flash",
          "tokens_input": 6200,
          "tokens_output": 450,
          "response_time_ms": 3500,
          "query_expansion": true,
          "chunks_retrieved": 10,
          "chunks_used": 3
        }
      }
    }
  ],
  "conversation_metadata": {
    "total_turns": 2,
    "total_llm_calls": 3,
    "total_tokens": 8250,
    "final_stage": "answer_ready",
    "solicitud_created": false,
    "solicitud_id": null
  }
}
```

---

## Estructura Detallada por Componente

### 1. Información del Estudiante (student_context)

```json
{
  "student_context": {
    "student_id": 12345,
    "cedula": "1234567890",
    "nombre": "Juan Pérez",
    "email": "juan.perez@unemi.edu.ec",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería",
    "modalidad": "Presencial",
    "periodo_actual": "2024-2",
    "nivel": "5to",
    "perfil_id": 67890,
    "perfil_tipo": "Ingeniería de Software Presencial"
  }
}
```

**Campos requeridos:**
- `student_id`: ID único del estudiante
- `cedula`: Cédula del estudiante
- `nombre`: Nombre completo
- `carrera`: Nombre de la carrera
- `facultad`: Facultad a la que pertenece
- `modalidad`: Modalidad de estudio (Presencial, En línea, Híbrida)
- `periodo_actual`: Período académico actual (formato: YYYY-N)

**Campos opcionales:**
- `email`: Correo electrónico
- `nivel`: Nivel académico actual
- `perfil_id`: ID del perfil activo
- `perfil_tipo`: Tipo de perfil completo

---

### 2. Mensajes de la Conversación (messages)

#### Mensaje del Usuario

```json
{
  "turn": 1,
  "role": "user",
  "message": "¿Cuáles son los requisitos para matricularme?",
  "timestamp": "2024-11-15T10:30:00Z",
  "metadata": {
    "is_greeting": false,
    "is_confirmation": false,
    "is_related_request_selection": false,
    "control_action": null,
    "uploaded_file": null
  }
}
```

**Campos requeridos:**
- `turn`: Número de turno en la conversación (1, 2, 3...)
- `role`: "user" o "assistant"
- `message`: Texto del mensaje
- `timestamp`: Fecha y hora del mensaje (ISO 8601)

**Campos opcionales en metadata:**
- `is_greeting`: true si es un saludo
- `is_confirmation`: true si es una confirmación ("sí", "no")
- `is_related_request_selection`: true si selecciona una solicitud relacionada
- `control_action`: "continue_current", "go_next_requirement", "new_requirement" (para multi-requirement)
- `uploaded_file`: Información del archivo subido (si aplica)

---

#### Mensaje del Asistente (Respuesta Completa)

```json
{
  "turn": 2,
  "role": "assistant",
  "message": "Los requisitos para matricularse son:\n\n1. Haber aprobado el proceso de admisión\n2. Presentar documentos de identidad\n3. Realizar el pago de matrícula\n4. Completar el formulario de inscripción",
  "timestamp": "2024-11-15T10:30:05Z",
  "intent_slots": {
    "intent_short": "consultar requisitos de matrícula",
    "intent_code": "otro",
    "accion": "consultar",
    "objeto": "requisitos",
    "asignatura": "",
    "unidad_o_actividad": "",
    "periodo": "",
    "carrera": "",
    "facultad": "",
    "modalidad": "",
    "sistema": "",
    "problema": "",
    "detalle_libre": "requisitos para matricularme",
    "original_user_message": "¿Cuáles son los requisitos para matricularme?",
    "needs_confirmation": false,
    "confirm_text": "",
    "answer_type": "informativo",
    "multi_intent": false,
    "intents": []
  },
  "response_metadata": {
    "stage": "answer_ready",
    "mode": "informativo",
    "status": "answer",
    "has_information": true,
    "confidence": 0.9,
    "category": "Academico",
    "subcategory": "Matriculación",
    "department": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "needs_confirmation": false,
    "confirmed": true,
    "handoff": false,
    "needs_handoff_details": false,
    "needs_related_request_selection": false
  },
  "sources": [
    {
      "archivo": "Reglamento_de_Matricula.pdf",
      "pagina": "5",
      "relevance_score": 0.85,
      "chunk_text": "Los requisitos para la matrícula incluyen..."
    }
  ],
  "related_requests": [],
  "llm_calls": {
    "intent_interpretation": {
      "model": "gemini-2.5-flash",
      "prompt": "Eres un extractor de intención...",
      "response": "{\"intent_short\": \"consultar requisitos de matrícula\", ...}",
      "tokens_input": 1320,
      "tokens_output": 280,
      "response_time_ms": 1200
    },
    "rag_generation": {
      "model": "gemini-2.5-flash",
      "query": "requisitos para matricularme",
      "expanded_queries": [
        "requisitos para matricularme",
        "qué necesito para matricularme",
        "documentos para matrícula"
      ],
      "response": "Los requisitos para matricularse son...",
      "tokens_input": 6200,
      "tokens_output": 450,
      "response_time_ms": 3500,
      "query_expansion": true,
      "chunks_retrieved": 10,
      "chunks_used": 3,
      "has_information": true
    }
  }
}
```

---

### 3. Intent Slots (intent_slots)

Estructura completa de los slots de intención extraídos:

```json
{
  "intent_slots": {
    "intent_short": "consultar requisitos de matrícula",
    "intent_code": "otro",
    "accion": "consultar",
    "objeto": "requisitos",
    "asignatura": "",
    "unidad_o_actividad": "",
    "periodo": "2024-2",
    "carrera": "Ingeniería de Software",
    "facultad": "Facultad de Ciencias e Ingeniería",
    "modalidad": "Presencial",
    "sistema": "SGA",
    "problema": "",
    "detalle_libre": "requisitos para matricularme",
    "original_user_message": "¿Cuáles son los requisitos para matricularme?",
    "needs_confirmation": false,
    "confirm_text": "",
    "answer_type": "informativo",
    "multi_intent": false,
    "intents": [
      {
        "id": "req_1",
        "intent_short": "consultar requisitos de matrícula",
        "intent_code": "otro",
        "accion": "consultar",
        "objeto": "requisitos",
        "answer_type": "informativo",
        "needs_confirmation": false,
        "confirm_text": ""
      }
    ]
  }
}
```

**Campos importantes:**
- `intent_short`: Resumen corto de la intención (12-16 palabras)
- `intent_code`: Código de intención predefinido
- `accion`: Verbo principal (consultar, cambiar, solicitar, etc.)
- `objeto`: Objeto sobre el que recae la acción
- `answer_type`: "informativo" o "operativo"
- `multi_intent`: true si hay múltiples requerimientos
- `intents`: Lista de requerimientos individuales (si multi_intent=true)

---

### 4. Response Metadata (response_metadata)

```json
{
  "response_metadata": {
    "stage": "answer_ready",
    "mode": "informativo",
    "status": "answer",
    "has_information": true,
    "confidence": 0.9,
    "category": "Academico",
    "subcategory": "Matriculación",
    "department": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
    "needs_confirmation": false,
    "confirmed": true,
    "handoff": false,
    "needs_handoff_details": false,
    "needs_related_request_selection": false
  }
}
```

**Campos:**
- `stage`: Estado de la conversación
- `mode`: Modo de operación (informativo/operativo/handoff)
- `status`: Estado de la respuesta (answer/need_details/handoff/error)
- `has_information`: true si se encontró información útil
- `confidence`: Nivel de confianza (0.0 - 1.0)
- `category`: Categoría seleccionada (si aplica)
- `subcategory`: Subcategoría seleccionada (si aplica)
- `department`: Departamento determinado para handoff

---

### 5. Sources (Fuentes de Información)

```json
{
  "sources": [
    {
      "archivo": "Reglamento_de_Matricula.pdf",
      "pagina": "5",
      "relevance_score": 0.85,
      "chunk_text": "Los requisitos para la matrícula incluyen haber aprobado el proceso de admisión, presentar documentos de identidad válidos, realizar el pago correspondiente y completar el formulario de inscripción en línea.",
      "chunk_id": "chunk_12345",
      "document_id": "doc_67890"
    }
  ]
}
```

**Campos:**
- `archivo`: Nombre del archivo PDF
- `pagina`: Número de página
- `relevance_score`: Score de relevancia (0.0 - 1.0)
- `chunk_text`: Texto del chunk utilizado (opcional pero recomendado)
- `chunk_id`: ID del chunk en el vector store
- `document_id`: ID del documento completo

---

### 6. Related Requests (Solicitudes Relacionadas)

```json
{
  "related_requests": [
    {
      "id": 123,
      "codigo": "SOL-2024-001",
      "descripcion": "Cambio de paralelo en Matemática",
      "estado": "En trámite",
      "fecha_creacion": "2024-10-15T08:00:00Z",
      "departamento": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS",
      "similarity_score": 0.82,
      "selected": false
    }
  ]
}
```

**Campos:**
- `id`: ID de la solicitud
- `codigo`: Código de la solicitud (SOL-YYYY-XXX)
- `descripcion`: Descripción de la solicitud
- `estado`: Estado actual (Pendiente, En trámite, Aprobado, etc.)
- `fecha_creacion`: Fecha de creación
- `departamento`: Departamento asignado
- `similarity_score`: Score de similitud con la consulta actual
- `selected`: true si el usuario seleccionó esta solicitud

---

### 7. LLM Calls (Llamadas al LLM)

```json
{
  "llm_calls": {
    "intent_interpretation": {
      "model": "gemini-2.5-flash",
      "prompt": "Eres un extractor de intención...",
      "response": "{\"intent_short\": \"consultar requisitos de matrícula\", ...}",
      "tokens_input": 1320,
      "tokens_output": 280,
      "response_time_ms": 1200,
      "temperature": 0,
      "success": true,
      "error": null
    },
    "rag_generation": {
      "model": "gemini-2.5-flash",
      "query": "requisitos para matricularme",
      "expanded_queries": [
        "requisitos para matricularme",
        "qué necesito para matricularme",
        "documentos para matrícula"
      ],
      "system_prompt": "Eres un asistente RAG...",
      "context_chunks": [
        {
          "chunk_id": "chunk_12345",
          "text": "Los requisitos para la matrícula...",
          "score": 0.85
        }
      ],
      "response": "Los requisitos para matricularse son...",
      "tokens_input": 6200,
      "tokens_output": 450,
      "response_time_ms": 3500,
      "query_expansion": true,
      "chunks_retrieved": 10,
      "chunks_used": 3,
      "has_information": true,
      "success": true,
      "error": null
    }
  }
}
```

**Información útil para entrenamiento:**
- Prompts utilizados
- Respuestas del LLM
- Tokens consumidos
- Tiempo de respuesta
- Chunks utilizados (para RAG)

---

## Casos Especiales

### Caso 1: Handoff Operativo

```json
{
  "conversation_id": "conv_2024_002",
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "message": "quiero cambiar de paralelo"
    },
    {
      "turn": 2,
      "role": "assistant",
      "message": "¿Quieres solicitar un cambio de paralelo?",
      "response_metadata": {
        "stage": "await_confirm",
        "mode": "operativo",
        "needs_confirmation": true
      }
    },
    {
      "turn": 3,
      "role": "user",
      "message": "sí"
    },
    {
      "turn": 4,
      "role": "assistant",
      "message": "Gerson, Entiendo que necesitas realizar una solicitud. Para procesarla correctamente, te voy a conectar con mis compañeros humanos del departamento **DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS**. 💁\n\nPara enviar tu solicitud, necesito que:\n1. Describes nuevamente tu solicitud con todos los detalles\n2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud",
      "response_metadata": {
        "stage": "await_handoff_details",
        "mode": "handoff",
        "handoff": true,
        "needs_handoff_details": true,
        "department": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
      }
    },
    {
      "turn": 5,
      "role": "user",
      "message": "Necesito cambiar de paralelo porque tengo conflicto de horarios",
      "metadata": {
        "uploaded_file": {
          "filename": "solicitud_cambio_paralelo.pdf",
          "size_bytes": 245678,
          "content_type": "application/pdf"
        }
      }
    },
    {
      "turn": 6,
      "role": "assistant",
      "message": "Gerson, ✅ Tu solicitud ha sido enviada exitosamente al departamento **DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS**. 📋\n\nUn agente se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud. Mantente atento a tu correo.",
      "response_metadata": {
        "stage": "answer_ready",
        "mode": "handoff",
        "status": "answer",
        "handoff": true,
        "solicitud_created": true,
        "solicitud_id": "SOL-2024-045"
      }
    }
  ]
}
```

---

### Caso 2: Multi-Requirement

```json
{
  "conversation_id": "conv_2024_003",
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "message": "quiero información sobre becas y también cambiar de paralelo"
    },
    {
      "turn": 2,
      "role": "assistant",
      "message": "He detectado que estás pidiendo 2 cosas distintas:\n\n1. Información sobre becas estudiantiles\n2. Cambio de paralelo\n\n¿Te parece?",
      "intent_slots": {
        "multi_intent": true,
        "intents": [
          {
            "id": "req_1",
            "intent_short": "información sobre becas estudiantiles",
            "answer_type": "informativo"
          },
          {
            "id": "req_2",
            "intent_short": "cambio de paralelo",
            "answer_type": "operativo"
          }
        ]
      },
      "response_metadata": {
        "stage": "await_confirm",
        "is_multi_req_confirmation": true
      }
    },
    {
      "turn": 3,
      "role": "user",
      "message": "sí"
    },
    {
      "turn": 4,
      "role": "assistant",
      "message": "¿Quieres información sobre becas estudiantiles?",
      "response_metadata": {
        "stage": "await_confirm",
        "current_requirement_index": 0
      }
    },
    {
      "turn": 5,
      "role": "user",
      "message": "sí"
    },
    {
      "turn": 6,
      "role": "assistant",
      "message": "Las becas estudiantiles están disponibles para...",
      "response_metadata": {
        "stage": "answer_ready",
        "has_information": true,
        "requirements": [
          {
            "id": "req_1",
            "status": "completed"
          },
          {
            "id": "req_2",
            "status": "pending"
          }
        ],
        "multi_requirement_menu": true
      }
    }
  ]
}
```

---

### Caso 3: Sin Información (Handoff Informativo)

```json
{
  "conversation_id": "conv_2024_004",
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "message": "¿Cómo puedo consultar las notas de mi hijo?"
    },
    {
      "turn": 2,
      "role": "assistant",
      "message": "Gerson, Este caso necesita ser revisado por mis compañeros humanos del departamento **DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS**. 💁\n\nPara enviar tu solicitud, por favor:\n1. Describe nuevamente tu requerimiento con todos los detalles.\n2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.\n\nCon esta información podré derivarlo al equipo correspondiente. ✔️",
      "response_metadata": {
        "stage": "await_handoff_details",
        "mode": "handoff",
        "has_information": false,
        "department": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
      },
      "llm_calls": {
        "rag_generation": {
          "has_information": false,
          "response": "Lo siento, no encontré información específica sobre cómo consultar las notas de un hijo en los documentos disponibles."
        }
      }
    }
  ]
}
```

---

## Formato de Archivo Recomendado

### Opción 1: JSON Lines (.jsonl)

Un archivo con una conversación por línea:

```
{"conversation_id": "conv_2024_001", "messages": [...], ...}
{"conversation_id": "conv_2024_002", "messages": [...], ...}
{"conversation_id": "conv_2024_003", "messages": [...], ...}
```

**Ventajas:**
- Fácil de procesar línea por línea
- Eficiente para datasets grandes
- Permite streaming

---

### Opción 2: JSON Array

Un archivo con todas las conversaciones en un array:

```json
{
  "dataset_version": "1.0",
  "created_at": "2024-11-15T10:00:00Z",
  "total_conversations": 1000,
  "conversations": [
    {"conversation_id": "conv_2024_001", ...},
    {"conversation_id": "conv_2024_002", ...},
    ...
  ]
}
```

**Ventajas:**
- Estructura más clara
- Fácil de validar
- Permite metadatos del dataset

---

## Datos Mínimos Requeridos

Para entrenar un modelo básico, necesitas al menos:

```json
{
  "conversation_id": "conv_2024_001",
  "messages": [
    {
      "turn": 1,
      "role": "user",
      "message": "¿Cuáles son los requisitos para matricularme?"
    },
    {
      "turn": 2,
      "role": "assistant",
      "message": "Los requisitos para matricularse son:\n\n1. Haber aprobado el proceso de admisión\n2. Presentar documentos de identidad\n3. Realizar el pago de matrícula\n4. Completar el formulario de inscripción",
      "intent_slots": {
        "intent_short": "consultar requisitos de matrícula",
        "answer_type": "informativo"
      },
      "response_metadata": {
        "has_information": true,
        "category": "Academico",
        "subcategory": "Matriculación"
      },
      "sources": [
        {
          "archivo": "Reglamento_de_Matricula.pdf",
          "pagina": "5"
        }
      ]
    }
  ]
}
```

---

## Datos Recomendados para Entrenamiento Avanzado

Para un modelo más robusto, incluye:

1. **Historial completo de conversación** (no solo el último turno)
2. **Contexto del estudiante** (carrera, facultad, modalidad)
3. **Slots de intención completos** (todos los campos)
4. **Fuentes con texto completo** (chunk_text)
5. **Prompts utilizados** (para entender cómo se generó la respuesta)
6. **Múltiples variaciones** de la misma pregunta
7. **Casos edge** (errores, sin información, multi-requirement)
8. **Solicitudes relacionadas** (para contexto)

---

## Script de Exportación Sugerido

Basado en el script existente `exportar_solicitudes_balcon.py`, puedes crear uno que exporte en este formato:

```python
# exportar_conversaciones_entrenamiento.py
import json
from datetime import datetime
from django.db.models import Q

# Obtener conversaciones del sistema
# (necesitarías almacenar el historial de conversaciones)

conversaciones = []

for conversacion in Conversacion.objects.filter(
    fecha_creacion__year=2024,
    status=True
):
    datos = {
        "conversation_id": f"conv_{conversacion.id}",
        "timestamp": conversacion.fecha_creacion.isoformat(),
        "student_context": {
            "student_id": conversacion.estudiante.id,
            "cedula": conversacion.estudiante.cedula,
            "nombre": conversacion.estudiante.nombre_completo(),
            "carrera": conversacion.estudiante.carrera.nombre,
            # ... más campos
        },
        "messages": [
            # Construir mensajes desde el historial
        ],
        "conversation_metadata": {
            "total_turns": len(conversacion.mensajes),
            "final_stage": conversacion.estado_final,
            "solicitud_created": conversacion.solicitud is not None
        }
    }
    conversaciones.append(datos)

# Exportar en formato JSON Lines
with open('conversaciones_entrenamiento.jsonl', 'w', encoding='utf-8') as f:
    for conv in conversaciones:
        f.write(json.dumps(conv, ensure_ascii=False) + '\n')
```

---

## Consideraciones para el Entrenamiento

### 1. Balance de Datos

Asegúrate de tener:
- **Consultas informativas** (con y sin información)
- **Consultas operativas** (handoff)
- **Multi-requirement** (múltiples requerimientos)
- **Casos con confirmación** y **sin confirmación**
- **Casos con solicitudes relacionadas** y **sin relacionadas**

### 2. Calidad de las Respuestas

- Las respuestas deben ser **correctas** y **completas**
- Deben incluir **fuentes** cuando sea posible
- Deben ser **naturales** y **conversacionales**

### 3. Variación de Lenguaje

Incluye variaciones de:
- Formas de preguntar lo mismo
- Niveles de formalidad
- Errores ortográficos comunes
- Expresiones coloquiales

### 4. Contexto

- Incluye **historial de conversación** completo
- Incluye **contexto del estudiante** (carrera, facultad, etc.)
- Incluye **solicitudes relacionadas** cuando aplique

---

## Ejemplo Completo de Dataset

Ver archivo `ejemplo_dataset_entrenamiento.jsonl` (si lo creas) con múltiples conversaciones de ejemplo en formato JSON Lines.

---

## Conclusión

Para entrenar un modelo efectivo, necesitas:

1. **Mensajes del usuario** (preguntas/solicitudes)
2. **Respuestas del asistente** (completas y correctas)
3. **Slots de intención** (estructura extraída)
4. **Metadatos de respuesta** (stage, mode, status, etc.)
5. **Fuentes** (documentos y páginas utilizadas)
6. **Contexto del estudiante** (carrera, facultad, etc.)
7. **Historial de conversación** (para contexto)
8. **LLM calls** (opcional pero útil para entender el proceso)

El formato JSON propuesto captura todos estos aspectos y es flexible para diferentes tipos de entrenamiento (fine-tuning, RAG, clasificación, etc.).



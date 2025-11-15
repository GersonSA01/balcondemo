# Flujo Completo del Balcón de Servicios - Documentación Exhaustiva

## Tabla de Contenidos

1. [Introducción](#introducción)
2. [Estados de Conversación (Stages)](#estados-de-conversación-stages)
3. [Modos de Operación](#modos-de-operación)
4. [Estados de Respuesta](#estados-de-respuesta)
5. [Flujo Principal Completo](#flujo-principal-completo)
6. [Mensajes del Sistema](#mensajes-del-sistema)
7. [Casos Especiales](#casos-especiales)
8. [Multi-Requirement Flow](#multi-requirement-flow)
9. [Handoff Flow](#handoff-flow)
10. [Manejo de Errores](#manejo-de-errores)

---

## Introducción

El Balcón de Servicios es un sistema de chat inteligente que ayuda a los estudiantes de la UNEMI a:
- Obtener información sobre trámites y procedimientos
- Realizar solicitudes operativas que requieren intervención humana
- Consultar el estado de sus solicitudes previas
- Relacionar nuevas solicitudes con solicitudes anteriores

El sistema utiliza:
- **LLM (Gemini 2.5 Flash)** para interpretar intenciones y generar respuestas
- **PrivateGPT** para búsqueda RAG (Retrieval Augmented Generation) en documentos
- **Heurísticas** para clasificación sin LLM cuando es posible
- **Embeddings** para matching de solicitudes relacionadas

---

## Estados de Conversación (Stages)

El sistema maneja los siguientes estados:

### 1. `GREETING` - Saludo Inicial
**Cuándo se activa:**
- Al iniciar la conversación
- Cuando el usuario escribe "hola", "buenos días", etc.

**Acción:** Mostrar mensaje de bienvenida personalizado

### 2. `AWAIT_INTENT` - Esperando Intención
**Cuándo se activa:**
- Estado inicial por defecto
- Después de completar un requerimiento
- Cuando se resetea el contexto

**Acción:** Interpretar el mensaje del usuario y extraer intención

### 3. `AWAIT_CONFIRM` - Esperando Confirmación
**Cuándo se activa:**
- Cuando `needs_confirmation=True` después de interpretar intención
- Cuando se detectan múltiples requerimientos

**Acción:** Mostrar mensaje de confirmación y esperar respuesta del usuario

### 4. `AWAIT_RELATED_REQUEST` - Esperando Selección de Solicitud Relacionada
**Cuándo se activa:**
- Cuando se encuentran solicitudes relacionadas con la consulta actual
- Después de confirmar una intención operativa o informativa

**Acción:** Mostrar lista de solicitudes relacionadas y esperar selección

### 5. `AWAIT_HANDOFF_DETAILS` - Esperando Detalles para Handoff
**Cuándo se activa:**
- Cuando `answer_type="operativo"` y se confirma la intención
- Cuando PrivateGPT retorna `has_information=False`

**Acción:** Solicitar detalles adicionales y archivo para crear solicitud

### 6. `ANSWER_READY` - Respuesta Lista
**Cuándo se activa:**
- Cuando PrivateGPT retorna `has_information=True`
- Cuando se completa un handoff exitosamente

**Acción:** Mostrar respuesta final al usuario

---

## Modos de Operación

### `INFORMATIVE` - Modo Informativo
**Cuándo:** `answer_type="informativo"`
- Consultas que se pueden responder con información de documentos
- Ejemplos: "¿Cuáles son los requisitos para matricularme?", "¿Qué horarios tiene la biblioteca?"

**Flujo:**
1. Interpretar intención
2. Confirmar (si es necesario)
3. Buscar solicitudes relacionadas
4. Llamar a PrivateGPT RAG
5. Mostrar respuesta con fuentes

### `OPERATIVE` - Modo Operativo
**Cuándo:** `answer_type="operativo"`
- Trámites que requieren acción humana
- Ejemplos: "Quiero cambiar de paralelo", "Necesito anular mi matrícula"

**Flujo:**
1. Interpretar intención
2. Confirmar (si es necesario)
3. Buscar solicitudes relacionadas
4. Derivar a departamento (handoff)
5. Solicitar detalles y archivo
6. Crear solicitud en el sistema

### `HANDOFF` - Modo Handoff
**Cuándo:** Se necesita derivar a un agente humano
- Casos operativos
- Casos informativos sin información suficiente

**Flujo:**
1. Determinar departamento
2. Solicitar detalles y archivo
3. Crear solicitud
4. Confirmar envío

---

## Estados de Respuesta

### `ANSWER` - Respuesta Lista
- Respuesta completa con información
- Puede incluir fuentes (PDFs, páginas)

### `NEED_DETAILS` - Necesita Detalles
- Requiere confirmación del usuario
- Requiere detalles adicionales para handoff

### `HANDOFF` - Derivación
- Solicitud derivada a departamento
- Requiere detalles y archivo

### `ERROR` - Error
- Error técnico o de procesamiento
- Mensaje de error amigable

---

## Flujo Principal Completo

### Escenario 1: Consulta Informativa Simple (Sin Confirmación)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuario envía mensaje                                    │
│    "¿Cuáles son los requisitos para matricularme?"         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Sistema: interpretar_intención_principal()                │
│    - LLM Call #1: Extraer intención                         │
│    - Resultado:                                             │
│      • needs_confirmation: false                            │
│      • answer_type: "informativo"                           │
│      • intent_short: "consultar requisitos de matrícula"   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Sistema: Buscar solicitudes relacionadas                 │
│    - Usa embeddings (sin LLM)                               │
│    - Resultado: No hay solicitudes relacionadas            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Sistema: Llamar a PrivateGPT RAG                         │
│    - Query Expansion (opcional): LLM Call #2               │
│    - RAG Generation: LLM Call #3                            │
│    - Resultado: has_information=true                        │
│      • response: "Los requisitos para matricularse son..."  │
│      • fuentes: [{"archivo": "Reglamento.pdf", "pagina": 5}]│
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Bot: Mostrar respuesta con fuentes                       │
│    "Los requisitos para matricularse son:                   │
│     1. ...                                                  │
│     2. ...                                                  │
│                                                              │
│     📄 Fuentes: Reglamento.pdf (página 5)"                  │
└─────────────────────────────────────────────────────────────┘
```

**Mensajes del Bot:**
- **Mensaje final:** Respuesta informativa con fuentes

**Total LLM Calls:** 3 (1 interpretación + 1 expansion opcional + 1 RAG)

---

### Escenario 2: Consulta Informativa con Confirmación

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuario: "quiero información sobre becas"                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Sistema: interpretar_intención_principal()                │
│    - LLM Call #1                                            │
│    - Resultado:                                             │
│      • needs_confirmation: true                            │
│      • confirm_text: "¿Quieres información sobre cómo      │
│        obtener una beca para estudiar?"                     │
│      • answer_type: "informativo"                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Bot: "¿Quieres información sobre cómo obtener una beca   │
│         para estudiar?"                                      │
│    [Botón: Sí] [Botón: No]                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Usuario: "sí"              Usuario: "no"
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 4. Sistema:      │      │ 4. Bot: "Gracias por aclarar. │
│ Confirmación     │      │    Cuéntame nuevamente tu    │
│ positiva         │      │    requerimiento..."         │
│                  │      └──────────────────────────────┘
│ Continuar con    │
│ flujo informativo│
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Sistema: Buscar solicitudes relacionadas                 │
│    - Resultado: No hay                                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Sistema: Llamar a PrivateGPT RAG                         │
│    - LLM Call #2: Query Expansion                           │
│    - LLM Call #3: RAG Generation                            │
│    - Resultado: has_information=true                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Bot: Mostrar respuesta con fuentes                       │
└─────────────────────────────────────────────────────────────┘
```

**Mensajes del Bot:**
- **Mensaje de confirmación:** "¿Quieres información sobre cómo obtener una beca para estudiar?"
- **Mensaje final:** Respuesta informativa con fuentes

**Total LLM Calls:** 3 (1 interpretación + 1 expansion + 1 RAG)

---

### Escenario 3: Consulta Operativa (Cambio de Paralelo)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuario: "quiero cambiar de paralelo"                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Sistema: interpretar_intención_principal()                │
│    - LLM Call #1                                            │
│    - Resultado:                                             │
│      • needs_confirmation: true                            │
│      • confirm_text: "¿Quieres solicitar un cambio de     │
│        paralelo?"                                            │
│      • answer_type: "operativo"                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Bot: "¿Quieres solicitar un cambio de paralelo?"         │
│    [Botón: Sí] [Botón: No]                                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Usuario: "sí"              Usuario: "no"
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 4. Sistema:      │      │ 4. Bot: "Gracias por aclarar. │
│ Confirmación     │      │    Cuéntame nuevamente..."   │
│ positiva         │      └──────────────────────────────┘
│                  │
│ answer_type =    │
│ "operativo"      │
└────────┬─────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Sistema: Buscar solicitudes relacionadas                 │
│    - Resultado: 2 solicitudes encontradas                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Bot: "{Nombre}, He encontrado 2 solicitud(es)           │
│         relacionada(s) con tu requerimiento:                │
│                                                              │
│         1. SOL-2024-001 - Cambio de paralelo Matemática     │
│            Estado: En trámite                               │
│                                                              │
│         2. SOL-2024-045 - Cambio de paralelo Física         │
│            Estado: Aprobado                                 │
│                                                              │
│         ¿Deseas relacionar tu solicitud actual con alguna   │
│         de estas? Si ninguna es relevante, puedes          │
│         continuar sin relacionar."                          │
│                                                              │
│    [Seleccionar 1] [Seleccionar 2] [No hay solicitud        │
│    relacionada]                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Usuario: "1" o          Usuario: "no hay"
    código SOL-2024-001              │
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 7. Sistema:      │      │ 7. Sistema: Continuar sin     │
│ Guardar          │      │    relacionar                │
│ solicitud        │      │                              │
│ relacionada      │      │ Determinar departamento      │
│                  │      │ desde handoff_config.json    │
└────────┬─────────┘      └──────────────┬───────────────┘
         │                                │
         │                                ▼
         │                    ┌──────────────────────────────┐
         │                    │ 8. Bot: "{Nombre}, Entiendo  │
         │                    │         que necesitas        │
         │                    │         realizar una         │
         │                    │         solicitud. Para      │
         │                    │         procesarla           │
         │                    │         correctamente, te    │
         │                    │         voy a conectar con   │
         │                    │         mis compañeros       │
         │                    │         humanos del          │
         │                    │         departamento         │
         │                    │         **DIRECCIÓN DE       │
         │                    │         GESTIÓN Y           │
         │                    │         SERVICIOS          │
         │                    │         ACADÉMICOS**. 💁    │
         │                    │                              │
         │                    │         Para enviar tu      │
         │                    │         solicitud,           │
         │                    │         necesito que:       │
         │                    │         1. Describes        │
         │                    │            nuevamente tu    │
         │                    │            solicitud con    │
         │                    │            todos los        │
         │                    │            detalles          │
         │                    │         2. Subas un archivo │
         │                    │            PDF o imagen    │
         │                    │            (máximo 4MB)     │
         │                    │            relacionado con  │
         │                    │            tu solicitud    │
         │                    │                              │
         │                    │    [Campo de texto]         │
         │                    │    [Botón: Subir archivo]  │
         │                    │    [Botón: Enviar]          │
         └────────────────────┼──────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. Usuario: Proporciona detalles y archivo                  │
│    Detalles: "Necesito cambiar de paralelo porque..."      │
│    Archivo: solicitud_cambio_paralelo.pdf                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 10. Sistema: Crear solicitud en el sistema                 │
│     - Código generado: SOL-2024-XXX                        │
│     - Estado: Pendiente                                    │
│     - Departamento: DIRECCIÓN DE GESTIÓN Y SERVICIOS       │
│       ACADÉMICOS                                            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 11. Bot: "{Nombre}, ✅ Tu solicitud ha sido enviada        │
│          exitosamente al departamento **DIRECCIÓN DE        │
│          GESTIÓN Y SERVICIOS ACADÉMICOS**. 📋              │
│                                                              │
│          Un agente se pondrá en contacto contigo pronto    │
│          para dar seguimiento a tu solicitud. Mantente     │
│          atento a tu correo."                              │
└─────────────────────────────────────────────────────────────┘
```

**Mensajes del Bot:**
1. **Confirmación:** "¿Quieres solicitar un cambio de paralelo?"
2. **Solicitudes relacionadas:** Lista de solicitudes relacionadas (si hay)
3. **Solicitud de detalles:** Mensaje pidiendo detalles y archivo
4. **Confirmación de envío:** Mensaje de éxito con código de solicitud

**Total LLM Calls:** 1 (solo interpretación, no se llama a PrivateGPT para operativos)

---

### Escenario 4: Consulta Informativa Sin Información Suficiente

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuario: "¿Cómo puedo consultar las notas de mi hijo?"  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Sistema: interpretar_intención_principal()               │
│    - LLM Call #1                                            │
│    - Resultado:                                             │
│      • needs_confirmation: false                           │
│      • answer_type: "informativo"                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Sistema: Buscar solicitudes relacionadas                 │
│    - Resultado: No hay                                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Sistema: Llamar a PrivateGPT RAG                          │
│    - LLM Call #2: Query Expansion                           │
│    - LLM Call #3: RAG Generation                            │
│    - Resultado: has_information=false                        │
│      • response: "Lo siento, no encontré información..."   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Sistema: Determinar departamento para handoff            │
│    - Usa handoff_config.json                                │
│    - Departamento: DIRECCIÓN DE GESTIÓN Y SERVICIOS        │
│      ACADÉMICOS                                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Bot: "{Nombre}, Este caso necesita ser revisado por      │
│         mis compañeros humanos del departamento             │
│         **DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS**.   │
│         💁                                                  │
│                                                              │
│         Para enviar tu solicitud, por favor:                │
│         1. Describe nuevamente tu requerimiento con        │
│            todos los detalles.                              │
│         2. Sube un archivo PDF o imagen (máximo 4MB)       │
│            relacionado con tu solicitud.                    │
│                                                              │
│         Con esta información podré derivarlo al equipo      │
│         correspondiente. ✔️                                 │
│                                                              │
│    [Campo de texto]                                         │
│    [Botón: Subir archivo]                                   │
│    [Botón: Enviar]                                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Usuario: Proporciona detalles y archivo                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Sistema: Crear solicitud                                 │
│    - Código: SOL-2024-XXX                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. Bot: Mensaje de confirmación de envío                   │
└─────────────────────────────────────────────────────────────┘
```

**Mensajes del Bot:**
1. **Solicitud de detalles:** Mensaje pidiendo detalles y archivo (handoff)
2. **Confirmación de envío:** Mensaje de éxito

**Total LLM Calls:** 3 (1 interpretación + 1 expansion + 1 RAG)

---

## Mensajes del Sistema

### Mensajes de Saludo

#### Saludo Inicial (GREETING)
```
"Hola{Nombre}! 👋 Soy tu asistente virtual del Balcón de Servicios UNEMI. 
Estoy aquí para ayudarte con tus consultas y solicitudes. 
¿En qué puedo asistirte hoy?"
```

**Variantes:**
- Con nombre: "Hola Gerson! 👋 Soy tu asistente..."
- Sin nombre: "Hola! 👋 Soy tu asistente..."

**Cuándo se muestra:**
- Al iniciar la conversación
- Cuando el usuario escribe "hola", "buenos días", "buenas tardes", etc.

---

### Mensajes de Confirmación

#### Confirmación Simple
```
"¿Quieres {confirm_text}?"
```

**Ejemplos:**
- "¿Quieres consultar la nota de Parcial 1 en Matemática del período 2025-2?"
- "¿Quieres solicitar un cambio de paralelo?"
- "¿Quieres información sobre becas estudiantiles?"

**Cuándo se muestra:**
- Cuando `needs_confirmation=true` después de interpretar intención
- El usuario puede responder "sí", "no", o proporcionar más detalles

---

#### Confirmación de Múltiples Requerimientos
```
"He detectado que estás pidiendo {N} cosas distintas:

1. {intent_short_1}
2. {intent_short_2}
...

¿Te parece?"
```

**Ejemplo:**
```
"He detectado que estás pidiendo 2 cosas distintas:

1. Información sobre becas estudiantiles
2. Cambio de paralelo en Matemática

¿Te parece?"
```

**Cuándo se muestra:**
- Cuando `multi_intent=true` y hay múltiples requerimientos detectados

**Respuestas posibles:**
- "sí" → Proceder con el primer requerimiento
- "no" → Proceder con el segundo requerimiento

---

### Mensajes de Solicitudes Relacionadas

#### Lista de Solicitudes Relacionadas
```
"{Nombre}, He encontrado {N} solicitud(es) relacionada(s) con tu requerimiento:

1. {codigo} - {descripcion}
   Estado: {estado}

2. {codigo} - {descripcion}
   Estado: {estado}

¿Deseas relacionar tu solicitud actual con alguna de estas? 
Si ninguna es relevante, puedes continuar sin relacionar."
```

**Ejemplo:**
```
"Gerson, He encontrado 2 solicitud(es) relacionada(s) con tu requerimiento:

1. SOL-2024-001 - Cambio de paralelo Matemática
   Estado: En trámite

2. SOL-2024-045 - Cambio de paralelo Física
   Estado: Aprobado

¿Deseas relacionar tu solicitud actual con alguna de estas? 
Si ninguna es relevante, puedes continuar sin relacionar."
```

**Cuándo se muestra:**
- Después de confirmar una intención (informativa o operativa)
- Cuando se encuentran solicitudes relacionadas usando embeddings

**Opciones del usuario:**
- Seleccionar número (1, 2, 3...)
- Seleccionar código (SOL-2024-001)
- Decir "no hay solicitud relacionada" o "ninguna es relevante"

---

### Mensajes de Handoff (Derivación)

#### Solicitud de Detalles para Handoff
```
"{Nombre}, {mensaje_introductorio}

Para enviar tu solicitud, {instrucciones}:

1. {instrucción_1}
2. {instrucción_2}

{mensaje_cierre}"
```

**Variantes:**

**Para casos operativos:**
```
"{Nombre}, Entiendo que necesitas realizar una solicitud. 
Para procesarla correctamente, te voy a conectar con mis compañeros 
humanos del departamento **{departamento}**. 💁

Para enviar tu solicitud, necesito que:
1. Describes nuevamente tu solicitud con todos los detalles
2. Subas un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud"
```

**Para casos informativos sin información:**
```
"{Nombre}, Este caso necesita ser revisado por mis compañeros humanos 
del departamento **{departamento}**. 💁

Para enviar tu solicitud, por favor:
1. Describe nuevamente tu requerimiento con todos los detalles.
2. Sube un archivo PDF o imagen (máximo 4MB) relacionado con tu solicitud.

Con esta información podré derivarlo al equipo correspondiente. ✔️"
```

**Cuándo se muestra:**
- Cuando `answer_type="operativo"` y se confirma la intención
- Cuando PrivateGPT retorna `has_information=false` para consultas informativas

**Campos requeridos:**
- Texto con detalles de la solicitud
- Archivo PDF o imagen (máximo 4MB)

---

#### Confirmación de Envío de Solicitud
```
"{Nombre}, ✅ Tu solicitud ha sido enviada exitosamente al departamento 
**{departamento}**. 📋

Un agente se pondrá en contacto contigo pronto para dar seguimiento 
a tu solicitud. Mantente atento a tu correo."
```

**Ejemplo:**
```
"Gerson, ✅ Tu solicitud ha sido enviada exitosamente al departamento 
**DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS**. 📋

Un agente se pondrá en contacto contigo pronto para dar seguimiento 
a tu solicitud. Mantente atento a tu correo."
```

**Cuándo se muestra:**
- Después de crear exitosamente una solicitud en el sistema
- El código de solicitud se guarda en el sistema pero no se muestra al usuario

---

### Mensajes de Respuesta Informativa

#### Respuesta con Información
```
"{respuesta_texto}

📄 Fuentes:
- {archivo_1} (página {pagina_1})
- {archivo_2} (página {pagina_2})
..."
```

**Ejemplo:**
```
"Los requisitos para matricularse son:

1. Haber aprobado el proceso de admisión
2. Presentar documentos de identidad
3. Realizar el pago de matrícula
4. Completar el formulario de inscripción

📄 Fuentes:
- Reglamento de Matrícula.pdf (página 5)
- Guía del Estudiante.pdf (página 12)"
```

**Cuándo se muestra:**
- Cuando PrivateGPT retorna `has_information=true`
- La respuesta viene directamente de PrivateGPT RAG

---

### Mensajes de Error

#### Error de Procesamiento
```
"⚠️ No puedo procesar tu solicitud en este momento. Por favor, intenta 
nuevamente o ingresa tu solicitud manualmente a través del formulario 
del Balcón de Servicios."
```

**Cuándo se muestra:**
- Cuando hay un error técnico al procesar la solicitud
- Cuando no se pueden recuperar los slots de intención

---

#### Error de Rate Limit
```
"Lo siento, no puedo responder por el momento debido a límites de 
cuota. Por favor, ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Cuándo se muestra:**
- Cuando se excede el límite de 9 RPM (Requests Per Minute) de Gemini
- Cuando hay problemas con la API key

---

#### Error de Timeout
```
"Lo siento, la solicitud está tardando más de lo esperado. Por favor, 
intenta nuevamente o ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Cuándo se muestra:**
- Cuando una llamada al LLM o a PrivateGPT excede el timeout

---

### Mensajes de Reinterpretación

#### Solicitud de Reformulación
```
"Gracias por aclarar. Cuéntame nuevamente tu requerimiento en una 
frase y lo vuelvo a interpretar."
```

**Cuándo se muestra:**
- Cuando el usuario rechaza una confirmación ("no")
- Cuando el usuario proporciona información que no coincide con la intención detectada

---

### Mensajes de Multi-Requirement

#### Menú de Opciones después de Completar Requerimiento
```
"Además, en tu mensaje también mencionaste otro requerimiento:

{descripción_del_siguiente_requerimiento}

¿Qué deseas hacer?

[Seguir con este mismo tema]
[Pasar al siguiente requerimiento]
[Empezar un requerimiento nuevo]"
```

**Cuándo se muestra:**
- Después de completar un requerimiento cuando hay más requerimientos pendientes en la cola
- Se muestra automáticamente después de una respuesta informativa o handoff completado

**Opciones:**
- **"Seguir con este mismo tema"** (`continue_current`): Mantiene el requerimiento actual activo para hacer preguntas de seguimiento
- **"Pasar al siguiente requerimiento"** (`go_next_requirement`): Mueve al siguiente requerimiento pendiente en la cola
- **"Empezar un requerimiento nuevo"** (`new_requirement`): Limpia la cola y permite empezar un nuevo requerimiento

---

## Casos Especiales

### Caso 1: Usuario Selecciona Solicitud Relacionada

**Flujo:**
1. Usuario confirma intención
2. Sistema muestra solicitudes relacionadas
3. Usuario selecciona una (por número o código)
4. Sistema guarda la selección en `selected_related_request`
5. Si es informativo: Se envía a PrivateGPT con contexto de la solicitud relacionada
6. Si es operativo: Se usa la solicitud relacionada como contexto para el handoff

**Mensaje enriquecido a PrivateGPT:**
```
{mensaje_original}

[CONTEXTO: Solicitud relacionada seleccionada - Código: {codigo}]
Descripción de la solicitud relacionada: {descripcion}
```

---

### Caso 2: Usuario Dice "No Hay Solicitud Relacionada"

**Flujo:**
1. Sistema muestra solicitudes relacionadas
2. Usuario dice "no hay solicitud relacionada" o "ninguna es relevante"
3. Sistema continúa sin relacionar
4. `selected_related_request` se establece en `None`

**Mensaje a PrivateGPT:**
- Solo el mensaje original del usuario, sin contexto adicional

---

### Caso 3: Usuario Hace Pregunta de Seguimiento

**Flujo:**
1. Sistema completa un requerimiento (respuesta informativa o handoff)
2. Usuario hace una pregunta relacionada
3. Sistema detecta si es nuevo intento o seguimiento:
   - Si el requerimiento anterior está completo Y no hay requerimientos pendientes → Nuevo intento
   - Si hay requerimientos pendientes → Seguimiento del requerimiento actual
   - Si el mensaje es corto y parece confirmación → Seguimiento

**Ejemplo:**
```
Bot: "Los requisitos para matricularse son: 1. ... 2. ..."
Usuario: "¿Y cuánto cuesta la matrícula?"
Sistema: Detecta como nuevo intento (requerimiento anterior completo)
Bot: "El costo de la matrícula es..."
```

---

### Caso 4: Usuario Sube Archivo sin Detalles

**Flujo:**
1. Sistema solicita detalles y archivo para handoff
2. Usuario sube archivo pero no proporciona texto
3. Sistema acepta el archivo y procede con la creación de solicitud
4. La descripción se toma del `intent_short` o `original_user_message`

**Lógica:**
- Si hay archivo → Proceder con handoff
- Si no hay archivo → Esperar hasta que se proporcione

---

## Multi-Requirement Flow

### Detección de Múltiples Requerimientos

**Cuándo se detecta:**
- El LLM en `interpretar_intención_principal()` detecta `multi_intent=true`
- El mensaje contiene múltiples requerimientos independientes

**Ejemplo de mensaje:**
```
"Quiero información sobre becas y también cambiar de paralelo"
```

**Resultado del LLM:**
```json
{
  "multi_intent": true,
  "intents": [
    {
      "id": "req_1",
      "intent_short": "información sobre becas estudiantiles",
      "answer_type": "informativo",
      "needs_confirmation": true,
      "confirm_text": "¿Quieres información sobre becas estudiantiles?"
    },
    {
      "id": "req_2",
      "intent_short": "cambio de paralelo",
      "answer_type": "operativo",
      "needs_confirmation": true,
      "confirm_text": "¿Quieres solicitar un cambio de paralelo?"
    }
  ]
}
```

---

### Flujo Completo Multi-Requirement

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Usuario: "quiero información sobre becas y también       │
│             cambiar de paralelo"                             │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Sistema: interpretar_intención_principal()                │
│    - LLM Call #1                                            │
│    - Resultado: multi_intent=true, intents=[req1, req2]    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Bot: "He detectado que estás pidiendo 2 cosas distintas:│
│                                                              │
│         1. Información sobre becas estudiantiles            │
│         2. Cambio de paralelo                              │
│                                                              │
│         ¿Te parece?"                                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Usuario: "sí"              Usuario: "no"
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 4. Bot:          │      │ 4. Bot:                       │
│ "¿Quieres        │      │ "¿Quieres solicitar un        │
│  información     │      │  cambio de paralelo?"         │
│  sobre becas     │      │  (Confirmación del req_2)    │
│  estudiantiles?"  │      └──────────────┬───────────────┘
│  (Confirmación    │                      │
│  del req_1)      │                      │
└────────┬─────────┘                      │
         │                                 │
    Usuario: "sí"                    Usuario: "sí"
         │                                 │
         ▼                                 ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 5. Sistema:      │      │ 5. Sistema:                   │
│ Procesar req_1   │      │ Procesar req_2                │
│ (informativo)    │      │ (operativo)                   │
│                  │      │                               │
│ - Buscar         │      │ - Buscar solicitudes          │
│   relacionadas   │      │   relacionadas               │
│ - Llamar RAG     │      │ - Handoff                    │
│ - Mostrar        │      │ - Solicitar detalles         │
│   respuesta      │      │ - Crear solicitud            │
└────────┬─────────┘      └──────────────┬───────────────┘
         │                                │
         ▼                                ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Bot: "Además, en tu mensaje también mencionaste otro     │
│         requerimiento:                                      │
│                                                              │
│         {descripción_del_siguiente_requerimiento}           │
│                                                              │
│         ¿Qué deseas hacer?                                  │
│                                                              │
│    [Seguir con este mismo tema]                             │
│    [Pasar al siguiente requerimiento]                      │
│    [Empezar un requerimiento nuevo]"                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Usuario: "Pasar al        Usuario: "Seguir con
    siguiente"                este mismo tema"
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────────────────┐
│ 7. Sistema:      │      │ 7. Sistema:                  │
│ Procesar req_2   │      │ Mantener req_1 activo        │
│                  │      │ Permitir preguntas de        │
│ - Buscar         │      │ seguimiento                  │
│   relacionadas   │      │                              │
│ - Handoff        │      │                              │
│ - Solicitar      │      │                              │
│   detalles       │      │                              │
│ - Crear          │      │                              │
│   solicitud      │      │                              │
└──────────────────┘      └──────────────────────────────┘
```

---

## Handoff Flow

### Tipos de Handoff

#### 1. Handoff Operativo
**Cuándo:** `answer_type="operativo"`

**Flujo:**
1. Usuario confirma intención operativa
2. Sistema busca solicitudes relacionadas
3. Si hay relacionadas → Mostrar para selección
4. Determinar departamento desde `handoff_config.json`
5. Solicitar detalles y archivo
6. Crear solicitud en el sistema
7. Confirmar envío

**No se llama a PrivateGPT** (solo se usa para interpretación inicial)

---

#### 2. Handoff Informativo Sin Información
**Cuándo:** `answer_type="informativo"` pero PrivateGPT retorna `has_information=false`

**Flujo:**
1. Usuario confirma intención informativa
2. Sistema busca solicitudes relacionadas
3. Llamar a PrivateGPT RAG
4. PrivateGPT retorna `has_information=false`
5. Determinar departamento desde `handoff_config.json`
6. Solicitar detalles y archivo
7. Crear solicitud en el sistema
8. Confirmar envío

---

### Determinación de Departamento

**Fuentes (en orden de prioridad):**
1. **Desde categoría/subcategoría:** Si el usuario seleccionó categoría y subcategoría desde el frontend
2. **Desde `handoff_config.json`:** Usando `classify_with_heuristics()` basado en `intent_slots`
3. **Por defecto:** "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"

**Ejemplo de `handoff_config.json`:**
```json
{
  "Academico": {
    "Cambio de paralelo": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
  },
  "Bienestar estudiantil": {
    "Beca estudiantil": "DIRECCIÓN DE BIENESTAR ESTUDIANTIL"
  }
}
```

---

### Creación de Solicitud

**Datos incluidos:**
- `solicitante_id`: ID del estudiante
- `descripcion`: Texto proporcionado por el usuario o `intent_short`
- `tipo`: 2 (SOLICITUD)
- `archivo_solicitud`: Archivo subido por el usuario
- `servicio_nombre`: Nombre del servicio desde subcategoría
- `servicio_sigla`: Sigla del servicio
- `departamento`: Departamento determinado
- `cedula`: Cédula del estudiante
- `perfil_id`: ID del perfil activo
- `perfil_tipo`: Tipo de perfil (carrera + modalidad)

**Código generado:**
- Formato: `SOL-{año}-{número_secuencial}`
- Ejemplo: `SOL-2024-001`

---

## Manejo de Errores

### Errores de LLM

#### Rate Limit (429)
**Mensaje al usuario:**
```
"Lo siento, no puedo responder por el momento debido a límites de 
cuota. Por favor, ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Acción del sistema:**
- Esperar según el header `retry-after` si está presente
- Reintentar hasta `max_retries` veces
- Si falla después de reintentos → Mostrar mensaje de error

---

#### Timeout
**Mensaje al usuario:**
```
"Lo siento, la solicitud está tardando más de lo esperado. Por favor, 
intenta nuevamente o ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Acción del sistema:**
- Timeout configurado: 30 segundos para requests normales
- Si excede timeout → Mostrar mensaje de error

---

#### Error de API Key
**Mensaje al usuario:**
```
"Lo siento, no puedo responder por el momento debido a un problema 
técnico. Por favor, ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Acción del sistema:**
- Detectar error de autenticación
- Mostrar mensaje genérico (no exponer detalles técnicos)

---

### Errores de PrivateGPT

#### PrivateGPT No Disponible
**Mensaje al usuario:**
```
"Lo siento, el servicio de información no está disponible en este 
momento. Por favor, intenta nuevamente más tarde o ingresa tu 
solicitud manualmente a través del formulario del Balcón de Servicios."
```

**Acción del sistema:**
- Verificar `health_check()` antes de llamar a PrivateGPT
- Si no está disponible → Derivar directamente a handoff

---

#### Error al Crear Solicitud
**Mensaje al usuario:**
```
"Hubo un problema al crear tu solicitud. Por favor, intenta nuevamente 
o ingresa tu solicitud manualmente a través del formulario del 
Balcón de Servicios."
```

**Acción del sistema:**
- Loggear el error completo
- Mostrar mensaje genérico al usuario
- Continuar el flujo aunque falle la creación

---

### Errores de Parsing

#### Error al Parsear Respuesta del LLM
**Mensaje al usuario:**
```
"⚠️ No puedo procesar tu solicitud en este momento. Por favor, 
intenta nuevamente o ingresa tu solicitud manualmente a través del 
formulario del Balcón de Servicios."
```

**Acción del sistema:**
- Usar valores por defecto para slots faltantes
- Intentar continuar con el flujo si es posible
- Si no es posible → Mostrar mensaje de error

---

## Resumen de Flujos y LLM Calls

| Escenario | LLM Calls | Descripción |
|-----------|-----------|-------------|
| **Operativo simple** | 1 | Solo interpretación |
| **Informativo simple** | 3 | Interpretación + Expansion + RAG |
| **Informativo con confirmación** | 3 | Interpretación + Expansion + RAG |
| **Informativo sin información** | 3 | Interpretación + Expansion + RAG → Handoff |
| **Multi-requirement (2 reqs)** | 5 | Interpretación + (Expansion + RAG) × 2 |
| **Con reinterpretación** | 4+ | Interpretación × 2 + Expansion + RAG |

---

## Campos de Respuesta del Sistema

### Campos Principales (Nuevo Contrato)

```json
{
  "stage": "greeting" | "await_intent" | "await_confirm" | 
           "await_related_request" | "await_handoff_details" | "answer_ready",
  "mode": "informativo" | "operativo" | "handoff",
  "status": "answer" | "need_details" | "handoff" | "error",
  "message": "Texto del mensaje del bot",
  "response": "Texto de respuesta (igual que message)",
  "has_information": true | false | null,
  "fuentes": [
    {"archivo": "Reglamento.pdf", "pagina": "5"}
  ],
  "source_pdfs": ["Reglamento.pdf"],
  "intent_slots": {
    "intent_short": "...",
    "answer_type": "informativo" | "operativo",
    ...
  }
}
```

### Campos Legacy (Compatibilidad)

```json
{
  "needs_confirmation": true | false,
  "confirmed": true | false,
  "handoff": true | false,
  "needs_handoff_details": true | false,
  "needs_related_request_selection": true | false,
  "category": "Academico" | null,
  "subcategory": "Cambio de paralelo" | null,
  "confidence": 0.0 - 1.0,
  "campos_requeridos": [],
  "related_requests": [...],
  "handoff_channel": "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"
}
```

---

## Conclusión

El flujo del Balcón de Servicios está diseñado para:
- **Minimizar llamadas al LLM** usando heurísticas cuando es posible
- **Proporcionar respuestas rápidas** para consultas informativas
- **Derivar eficientemente** casos operativos a agentes humanos
- **Manejar múltiples requerimientos** en una sola conversación
- **Relacionar solicitudes** para mejor contexto y seguimiento
- **Manejar errores** de forma amigable y sin exponer detalles técnicos

El sistema es robusto, eficiente y proporciona una experiencia de usuario fluida y natural.



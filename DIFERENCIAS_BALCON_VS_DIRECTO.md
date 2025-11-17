# Diferencias entre Consultas del Balcón de Servicios vs Consultas Directas

## Resumen

Cuando haces una consulta sobre "justificar una falta", obtienes respuestas diferentes dependiendo de cómo la hagas:

1. **A través del Balcón de Servicios** (chatbot integrado): La consulta pasa por `classify_with_privategpt` que aplica reglas de negocio específicas.
2. **Directo en el frontend** (consulta directa a PrivateGPT): La consulta va directamente a PrivateGPT sin pasar por las reglas de negocio.

## Flujo 1: Balcón de Servicios (con reglas de negocio)

### Proceso:

1. **Usuario pregunta**: "¿Cómo justificar una falta?"
2. **Frontend envía a**: `/api/chat/` (endpoint Django)
3. **Backend procesa con**: `classify_with_privategpt()` en `privategpt_chat_service.py`
4. **Se aplican reglas**:
   - `interpretar_intencion_principal()` - Extrae la intención
   - `_classify_answer_type_fallback()` - Clasifica como "operativo" o "informativo"
   - **`_aplicar_excepciones_informativas()`** - **AQUÍ SE APLICA LA REGLA ESPECIAL**
     - Detecta patrones como "justificar falta", "justificar inasistencia"
     - **Convierte de "operativo" a "informativo"** porque está prohibido
     - Esto hace que se consulte en el reglamento en lugar de crear una solicitud
5. **Se envía a PrivateGPT** con contexto adicional:
   - Rol del usuario (estudiante, profesor, etc.)
   - Categoría y subcategoría seleccionadas
   - Datos del estudiante (carrera, facultad, etc.)
   - Mensaje normalizado (sin tildes)
6. **Respuesta**: Información del reglamento sobre justificación de faltas

### Código relevante:

```python
# app/services/privategpt_chat_service.py línea 324-373
EXCEPCIONES_INFORMATIVAS = {
    "justificar falta",
    "justificar inasistencia",
    "como justificar falta",
    # ... más patrones
}

def _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, user_text):
    # Si detecta "justificar falta", convierte de "operativo" a "informativo"
    # Esto hace que se consulte en documentos en lugar de crear solicitud
```

## Flujo 2: Consulta Directa (sin reglas de negocio)

### Proceso:

1. **Usuario pregunta**: "¿Cómo justificar una falta?"
2. **Frontend envía directamente a**: PrivateGPT API (sin pasar por Django)
   - **Nota**: Según el código actual, `ChatbotInline.svelte` siempre envía a `/api/chat/`
   - Si hay consultas "directas", probablemente se hacen desde otro componente o interfaz
3. **No se aplican reglas**:
   - No pasa por `classify_with_privategpt`
   - No se aplica `_aplicar_excepciones_informativas`
   - No se detecta que "justificar falta" debe ser informativo
4. **PrivateGPT procesa**:
   - Busca en los documentos sin contexto adicional
   - Puede encontrar información sobre justificación de faltas
   - Pero no sabe que está "prohibido" según las reglas de negocio
5. **Respuesta**: Puede dar información diferente o menos precisa

### Posibles escenarios de "consulta directa":

1. **Interfaz alternativa**: Si existe otra interfaz que consulta directamente a PrivateGPT
2. **Diferentes parámetros**: Mismo endpoint pero con diferentes `student_data` o `category/subcategory`
3. **Sin contexto de usuario**: Consulta sin `student_data`, por lo que no se aplica el contexto de rol

## ¿Por qué son diferentes?

### Contexto adicional en Balcón de Servicios:

1. **Rol del usuario**: Se agrega `ROL DEL USUARIO: ESTUDIANTE` al mensaje
2. **Normalización de texto**: Se quitan tildes y caracteres especiales
3. **Session context**: Se envía información de carrera, facultad, modalidad
4. **Reglas de negocio**: Se aplican excepciones que convierten ciertas intenciones

### Ejemplo de mensaje enviado a PrivateGPT:

**Balcón de Servicios:**
```
System: ROL DEL USUARIO: ESTUDIANTE
User: como justificar una falta
Session Context: {carrera: "Ingeniería", facultad: "Tecnológica", modalidad: "Presencial"}
```

**Consulta Directa:**
```
User: ¿Cómo justificar una falta?
(Sin contexto adicional)
```

## Solución: Unificar el comportamiento

Para que ambas formas den la misma respuesta, necesitas:

### Opción 1: Hacer que las consultas directas pasen por el backend

Modificar el frontend para que todas las consultas vayan a `/api/chat/` en lugar de directamente a PrivateGPT.

### Opción 2: Aplicar las mismas reglas en el frontend

Si el frontend consulta directamente a PrivateGPT, necesitas replicar la lógica de `_aplicar_excepciones_informativas` en el frontend.

### Opción 3: Configurar PrivateGPT con reglas en el system prompt

Agregar las reglas de negocio directamente en el `default_query_system_prompt` de PrivateGPT.

## Recomendación

**Usar siempre el endpoint `/api/chat/`** porque:
- Aplica todas las reglas de negocio
- Agrega contexto del usuario
- Maneja el flujo completo (confirmación, solicitudes relacionadas, etc.)
- Es más consistente y mantenible

## Verificación

Para verificar qué está pasando, revisa los logs del backend cuando haces una consulta:

```python
# En privategpt_chat_service.py línea 3334
answer_type = _aplicar_excepciones_informativas(answer_type, intent_short, intent_slots, original_user_request)
print(f"🔍 [Answer Type] Después de excepciones: {answer_type}")
```

Si ves que `answer_type` cambia de "operativo" a "informativo", significa que la regla se está aplicando correctamente.

## Cómo verificar en tu caso específico

1. **Abre las herramientas de desarrollador** (F12) en el navegador
2. **Ve a la pestaña Network/Red**
3. **Haz la consulta "justificar falta" de ambas formas**
4. **Compara las peticiones**:
   - ¿Ambas van a `/api/chat/`?
   - ¿Tienen los mismos parámetros (`student_data`, `category`, `subcategory`)?
   - ¿El `student_data` está completo en ambas?

5. **Revisa los logs del backend Django**:
   - Busca mensajes que digan `[Answer Type]` o `[Excepciones]`
   - Verifica si `_aplicar_excepciones_informativas` se está llamando

## Posibles causas de diferencias

1. **Diferentes `student_data`**: Si una consulta tiene `student_data` completo y otra no, el contexto será diferente
2. **Diferentes `category/subcategory`**: Esto puede afectar cómo se procesa la intención
3. **Diferentes historiales**: Si una consulta tiene historial previo y otra no, el flujo puede ser diferente
4. **Timing**: Si haces las consultas en momentos diferentes, los documentos en PrivateGPT pueden haber cambiado


# Análisis de Contexto en PrivateGPT

## Problema Identificado

El frontend directo de PrivateGPT y el balcón están enviando diferentes cosas a PrivateGPT:

### Frontend Directo de PrivateGPT (UI):
1. **Agrega automáticamente** el `default_query_system_prompt` desde `settings-docker.yaml`
2. Este system prompt incluye instrucciones de filtrado por rol (líneas 70-76 de settings-docker.yaml)
3. **NO envía** `session_context` con `user_role`
4. **NO envía** system message adicional con "ROL DEL USUARIO: ESTUDIANTE"

### Balcón (antes de los cambios):
1. **NO agregaba** el `default_query_system_prompt`
2. **Agregaba** system message con "ROL DEL USUARIO: ESTUDIANTE"
3. **Enviaba** `session_context` con información de carrera/facultad
4. **Normalizaba** el texto (quitaba tildes)

### Balcón (después de los cambios):
1. ✅ **NO agrega** system message con rol
2. ✅ **NO envía** `session_context`
3. ✅ **NO normaliza** el texto
4. ❌ **TODAVÍA NO AGREGA** el `default_query_system_prompt`

## Solución

Para que el balcón responda **exactamente igual** que el frontend directo, necesitamos:

1. ✅ Ya hecho: Eliminar normalización de texto
2. ✅ Ya hecho: Eliminar system message con rol
3. ✅ Ya hecho: Eliminar session_context
4. ⚠️ **FALTA**: Agregar el `default_query_system_prompt` como system message

## Código Relevante

### Frontend PrivateGPT (ui.py líneas 209-216):
```python
if self._system_prompt:
    all_messages.insert(
        0,
        ChatMessage(
            content=self._system_prompt,  # default_query_system_prompt
            role=MessageRole.SYSTEM,
        ),
    )
```

### System Prompt (settings-docker.yaml líneas 57-87):
```yaml
default_query_system_prompt: >
  Eres un asistente RAG. Debes responder exclusivamente con un JSON válido...
  
  FILTRADO CRITICO DE DOCUMENTOS (APLICAR ANTES DE GENERAR JSON):
  - Si recibes un contexto del sistema que especifica un ROL del usuario...
```

## Recomendación

Agregar el `default_query_system_prompt` al balcón para que sea idéntico al frontend directo.


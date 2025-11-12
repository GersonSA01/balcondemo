# Integración con PrivateGPT API

Este proyecto ahora usa **PrivateGPT** como servicio externo para manejar las consultas a documentos. El sistema RAG anterior ha sido reemplazado por llamadas a la API de PrivateGPT.

## 📋 Configuración

### 1. Ejecutar PrivateGPT como Servicio

PrivateGPT debe ejecutarse como un servicio separado (preferiblemente con Docker):

```bash
# Desde el directorio de private-gpt
docker-compose up -d

# O con un perfil específico
docker-compose --profile ollama-cpu up -d
docker-compose --profile gemini up -d
```

La API estará disponible en: `http://localhost:8001`

### 2. Configurar URL de PrivateGPT

Puedes configurar la URL de PrivateGPT de dos formas:

#### Opción A: Variable de entorno (Recomendado)

Crea un archivo `.env` en la raíz del proyecto:

```env
PRIVATEGPT_API_URL=http://localhost:8001
```

#### Opción B: Configuración Django

En `balcon/settings.py`:

```python
PRIVATEGPT_API_URL = os.getenv("PRIVATEGPT_API_URL", "http://localhost:8001")
```

### 3. Configurar CORS en PrivateGPT

Edita `settings.yaml` o `settings-docker.yaml` en PrivateGPT:

```yaml
server:
  port: 8001
  cors:
    enabled: true
    allow_origins: ["*"]  # O especifica tu dominio en producción
    allow_methods: ["*"]
    allow_headers: ["*"]
  auth:
    enabled: false  # Cambiar a true si necesitas autenticación
```

## 🔄 Flujo de Trabajo

1. **Ingestión de Documentos**: Los documentos PDF deben ser ingestionados en PrivateGPT antes de poder consultarlos. Esto se puede hacer:
   - Manualmente usando la API de PrivateGPT
   - Automáticamente cuando se sube un archivo desde el frontend

2. **Consulta de Chat**: Cuando el usuario envía un mensaje:
   - El frontend envía la solicitud a Django (`/api/chat/`)
   - Django llama a `classify_with_privategpt()` en `app/services/privategpt_chat_service.py`
   - Este servicio construye los mensajes y llama a PrivateGPT API
   - PrivateGPT busca en los documentos ingestionados y genera una respuesta
   - La respuesta se devuelve al frontend

## 📁 Estructura de Archivos

### Nuevos Archivos

- `app/services/privategpt_client.py`: Cliente HTTP para comunicarse con PrivateGPT API
- `app/services/privategpt_chat_service.py`: Servicio de chat que reemplaza al RAG anterior

### Archivos Modificados

- `app/views.py`: Ahora usa `classify_with_privategpt` en lugar de `classify_with_rag`
- `app/services/config.py`: Agregada configuración de `PRIVATEGPT_API_URL`
- `requirements.txt`: Agregada dependencia `requests`

### Archivos Movidos (RAG Legacy)

Los siguientes archivos del sistema RAG anterior fueron movidos a `app/services/rag_legacy/`:

- `rag_chat_service.py`
- `retriever.py`
- `pdf_responder.py`
- `answerability.py`
- `query_planner.py`
- `hierarchical_router.py`
- `deterministic_router.py`
- `json_retriever.py`
- `unified_brain.py`

### Archivos Mantenidos

Los siguientes servicios se mantienen porque aún son útiles:

- `handoff.py`: Lógica para derivar a agentes humanos
- `intent_parser.py`: Parser de intenciones del usuario
- `related_request_matcher.py`: Matching de solicitudes relacionadas
- `conversation_context.py`: Gestión de contexto conversacional
- `heuristic_judge.py`: Evaluación heurística
- `title_lexicon.py`: Léxico de títulos

## 🚀 Uso

### Comandos de Gestión

#### Verificar estado de PrivateGPT

```bash
python manage.py check_privategpt
```

Este comando verifica:
- ✅ Si PrivateGPT está disponible
- 📚 Lista los documentos ingestionados
- 📍 Muestra la URL configurada

#### Ingestionar documentos

**Ingestionar todos los PDFs en app/data/ (recursivo):**
```bash
python manage.py ingest_to_privategpt --recursive
```

**Ingestionar solo PDFs en carpetas de primer nivel:**
```bash
python manage.py ingest_to_privategpt
```

**Ingestionar un archivo específico:**
```bash
python manage.py ingest_to_privategpt --path legal_nacional/leyes_organicas/LOES.pdf
```

**Ingestionar todos los PDFs de una carpeta:**
```bash
python manage.py ingest_to_privategpt --path legal_nacional/leyes_organicas/
```

**Solo verificar conexión (sin ingestionar):**
```bash
python manage.py ingest_to_privategpt --check-only
```

### Uso Programático

#### Verificar que PrivateGPT esté disponible

```python
from app.services.privategpt_client import get_privategpt_client

client = get_privategpt_client()
if client.is_available():
    print("✅ PrivateGPT está disponible")
else:
    print("❌ PrivateGPT no está disponible")
```

#### Ingestionar un documento

```python
from app.services.privategpt_client import get_privategpt_client

client = get_privategpt_client()
result = client.ingest_file("ruta/al/documento.pdf")
print(result)
```

#### Hacer una consulta

El servicio de chat se usa automáticamente desde `views.py`, pero también puedes usarlo directamente:

```python
from app.services.privategpt_chat_service import classify_with_privategpt

result = classify_with_privategpt(
    user_text="¿Cuáles son los requisitos para cambio de paralelo?",
    conversation_history=[],
    category="Matriculación",
    subcategory="Cambio de paralelo",
    student_data={"credenciales": {"nombre_completo": "Juan Pérez"}}
)

print(result["summary"])
print(result["source_pdfs"])
```

## 🔧 Troubleshooting

### Error: "PrivateGPT no disponible"

1. Verifica que PrivateGPT esté ejecutándose:
   ```bash
   curl http://localhost:8001/health
   ```

2. Verifica la URL en la configuración:
   ```python
   from app.services.privategpt_client import PRIVATEGPT_API_URL
   print(PRIVATEGPT_API_URL)
   ```

3. Verifica los logs de PrivateGPT para ver si hay errores

### Error: "CORS policy"

Si ves errores de CORS, asegúrate de que PrivateGPT tenga CORS habilitado en su configuración (ver sección de configuración arriba).

### Error: "Timeout"

Si las consultas tardan mucho, puedes aumentar el timeout en `privategpt_client.py`:

```python
REQUEST_TIMEOUT = 60  # Aumentar de 30 a 60 segundos
```

## 📝 Notas

- PrivateGPT maneja internamente la búsqueda en documentos, embeddings, y generación de respuestas
- El sistema anterior de RAG (FAISS, LangChain, etc.) ya no se usa
- Los documentos deben estar ingestionados en PrivateGPT antes de poder consultarlos
- El frontend no necesita cambios, sigue funcionando igual

## 🔗 Referencias

- [Documentación de PrivateGPT](https://docs.privategpt.dev/)
- [API Reference](http://localhost:8001/docs) (cuando PrivateGPT esté ejecutándose)


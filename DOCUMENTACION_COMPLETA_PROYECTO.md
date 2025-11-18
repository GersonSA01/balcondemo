    # 📚 DOCUMENTACIÓN COMPLETA DEL PROYECTO BALCONDEMO

    ## 🎯 VISIÓN GENERAL

    **Balcondemo** es un sistema de asistente virtual inteligente para el Balcón de Servicios de UNEMI (Universidad Estatal de Milagro). El sistema combina:
    - **Clasificación de intenciones** usando modelos de machine learning entrenados
    - **RAG (Retrieval-Augmented Generation)** mediante PrivateGPT para respuestas informativas
    - **Gestión de solicitudes** relacionadas usando embeddings semánticos
    - **Handoff inteligente** a agentes humanos cuando es necesario
    - **Frontend interactivo** en Svelte con UI moderna

    ---

    ## 🏗️ ARQUITECTURA DEL PROYECTO

    ### Estructura de Directorios

    ```
    balcondemo/
    ├── app/                          # Aplicación Django principal
    │   ├── services/                 # Servicios de lógica de negocio
    │   ├── data/                     # Datos estáticos (JSON, modelos, PDFs)
    │   ├── models.py                 # Modelos Django (vacío actualmente)
    │   ├── views.py                  # Vistas/endpoints de la API
    │   ├── urls.py                   # Rutas de la aplicación
    │   └── management/commands/      # Comandos de gestión Django
    ├── balcon/                       # Configuración Django
    │   ├── settings.py               # Configuración del proyecto
    │   ├── urls.py                   # URLs raíz
    │   └── wsgi.py                   # WSGI para producción
    ├── frontend/                     # Frontend Svelte
    │   └── src/lib/                  # Componentes Svelte
    ├── models/                       # Modelos ML entrenados
    │   └── brain_hybrid.pkl         # Modelo híbrido de clasificación
    ├── scripts/                      # Scripts de utilidad
    └── requirements.txt              # Dependencias Python
    ```

    ---

    ## 🔧 COMPONENTES PRINCIPALES

    ### 1. **Backend Django (`app/`)**

    #### 1.1. **Vistas y Endpoints (`views.py`)**

    **Funcionalidad Principal:**
    - **`balcon_view`**: Renderiza la página principal HTML
    - **`chat_api`**: Endpoint principal `/api/chat/` que procesa mensajes del usuario
    - **`taxonomia_api`**: Endpoint `/api/taxonomia/` para obtener taxonomía de servicios
    - **`usuarios_api`**: Endpoint `/api/usuarios/` para listar usuarios disponibles
    - **`estudiante_api`**: Endpoint `/api/estudiante/` para obtener datos del estudiante
    - **`serve_pdf`**: Sirve archivos PDF desde `solicitudbalcon/`
    - **`limpiar_archivos_tmp_api`**: Limpia archivos temporales

    **Flujo de `chat_api`:**
    1. Recibe mensaje del usuario (texto o FormData con archivo)
    2. Carga datos del estudiante desde `data_unemi.json`
    3. Llama a `classify_with_privategpt()` (orquestador principal)
    4. Retorna respuesta JSON estructurada al frontend

    **Datos que maneja:**
    - `data_unemi.json`: Base de datos simulada con usuarios, perfiles, solicitudes
    - Carga datos por cédula y perfil_id
    - Soporta múltiples perfiles por usuario (estudiante, profesor, administrativo, etc.)

    ---

    #### 1.2. **Orquestador Principal (`services/privategpt_chat_service.py`)**

    **Archivo más importante del sistema** - Coordina todo el flujo de conversación.

    **Funciones Principales:**

    ##### `classify_with_privategpt()`
    **Función central que orquesta todo el flujo:**

    1. **Detección de Saludo**
    - Si es saludo → `_handle_greeting()` → retorna saludo personalizado

    2. **Recuperación de Contexto**
    - Recupera `requirements` (requerimientos multi-intento) del historial
    - Verifica si están "done" y los limpia si es necesario
    - Detecta stage de conversación usando `ChatContext.from_history()`

    3. **Procesamiento de Confirmaciones**
    - Si `confirmed=True/False` (botón) → `_handle_confirmation_stage()`
    - Si `confirmed=None` (texto libre) → continúa con flujo normal

    4. **Detección de Nuevo Intent**
    - Compara nueva intención con intención anterior dinámicamente
    - Si son diferentes → limpia requirements y trata como nuevo intento
    - Si son iguales → continúa con contexto anterior

    5. **Interpretación de Intención**
    - Llama a `interpretar_intencion_principal()` (LLM Gemini)
    - Extrae: `intent_short`, `accion`, `objeto`, `answer_type`, `needs_confirmation`
    - Detecta múltiples intenciones (`multi_intent`)

    6. **Clasificación con BrainEngine**
    - Llama a `_ensure_slot_has_classification()`
    - Clasifica: `category`, `subcategory`, `department`
    - Usa modelo entrenado (`brain_hybrid.pkl`)

    7. **Manejo de Stages**
    - `AWAIT_INTENT`: Nueva intención → pide confirmación
    - `AWAIT_CONFIRM`: Esperando confirmación → procesa confirmación
    - `AWAIT_RELATED_REQUEST`: Esperando selección de solicitud relacionada
    - `AWAIT_HANDOFF_DETAILS`: Esperando detalles para handoff
    - `ANSWER_READY`: Respuesta lista

    8. **Flujo según `answer_type`:**
    - **`informativo`**: Busca solicitudes relacionadas → PrivateGPT API
    - **`operativo`**: Evalúa cronograma (si es retiro) → Handoff

    ##### `_handle_confirmation_stage()`
    **Maneja cuando el usuario confirma:**

    1. Recupera `original_user_message` del historial (evitando confirmaciones "Sí"/"No")
    2. Resuelve `answer_type` desde `intent_slots`
    3. Delega a:
    - `_handle_confirmation_informative()` si es informativo
    - `_handle_confirmation_operative()` si es operativo

    ##### `_handle_confirmation_informative()`
    **Flujo para intenciones informativas:**

    1. Busca solicitudes relacionadas con `find_related_requests()`
    2. Si hay solicitudes relacionadas:
    - Muestra opciones al usuario para relacionar
    - Espera selección o "continuar sin relacionar"
    3. Si no hay o después de seleccionar:
    - Llama a `call_privategpt_api()` con mensaje confirmado
    - Recibe respuesta con `has_information` y `fuentes`
    - Si `has_information=True` → retorna respuesta con fuentes
    - Si `has_information=False` → handoff

    ##### `_handle_confirmation_operative()`
    **Flujo para intenciones operativas:**

    1. Detecta si es "retiro de asignatura"
    2. Si es retiro:
    - Evalúa cronograma con `evaluar_cronograma_retiro()`
    - Si está dentro del cronograma → handoff con detalles
    - Si está fuera → informa fechas y cierra
    3. Si no es retiro:
    - Handoff directo con `determinar_departamento_handoff()`

    ##### `_ensure_slot_has_classification()`
    **Inyecta clasificación del BrainEngine en los slots:**

    1. Llama a `classify_user_intent_hybrid()` (BrainEngine)
    2. Obtiene: `category`, `subcategory`, `department`, `confidence`
    3. Actualiza slots incluso si confianza es baja (si no es "OTROS")
    4. Guarda en `slot["classification_from_logs"]`

    **Características:**
    - Usa valores predichos aunque no superen threshold (0.65)
    - Solo ignora si predice "OTROS"
    - Permite clasificación con confianza baja pero válida

    ---

    #### 1.3. **Clasificador de Intenciones (`services/intent_classifier_trained.py`)**

    **BrainEngine - Modelo Híbrido de Clasificación**

    **Clase `BrainEngine`:**
    - **Singleton**: Se carga una vez y se reutiliza
    - **Componentes:**
    - 3 clasificadores (categoría, subcategoría, departamento)
    - Modelo de embeddings (`sentence-transformers`)
    - Knowledge base de FAQs (deshabilitada actualmente)

    **Método `predict()`:**
    1. **Clasificación de Categoría**
    - Genera embedding del texto
    - Clasifica con modelo entrenado
    - Threshold: 0.65
    - Si no supera pero no es "OTROS" → asigna igual

    2. **Clasificación de Subcategoría**
    - Similar a categoría
    - Usa embedding y modelo específico

    3. **Clasificación de Departamento**
    - Similar a categoría y subcategoría
    - Retorna departamento sugerido

    **Función `classify_user_intent_hybrid()`:**
    - Wrapper que obtiene instancia singleton de `BrainEngine`
    - Llama a `predict()` con `answer_type` (para bloquear FAQ si es operativo)
    - Retorna diccionario con clasificaciones

    **Características:**
    - ✅ FAQ eliminado completamente
    - ✅ Solo clasifica (category, subcategory, department)
    - ✅ Usa modelo entrenado en logs históricos de solicitudes
    - ✅ Modelo: `brain_hybrid.pkl` (LogisticRegression + embeddings)

    ---

    #### 1.4. **Parser de Intenciones (`services/intent_parser.py`)**

    **Interpreta la intención del usuario usando LLM Gemini**

    **Función `interpretar_intención_principal()`:**
    - Usa LLM Gemini (`gemini-2.5-flash`) con prompt estructurado
    - Extrae información estructurada:
    - `intent_short`: Resumen de 12-16 palabras
    - `intent_code`: Código de intención específica
    - `accion`: Verbo principal (consultar, solicitar, cambiar, etc.)
    - `objeto`: Qué cosa (nota, materia, certificado, etc.)
    - `asignatura`, `periodo`, `carrera`, etc.: Campos específicos
    - `answer_type`: "informativo" o "operativo"
    - `needs_confirmation`: Si necesita confirmación
    - `confirm_text`: Texto de confirmación
    - `multi_intent`: Si hay múltiples intenciones
    - `intents`: Lista de intenciones si `multi_intent=True`

    **Rate Limiting:**
    - Usa `guarded_invoke()` para proteger contra límites de API
    - Token bucket: 9 requests por minuto
    - Maneja errores 429 con reintentos

    **Características:**
    - ✅ Detecta múltiples intenciones en un solo mensaje
    - ✅ Genera texto de confirmación natural
    - ✅ Clasifica `answer_type` automáticamente
    - ✅ Extrae campos estructurados para contexto

    ---

    #### 1.5. **Buscador de Solicitudes Relacionadas (`services/related_request_matcher.py`)**

    **Encuentra solicitudes previas similares usando embeddings semánticos**

    **Función `find_related_requests()`:**
    1. **Carga Solicitudes del Estudiante**
    - Llama a `load_student_requests()` desde `data_unemi.json`
    - Filtra por estudiante y ordena por fecha (más recientes primero)
    - Tope: 150 solicitudes recientes

    2. **Enriquecimiento de Consulta**
    - Combina `user_request` con `detalle_libre` de `intent_slots`
    - Normaliza texto para embeddings

    3. **Ranking Semántico**
    - Usa `BrainEngine` para generar embeddings
    - Calcula similitud coseno entre consulta y solicitudes
    - Filtra por umbral mínimo: 0.40
    - Selecciona top-K candidatas (máximo 30)

    4. **Selección Final**
    - Si hay candidatas → retorna top 3
    - Si no hay → retorna `no_related=True`

    **Función `build_text_for_embedding()`:**
    - Construye texto rico semánticamente de una solicitud
    - Combina: descripción, servicio, historial, categoría, subcategoría
    - Normaliza para mejorar matching

    **Características:**
    - ✅ Usa embeddings semánticos (no keywords)
    - ✅ Reutiliza `BrainEngine` (no carga modelo duplicado)
    - ✅ Prioriza solicitudes recientes
    - ✅ Filtra por similitud mínima

    ---

    #### 1.6. **Servicio de PrivateGPT (`services/privategpt_service.py`)**

    **Comunica con PrivateGPT API para RAG**

    **Función `call_privategpt_api()`:**
    1. **Construye Mensaje para PrivateGPT**
    - Si hay solicitud relacionada seleccionada → enriquece contexto
    - Agrega información del estudiante (rol, perfil)
    - Construye historial de conversación

    2. **Llamada a PrivateGPT**
    - Usa `get_privategpt_client()` para obtener cliente HTTP
    - POST a `/v1/chat/completions`
    - Parámetros:
        - `use_context: true`
        - `include_sources: true`
        - `context_filter`: IDs de documentos UNEMI prioritarios

    3. **Procesamiento de Respuesta**
    - Usa `PrivateGPTResponseParser` para parsear JSON
    - Extrae: `has_information`, `response`, `fuentes`
    - Agrupa fuentes por archivo con `agrupar_fuentes_por_archivo()`

    **Función `agrupar_fuentes_por_archivo()`:**
    - Agrupa fuentes duplicadas por archivo
    - Consolida páginas: `[{"archivo": "X.pdf", "paginas": ["1", "2"]}]`
    - Ordena páginas numéricamente

    **Características:**
    - ✅ Prioriza documentos UNEMI sobre otros
    - ✅ Filtra por rol del usuario (estudiante, profesor, etc.)
    - ✅ Agrupa fuentes para presentación limpia
    - ✅ Maneja errores y timeouts

    ---

    #### 1.7. **Servicio de Handoff (`services/handoff_service.py`)**

    **Maneja derivación a agentes humanos**

    **Función `determinar_departamento_handoff()`:**
    **Prioridad para determinar departamento:**
    1. `department_from_logs` (modelo entrenado) si confianza >= 0.7
    2. Desde categoría/subcategoría usando `get_departamento_real()`
    3. Heurísticas desde `classify_with_heuristics()`
    4. Por defecto: "DIRECCIÓN DE GESTIÓN Y SERVICIOS ACADÉMICOS"

    **Función `build_handoff_response()`:**
    - Construye mensaje de handoff personalizado
    - Incluye nombre del estudiante
    - Pide detalles y archivo PDF si `needs_handoff_details=True`
    - Usa `build_handoff_response_new()` internamente

    **Función `process_handoff_details()`:**
    - Procesa cuando usuario envía detalles y archivo
    - Crea solicitud con `crear_solicitud()`
    - Retorna confirmación de envío

    **Características:**
    - ✅ Determina departamento inteligentemente
    - ✅ Pide detalles adicionales si es necesario
    - ✅ Crea solicitud en sistema
    - ✅ Mensajes personalizados

    ---

    #### 1.8. **Servicio de Cronograma (`services/cronograma_service.py`)**

    **Evalúa cronogramas de retiro de asignaturas**

    **Función `evaluar_cronograma_retiro()`:**
    1. **Carga Cronograma**
    - Lee `cronograma_retiros.json`
    - Cachea en memoria para performance

    2. **Filtra Eventos**
    - Busca eventos de tipo "RETIRO_DEFINITIVO" y "RETIRO_FUERZA_MAYOR"
    - Prioriza por periodo académico del estudiante
    - Si no hay periodo → busca más cercano a fecha actual

    3. **Evalúa Estado**
    - Compara fecha actual con ventanas de retiro
    - Estados posibles:
        - `DENTRO_CRONOGRAMA`: Dentro de alguna ventana
        - `FUERA_DE_CRONOGRAMA`: Fuera de todas las ventanas
        - `PROXIMAMENTE`: Próximo a iniciar (dentro de 7 días)

    4. **Retorna Información**
    - Estado actual
    - Fechas de ventanas disponibles
    - Mensaje informativo

    **Características:**
    - ✅ Cachea cronograma en memoria
    - ✅ Maneja múltiples periodos académicos
    - ✅ Evalúa estado actual vs. cronograma
    - ✅ Informa fechas disponibles

    ---

    #### 1.9. **Gestión de Requirements (`services/requirements_service.py`)**

    **Maneja requerimientos multi-intento**

    **Función `get_requirements_from_history()`:**
    - Recupera `requirements` y `current_requirement_index` del historial
    - Busca en `meta.extra.requirements` de mensajes del bot
    - **Verifica si están "done"**:
    - Si todos están "done" → limpia requirements (retorna lista vacía)
    - Si el actual está "done" → busca siguiente pendiente
    - Si no hay pendientes → limpia requirements

    **Función `propagate_requirements_to_response()`:**
    - Propaga requirements a respuesta
    - Guarda en `extra.requirements` y `meta.extra.requirements`
    - Asegura persistencia en historial

    **Función `finish_requirement_and_maybe_next()`:**
    - Marca requirement actual como "done"
    - Si hay más pendientes → muestra menú de opciones
    - Si no hay más → limpia requirements

    **Características:**
    - ✅ Detecta requirements completados automáticamente
    - ✅ Limpia contexto cuando todos están "done"
    - ✅ Soporta múltiples requerimientos en cola
    - ✅ Menú para navegar entre requerimientos

    ---

    #### 1.10. **Dominio de Conversación (`services/chat_domain.py`)**

    **Define estructuras de datos y recuperación de contexto**

    **Clase `Requirement`:**
    - Representa un requerimiento individual
    - Campos: `id`, `summary`, `slots`, `answer_type`, `status`

    **Clase `ChatContext`:**
    - Representa el contexto completo de la conversación
    - Campos:
    - `stage`: Estado actual (AWAIT_INTENT, AWAIT_CONFIRM, etc.)
    - `pending_slots`: Slots pendientes de confirmación
    - `handoff_channel`: Canal de handoff
    - `requirements`: Lista de requerimientos
    - `current_requirement_index`: Índice del requerimiento actual

    **Método `from_history()`:**
    - Reconstruye contexto desde historial de mensajes
    - **Prioriza mensajes con requirements "done"** sobre confirmaciones pendientes
    - Detecta si último mensaje es respuesta completa (`has_information=True`)
    - Si todos los requirements están "done" → no establece `AWAIT_CONFIRM`

    **Método `is_new_intent()`:**
    - Detecta si un mensaje es nuevo intento
    - Compara con mensajes anteriores
    - Ignora confirmaciones simples

    **Características:**
    - ✅ Recupera contexto completo desde historial
    - ✅ Detecta stage correctamente
    - ✅ Prioriza mensajes finales sobre confirmaciones
    - ✅ Maneja requirements multi-intento

    ---

    #### 1.11. **Constructor de Respuestas (`services/response_builder.py`)**

    **Centraliza construcción de respuestas al frontend**

    **Función `build_message_object()`:**
    - Crea objeto de mensaje estructurado
    - Campos: `who`, `text`, `type`, `buttons`, `meta`
    - Usado para mensajes generados desde backend

    **Función `build_button_object()`:**
    - Crea objeto de botón estructurado
    - Campos: `id`, `label`, `action`, `style`
    - Usado para botones interactivos

    **Función `build_frontend_response()`:**
    - Construye respuesta estándar al frontend
    - Parámetros:
    - `stage`, `mode`, `status`: Estados de conversación
    - `messages`: Array de mensajes estructurados
    - `thinking_status`: Mensaje de estado único
    - `thinking_status_alternate`: Array de mensajes para alternar
    - `intent_slots`, `extra`, etc.: Metadata

    **Función `build_informative_answer_response()`:**
    - Construye respuesta informativa con fuentes
    - Stage: `ANSWER_READY`
    - Incluye: `has_information=True`, `fuentes`, `source_pdfs`

    **Función `build_need_confirm_response()`:**
    - Construye respuesta de confirmación
    - Incluye mensaje estructurado con botones
    - Stage: `AWAIT_CONFIRM`

    **Función `build_handoff_response_new()`:**
    - Construye respuesta de handoff
    - Stage: `AWAIT_HANDOFF_DETAILS` o `ANSWER_READY`
    - Incluye información de departamento

    **Características:**
    - ✅ Todos los mensajes generados desde backend
    - ✅ Estructura consistente para frontend
    - ✅ Soporte para mensajes alternados (PrivateGPT)
    - ✅ Botones estructurados

    ---

    #### 1.12. **Servicio de Saludos (`services/greeting_service.py`)**

    **Genera saludos personalizados por subcategoría**

    **Función `build_greeting_message()`:**
    - Genera saludo estructurado desde backend
    - Parámetros: `student_data`, `category`, `subcategory`
    - Busca saludo específico por subcategoría
    - Si no encuentra → usa saludo genérico
    - Retorna mensaje estructurado con `build_message_object()`

    **Diccionario `greetings_by_category`:**
    - Contiene saludos personalizados por subcategoría
    - Maneja múltiples variantes de categoría (mayúsculas, minúsculas)
    - Fallback a saludos genéricos

    **Características:**
    - ✅ Saludos personalizados por subcategoría
    - ✅ Incluye nombre del estudiante
    - ✅ Mensajes estructurados desde backend
    - ✅ Fallback a saludos genéricos

    ---

    #### 1.13. **Servicio de Datos del Estudiante (`services/student_data_service.py`)**

    **Responde consultas usando datos del estudiante directamente**

    **Función `maybe_answer_with_student_data()`:**
    - Detecta si la consulta puede responderse con datos del estudiante
    - Tipos de consultas:
    - `consultar_solicitudes_balcon`: Lista solicitudes del balcón
    - `consultar_datos_personales`: Nombre, email, etc.
    - `consultar_carrera_actual`: Carrera actual del estudiante
    - `consultar_roles_usuario`: Perfiles/roles del usuario
    - Si encuentra respuesta → retorna directamente sin llamar a PrivateGPT

    **Características:**
    - ✅ Respuestas rápidas sin LLM
    - ✅ Usa datos de `data_unemi.json`
    - ✅ Detecta tipos de consulta específicos
    - ✅ Optimiza performance

    ---

    #### 1.14. **Cliente PrivateGPT (`services/privategpt_client.py`)**

    **Cliente HTTP para comunicarse con PrivateGPT API**

    **Función `get_privategpt_client()`:**
    - Obtiene cliente HTTP reutilizable
    - Configura URL desde `PRIVATEGPT_API_URL` (default: `http://localhost:8001`)
    - Maneja conexiones persistentes

    **Características:**
    - ✅ Cliente HTTP reutilizable
    - ✅ Configuración centralizada
    - ✅ Manejo de errores y timeouts

    ---

    #### 1.15. **Parser de Respuestas PrivateGPT (`services/privategpt_response_parser.py`)**

    **Parsea respuestas JSON de PrivateGPT**

    **Clase `PrivateGPTResponseParser`:**
    - Parsea JSON de respuesta de PrivateGPT
    - Extrae: `has_information`, `response`, `fuentes`
    - Valida estructura
    - Maneja errores de parsing

    **Características:**
    - ✅ Parsing robusto de JSON
    - ✅ Validación de estructura
    - ✅ Manejo de errores

    ---

    #### 1.16. **Tipos de Conversación (`services/conversation_types.py`)**

    **Define enums para estados de conversación**

    **`ConversationStage`:**
    - `GREETING`: Mostrando saludo
    - `AWAIT_INTENT`: Esperando nueva intención
    - `AWAIT_CONFIRM`: Esperando confirmación
    - `AWAIT_RELATED_REQUEST`: Esperando selección de solicitud relacionada
    - `AWAIT_HANDOFF_DETAILS`: Esperando detalles para handoff
    - `ANSWER_READY`: Respuesta lista

    **`ConversationMode`:**
    - `INFORMATIVE`: Modo informativo (RAG)
    - `OPERATIVE`: Modo operativo (handoff)
    - `HANDOFF`: Modo handoff activo

    **`ConversationStatus`:**
    - `ANSWER`: Respuesta lista
    - `NEED_DETAILS`: Necesita detalles/confirmación
    - `HANDOFF`: Derivación a humano
    - `ERROR`: Error técnico

    ---

    #### 1.17. **Configuración (`services/config.py`)**

    **Configuración central y cliente LLM**

    **Configuración:**
    - `GOOGLE_API_KEY`: API key de Gemini (desde env o .env)
    - `PRIVATEGPT_API_URL`: URL de PrivateGPT (default: `http://localhost:8001`)
    - `LLM_FREE_TIER`: Flag para modo free tier (limita uso de LLM)

    **Cliente LLM:**
    - `llm`: Cliente Gemini (`gemini-2.5-flash`)
    - Temperature: 0 (determinístico)

    **Rate Limiting:**
    - Token bucket: 9 requests por minuto
    - `guarded_invoke()`: Protege contra límites de API
    - Maneja errores 429 con reintentos

    **Funciones de Encriptación:**
    - `encrypt()`: Encripta IDs (base64)
    - `decrypt()`: Desencripta IDs

    **Características:**
    - ✅ Configuración centralizada
    - ✅ Rate limiting robusto
    - ✅ Manejo de errores 429
    - ✅ Encriptación simple de IDs

    ---

    #### 1.18. **Servicio de Solicitudes (`services/solicitud_service.py`)**

    **Crea y gestiona solicitudes en el sistema**

    **Función `crear_solicitud()`:**
    - Crea solicitud en el sistema
    - Guarda PDF en `solicitudbalcon/`
    - Genera código único
    - Retorna información de solicitud creada

    **Función `obtener_solicitudes_usuario()`:**
    - Obtiene solicitudes del usuario desde `data_unemi.json`
    - Filtra por usuario y perfil
    - Retorna lista de solicitudes

    **Función `obtener_historial_solicitud()`:**
    - Obtiene historial de una solicitud específica
    - Incluye estados, observaciones, etc.

    **Características:**
    - ✅ Crea solicitudes con PDFs
    - ✅ Genera códigos únicos
    - ✅ Integra con datos de `data_unemi.json`

    ---

    ### 2. **Frontend Svelte (`frontend/`)**

    #### 2.1. **Componente Principal (`src/lib/ChatbotInline.svelte`)**

    **Componente de chat interactivo**

    **Funcionalidades Principales:**

    ##### Estado del Componente
    - `messages`: Array de mensajes de la conversación
    - `input`: Texto del input del usuario
    - `sending`: Flag de envío en progreso
    - `currentCategory`, `currentSubcategory`: Categoría actual
    - `studentData`: Datos del estudiante
    - `needsConfirmation`: Si necesita confirmación
    - `needsRelatedRequestSelection`: Si necesita seleccionar solicitud relacionada
    - `thinkingStatus`: Mensaje de estado dinámico
    - `thinkingStatusAlternate`: Array de mensajes para alternar

    ##### Función `send()`
    **Envía mensaje del usuario:**
    1. Valida input
    2. Prepara payload con:
    - `text`: Mensaje del usuario
    - `category`, `subcategory`: Categorías actuales
    - `confirmed`: Boolean si es click en botón
    - `related_request_id`: ID de solicitud relacionada si aplica
    - `file`: Archivo si hay uno seleccionado
    3. POST a `/api/chat/`
    4. Procesa respuesta con `processChatResponse()`

    ##### Función `processChatResponse()`
    **Procesa respuesta del backend:**
    1. **Prioriza `data.messages`** (array estructurado)
    - Si existe → itera y agrega mensajes
    - Extrae botones de `message.buttons`
    - Extrae flags de `message.meta`
    2. Si no hay `messages` → crea mensaje desde `data.response`
    3. Actualiza estado:
    - `needsConfirmation`, `needsRelatedRequestSelection`, etc.
    - `thinkingStatus` o `thinkingStatusAlternate`
    4. Actualiza header con clasificación
    5. Maneja archivos y handoff

    ##### Función `handleButtonClick()`
    **Maneja clicks en botones estructurados:**
    1. Determina acción según `button.action` o `button.id`
    2. Mapea a `confirmed: true/false` según tipo
    3. Envía request con `confirmed` booleano
    4. No usa keywords, solo valores booleanos

    ##### Función `startThinkingStatusAlternate()`
    **Alterna mensajes de estado:**
    - Recibe array de mensajes
    - Alterna entre ellos cada 2 segundos
    - Usado para PrivateGPT ("Buscando documentos" / "Pensando en una mejor respuesta")
    - Se detiene cuando llega respuesta final

    ##### Renderizado
    - Renderiza mensajes desde `messages` array
    - Renderiza botones dinámicamente desde `message.buttons`
    - Muestra `thinkingStatus` cuando está activo
    - Input de archivo para handoff
    - Header con categoría/subcategoría/departamento

    **Características:**
    - ✅ Renderiza solo lo que recibe del backend
    - ✅ Botones dinámicos desde backend
    - ✅ Mensajes de estado alternados
    - ✅ Manejo de archivos
    - ✅ UI moderna y responsive

    ---

    ### 3. **Datos (`app/data/`)**

    #### 3.1. **`data_unemi.json`**
    **Base de datos simulada de usuarios y solicitudes:**
    - Estructura: `{cedula: {persona, perfiles, solicitudes_balcon, ...}}`
    - Contiene: usuarios, perfiles, solicitudes históricas
    - Usado para: cargar datos del estudiante, buscar solicitudes relacionadas

    #### 3.2. **`cronograma_retiros.json`**
    **Cronogramas de retiro de asignaturas:**
    - Lista de eventos con fechas de inicio/fin
    - Tipos: "RETIRO_DEFINITIVO", "RETIRO_FUERZA_MAYOR"
    - Usado para evaluar si está dentro del cronograma

    #### 3.3. **`taxonomia.json`**
    **Taxonomía de servicios del balcón:**
    - Categorías, subcategorías, procesos
    - Usado para mostrar opciones al usuario

    #### 3.4. **Modelos ML (`models/brain_hybrid.pkl`)**
    **Modelo entrenado de clasificación:**
    - Contiene: clasificadores, encoders, knowledge base
    - Usado por `BrainEngine` para clasificar intenciones

    ---

    ## 🔄 FLUJO COMPLETO DEL SISTEMA

    ### Flujo Típico de una Consulta Informativa

    1. **Usuario envía mensaje** → Frontend llama `/api/chat/`
    2. **Backend recibe** → `chat_api()` en `views.py`
    3. **Carga datos** → `_load_student_data_from_unemi()`
    4. **Orquestador** → `classify_with_privategpt()`
    5. **Detecta saludo** → Si es saludo → `_handle_greeting()` → retorna
    6. **Interpreta intención** → `interpretar_intencion_principal()` (LLM)
    7. **Clasifica** → `_ensure_slot_has_classification()` (BrainEngine)
    8. **Pide confirmación** → Si `needs_confirmation=True` → retorna con botones
    9. **Usuario confirma** → `_handle_confirmation_stage()`
    10. **Busca relacionadas** → `find_related_requests()` (embeddings)
    11. **Muestra opciones** → Si hay relacionadas → espera selección
    12. **Llama PrivateGPT** → `call_privategpt_api()` con mensaje confirmado
    13. **Recibe respuesta** → `has_information`, `response`, `fuentes`
    14. **Retorna al frontend** → Respuesta estructurada con mensajes y botones
    15. **Frontend renderiza** → Muestra respuesta, fuentes, botones

    ### Flujo Típico de una Solicitud Operativa

    1-8. **Igual que informativo**
    9. **Usuario confirma** → `_handle_confirmation_operative()`
    10. **Evalúa cronograma** → Si es retiro → `evaluar_cronograma_retiro()`
    11. **Determina departamento** → `determinar_departamento_handoff()`
    12. **Pide detalles** → `build_handoff_response()` con `needs_handoff_details=True`
    13. **Usuario envía detalles + PDF** → `process_handoff_details()`
    14. **Crea solicitud** → `crear_solicitud()` → guarda PDF
    15. **Confirma envío** → Retorna confirmación

    ---

    ## 🧠 DETECCIÓN DINÁMICA DE INTENCIONES

    **Sistema implementado para detectar si usar contexto o no:**

    1. **Comparación de Intenciones**
    - Compara `accion` y `objeto` de nueva intención vs. requirement anterior
    - Si coinciden → misma intención → usa contexto
    - Si difieren → nueva intención → limpia contexto

    2. **Fallback por Palabras**
    - Si no hay `accion`/`objeto` → compara palabras significativas en `intent_short`
    - Si comparten >= 2 palabras significativas (>3 caracteres) → misma intención

    3. **Limpieza Automática**
    - Si requirement está "done" → limpia automáticamente
    - Si nueva intención es diferente → limpia requirements

    **Características:**
    - ✅ No usa keywords
    - ✅ Comparación semántica de intenciones
    - ✅ Limpieza automática de contexto
    - ✅ Detección dinámica sin reglas fijas

    ---

    ## 📊 MENSAJES DE ESTADO

    **Sistema de mensajes de estado desde backend:**

    1. **Mensajes Únicos**
    - `thinking_status`: Un mensaje fijo ("Analizando solicitudes anteriores")
    - Se muestra mientras se procesa

    2. **Mensajes Alternados**
    - `thinking_status_alternate`: Array de mensajes
    - Frontend alterna entre ellos cada 2 segundos
    - Usado para PrivateGPT: ["Buscando documentos", "Pensando en una mejor respuesta"]

    3. **Limpieza**
    - Antes de establecer `thinking_status_alternate` → limpia `thinking_status`
    - Evita conflictos y superposiciones

    **Características:**
    - ✅ Todos los mensajes desde backend
    - ✅ Alternancia suave en frontend
    - ✅ Sin conflictos entre mensajes
    - ✅ Mensajes específicos por etapa

    ---

    ## 🔐 SEGURIDAD Y CONFIGURACIÓN

    ### Variables de Entorno
    - `GOOGLE_API_KEY`: API key de Gemini
    - `PRIVATEGPT_API_URL`: URL de PrivateGPT (default: `http://localhost:8001`)
    - `LLM_FREE_TIER`: Flag para modo free tier

    ### Rate Limiting
    - **Token bucket**: 9 requests por minuto
    - **Protección**: `guarded_invoke()` maneja límites de API
    - **Reintentos**: Hasta 2 reintentos con espera automática

    ### Encriptación
    - IDs encriptados con base64 (simulación)
    - Funciones: `encrypt()`, `decrypt()`

    ---

    ## 📦 DEPENDENCIAS PRINCIPALES

    ### Backend
    - **Django 4.2.25**: Framework web
    - **langchain-google-genai**: Cliente Gemini
    - **sentence-transformers**: Embeddings semánticos
    - **scikit-learn**: Modelos ML
    - **numpy, pandas**: Procesamiento de datos
    - **httpx**: Cliente HTTP para PrivateGPT

    ### Frontend
    - **Svelte**: Framework frontend
    - **Vite**: Build tool
    - **SvelteStrap**: Componentes UI

    ---

    ## 🚀 COMANDOS DE GESTIÓN

    ### `ingest_to_privategpt`
    - Ingestiona documentos a PrivateGPT
    - Carga PDFs desde `app/data/`
    - Genera embeddings y los indexa

    ### `check_privategpt`
    - Verifica estado de PrivateGPT
    - Comprueba conexión y salud del servicio

    ### `build_policy_index`
    - Construye índice de políticas
    - Procesa documentos legales

    ---

    ## 📝 ARCHIVOS DE DATOS

    ### `data_unemi.json`
    - Base de datos simulada
    - Estructura: `{cedula: {persona, perfiles, solicitudes_balcon}}`
    - Usado para: usuarios, perfiles, solicitudes

    ### `cronograma_retiros.json`
    - Cronogramas de retiro
    - Eventos con fechas de inicio/fin
    - Usado para evaluar disponibilidad

    ### `taxonomia.json`
    - Taxonomía de servicios
    - Categorías, subcategorías, procesos
    - Usado para mostrar opciones

    ### `solicitudes_balcon_dump.jsonl`
    - Dump de solicitudes históricas
    - Usado para entrenar modelo de clasificación
    - Formato JSONL (una línea por solicitud)

    ---

    ## 🎯 CARACTERÍSTICAS DESTACADAS

    1. **Clasificación Híbrida**
    - Modelo ML entrenado en logs históricos
    - Clasifica: categoría, subcategoría, departamento
    - Usa embeddings semánticos

    2. **RAG con PrivateGPT**
    - Respuestas informativas desde documentos
    - Filtrado por rol del usuario
    - Priorización de documentos UNEMI

    3. **Solicitudes Relacionadas**
    - Encuentra solicitudes previas similares
    - Usa embeddings semánticos
    - Permite relacionar solicitudes nuevas con anteriores

    4. **Handoff Inteligente**
    - Determina departamento automáticamente
    - Pide detalles adicionales si es necesario
    - Crea solicitudes en el sistema

    5. **Multi-Intento**
    - Detecta múltiples requerimientos en un mensaje
    - Maneja cola de requerimientos
    - Navegación entre requerimientos

    6. **Detección Dinámica**
    - Compara intenciones para decidir usar contexto
    - Limpia contexto automáticamente
    - No depende de keywords

    7. **Mensajes Estructurados**
    - Todos los mensajes desde backend
    - Botones dinámicos
    - Mensajes de estado alternados

    ---

    ## 🔄 FLUJOS ESPECÍFICOS

    ### Flujo de Retiro de Asignatura
    1. Usuario: "necesito retirar una materia"
    2. Sistema: Clasifica como operativo
    3. Sistema: Pide confirmación
    4. Usuario: Confirma
    5. Sistema: Evalúa cronograma
    6. Si dentro → Handoff con detalles
    7. Si fuera → Informa fechas y cierra

    ### Flujo de Consulta Informativa
    1. Usuario: "cuando son los examenes"
    2. Sistema: Clasifica como informativo
    3. Sistema: Pide confirmación
    4. Usuario: Confirma
    5. Sistema: Busca solicitudes relacionadas
    6. Sistema: Llama PrivateGPT
    7. Sistema: Retorna respuesta con fuentes

    ### Flujo de Solicitud Relacionada
    1. Usuario: Confirma intención
    2. Sistema: Busca solicitudes relacionadas (embeddings)
    3. Sistema: Muestra opciones al usuario
    4. Usuario: Selecciona solicitud o "continuar sin relacionar"
    5. Sistema: Si selecciona → enriquece contexto para PrivateGPT
    6. Sistema: Llama PrivateGPT con contexto enriquecido

    ---

    ## 🛠️ TECNOLOGÍAS Y HERRAMIENTAS

    ### Machine Learning
    - **scikit-learn**: Clasificadores (LogisticRegression)
    - **sentence-transformers**: Embeddings semánticos
    - **numpy**: Procesamiento numérico

    ### LLM
    - **Google Gemini 2.5 Flash**: Interpretación de intenciones
    - **PrivateGPT**: RAG para respuestas informativas

    ### Backend
    - **Django**: Framework web
    - **LangChain**: Integración con LLMs

    ### Frontend
    - **Svelte**: Framework reactivo
    - **Vite**: Build tool
    - **SvelteStrap**: Componentes UI

    ---

    ## 📈 OPTIMIZACIONES

    1. **Singleton Pattern**
    - `BrainEngine` se carga una vez
    - Reutilizado en todas las llamadas
    - Ahorra ~400MB de RAM

    2. **Caché de Cronograma**
    - Cronograma cacheado en memoria
    - Thread-safe con locks

    3. **Rate Limiting**
    - Token bucket para proteger API
    - Reintentos automáticos

    4. **Limpieza de Contexto**
    - Detecta requirements "done" automáticamente
    - Limpia contexto cuando es necesario
    - Evita usar mensajes anteriores incorrectamente

    ---

    ## 🎨 INTERFAZ DE USUARIO

    ### Componentes Frontend
    - **ChatbotInline.svelte**: Componente principal de chat
    - **Header dinámico**: Muestra categoría/subcategoría/departamento
    - **Botones interactivos**: Generados desde backend
    - **Mensajes de estado**: Alternados para PrivateGPT
    - **Input de archivo**: Para handoff

    ### Características UI
    - ✅ Diseño moderno y responsive
    - ✅ Mensajes estructurados
    - ✅ Botones dinámicos
    - ✅ Estados de carga
    - ✅ Animaciones suaves

    ---

    ## 🔍 DEBUGGING Y LOGS

    ### Prints de Debug
    - Todos los servicios tienen prints detallados
    - Formato: `🔍 [Servicio] Mensaje`
    - Incluyen datos relevantes para debugging

    ### Logs Principales
    - `[classify_with_privategpt]`: Flujo principal
    - `[BrainService]`: Clasificación
    - `[Intent Parser]`: Interpretación de intención
    - `[PrivateGPT]`: Llamadas a PrivateGPT
    - `[Handoff]`: Procesamiento de handoff
    - `[Requirements]`: Gestión de requirements

    ---

    ## 📚 ARCHIVOS DE DOCUMENTACIÓN

    - `ANALISIS_BALCON_SERVICIOS_COMPLETO.md`: Análisis del sistema
    - `FLUJO_COMPLETO_BALCON_SERVICIOS.md`: Flujos detallados
    - `README_BALCON_SERVICIOS.md`: Guía de uso
    - `NOTAS_BACKEND.md`: Notas de implementación

    ---

    ## 🎯 RESUMEN EJECUTIVO

    **Balcondemo** es un sistema completo de asistente virtual que:

    1. **Clasifica intenciones** usando modelos ML entrenados
    2. **Interpreta intenciones** usando LLM Gemini
    3. **Responde informativamente** usando RAG con PrivateGPT
    4. **Deriva operativamente** a agentes humanos cuando es necesario
    5. **Encuentra solicitudes relacionadas** usando embeddings semánticos
    6. **Gestiona múltiples requerimientos** en una sola conversación
    7. **Detecta dinámicamente** si usar contexto o no
    8. **Genera mensajes estructurados** desde el backend
    9. **Renderiza UI moderna** en el frontend

    El sistema está diseñado para ser:
    - ✅ **Inteligente**: Usa ML y LLM para entender intenciones
    - ✅ **Eficiente**: Optimizado para performance
    - ✅ **Robusto**: Maneja errores y edge cases
    - ✅ **Extensible**: Fácil de agregar nuevas funcionalidades
    - ✅ **Mantenible**: Código bien estructurado y documentado

    ---

    ## 🔗 INTEGRACIONES

    ### PrivateGPT
    - API REST en `http://localhost:8001`
    - Endpoint: `/v1/chat/completions`
    - Filtrado por documentos UNEMI
    - Filtrado por rol del usuario

    ### Google Gemini
    - API para interpretación de intenciones
    - Modelo: `gemini-2.5-flash`
    - Rate limit: 9 RPM
    - Protección con token bucket

    ---

    ## 📝 NOTAS FINALES

    Este sistema representa una arquitectura completa de chatbot inteligente que combina:
    - **Machine Learning** para clasificación
    - **LLM** para interpretación
    - **RAG** para respuestas informativas
    - **Handoff** para trámites operativos
    - **Frontend moderno** para interacción

    Todo el sistema está diseñado para ser **backend-driven**, donde el backend genera todos los mensajes, botones y estados, y el frontend solo renderiza lo que recibe.


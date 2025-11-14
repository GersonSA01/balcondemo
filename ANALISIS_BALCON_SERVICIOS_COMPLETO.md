# ANÁLISIS COMPLETO DEL SISTEMA BALCÓN DE SERVICIOS

## ÍNDICE
1. [Estructura General del Sistema](#estructura-general)
2. [Modelos de Datos](#modelos-de-datos)
3. [Vistas Administrativas](#vistas-administrativas)
4. [Vistas de Estudiante](#vistas-de-estudiante)
5. [APIs y Serializers](#apis-y-serializers)
6. [Funciones de Reasignación](#funciones-de-reasignación)
7. [Creación y Configuración de Servicios](#creación-y-configuración-de-servicios)
8. [Flujos de Trabajo](#flujos-de-trabajo)
9. [Notificaciones y Comunicaciones](#notificaciones-y-comunicaciones)
10. [Integración Frontend (sgaest)](#integración-frontend)

---

## ESTRUCTURA GENERAL DEL SISTEMA

### Ubicación de Archivos

**Proyecto Academico:**
- Módulo principal: `balcon/`
- Modelos: `balcon/models.py`
- Vistas administrativas: `balcon/adm_balconservicios.py`, `balcon/adm_solicitudbalcon.py`
- Vistas estudiante: `balcon/alu_solicitudbalcon.py`, `balcon/alu_solicitudbalconexterno.py`
- APIs: `api/views/alumno/balconservicio.py`
- Serializers: `api/serializers/alumno/balconservicio.py`
- Forms: `balcon/forms.py`
- URLs: `balcon/urls.py`

**Proyecto sgaest:**
- Frontend completo en SvelteKit
- Rutas: `src/routes/alu_solicitudbalcon/`
- Componentes: `_menu.svelte`, `_formulario.svelte`, `_carruselinfo.svelte`, `_solicitudesinfo.svelte`
- Páginas principales: `index.svelte`, `missolicitudes_new.svelte`, `missolicitudes.svelte`, `seguimientosolicitud.svelte`
- Seguimiento: `followup/[id].svelte` con componentes `_observaciones.svelte`, `_formulario.svelte`, `_archivo_modal_correccion.svelte`

---

## MODELOS DE DATOS

### Modelos Principales

#### 1. **Categoria** (`balcon/models.py:66-85`)
- **Propósito**: Categorías de procesos (ej: Académico, Administrativo)
- **Campos principales**:
  - `descripcion`: Descripción de la categoría
  - `estado`: Activo/Inactivo
  - `coordinaciones`: ManyToMany con Coordinacion
- **Métodos importantes**:
  - `en_uso()`: Verifica si tiene procesos asociados
  - `procesos()`: Retorna procesos activos de la categoría

#### 2. **Tipo** (`balcon/models.py:109-124`)
- **Propósito**: Tipo de solicitud (Información/Solicitud)
- **Campos**: `descripcion`, `estado`

#### 3. **Servicio** (`balcon/models.py:127-145`)
- **Propósito**: Servicios disponibles en el sistema
- **Campos principales**:
  - `nombre`: Nombre del servicio
  - `descripcion`: Descripción detallada
  - `estado`: Activo/Inactivo
  - `opcsistema`: ManyToMany con OpcionSistema (módulos del sistema)

#### 4. **Proceso** (`balcon/models.py:148-202`)
- **Propósito**: Procesos del balcón de servicios
- **Campos principales**:
  - `sigla`: Sigla del proceso (única)
  - `descripcion`: Descripción del proceso
  - `interno`: Para usuarios internos
  - `externo`: Para usuarios externos
  - `tipo`: ForeignKey a Tipo
  - `categoria`: ForeignKey a Categoria
  - `departamento`: ForeignKey a Departamento
  - `tiempoestimado`: Tiempo estimado de resolución
  - `activo`: Visible para estudiantes
  - `activoadmin`: Visible para administradores
  - `unicasolicitud`: Solo permite una solicitud activa
  - `subesolicitud`: Requiere subir archivo de solicitud
  - `persona`: Responsable del proceso
  - `presidentecurso`: Aplica para presidente de curso
- **Métodos importantes**:
  - `encuesta_configurada()`: Verifica si tiene encuesta
  - `informacion_mostrada()`: Información visible del proceso
  - `get_procesoservicios()`: Servicios asociados

#### 5. **ProcesoServicio** (`balcon/models.py:205-263`)
- **Propósito**: Relación entre Proceso y Servicio
- **Campos principales**:
  - `proceso`: ForeignKey a Proceso
  - `servicio`: ForeignKey a Servicio
  - `tiempominimo`: Tiempo mínimo de resolución
  - `tiempomaximo`: Tiempo máximo de resolución
  - `minutos`: Tiempo en minutos
  - `opcsistema`: Opción del sistema asociada
  - `url`: URL externa del servicio
- **Métodos importantes**:
  - `tiene_requisitos()`: Verifica si tiene requisitos configurados
  - `solicitudes()`: Retorna todas las solicitudes del servicio
  - `solicitudes_por_estado(estado)`: Solicitudes filtradas por estado

#### 6. **TipoProcesoServicio** (`balcon/models.py:266-278`)
- **Propósito**: Tipos específicos dentro de un servicio
- **Campos**: `servicio`, `nombre`, `descripcion`, `departamento`, `mostrar`

#### 7. **Informacion** (`balcon/models.py:281-326`)
- **Propósito**: Información mostrada a estudiantes sobre servicios
- **Campos principales**:
  - `tipo`: RESPUESTA RAPIDA (1) o INFORMATIVA (2)
  - `descripcion`: Descripción breve
  - `informacion`: Contenido HTML/información detallada
  - `archivomostrar`: Archivo para mostrar
  - `archivodescargar`: Archivo para descargar
  - `mostrar`: Visible/No visible
  - `servicio`: ForeignKey a ProcesoServicio

#### 8. **Requisito** (`balcon/models.py:88-106`)
- **Propósito**: Requisitos genéricos del sistema
- **Campos**: `descripcion`, `estado`
- **Método**: `nombre_input()`: Genera nombre para inputs HTML

#### 9. **RequisitosConfiguracion** (`balcon/models.py:330-341`)
- **Propósito**: Configuración de requisitos por servicio
- **Campos**:
  - `servicio`: ForeignKey a ProcesoServicio
  - `requisito`: ForeignKey a Requisito
  - `obligatorio`: Si es obligatorio o no
  - `activo`: Activo/Inactivo

#### 10. **Agente** (`balcon/models.py:389-424`)
- **Propósito**: Personas que reciben y gestionan solicitudes
- **Campos principales**:
  - `persona`: ForeignKey a Persona
  - `alias`: Alias único
  - `estado`: Activo/Inactivo
  - `admin`: Es administrador
  - `proceso`: ManyToMany con Proceso
- **Métodos importantes**:
  - `total_solicitud()`: Total de solicitudes pendientes
  - `total_solicitud_rechazadas()`: Total rechazadas
  - `total_solicitud_entramite()`: Total en trámite
  - `total_solicitud_resuelto()`: Total resueltas
  - `total_solicitud_cerrado()`: Total cerradas

#### 11. **Solicitud** (`balcon/models.py:427-621`)
- **Propósito**: Solicitudes de estudiantes
- **Campos principales**:
  - `codigo`: Código único de solicitud (generado automáticamente)
  - `solicitante`: ForeignKey a Persona (quien solicita)
  - `agente`: ForeignKey a Agente (agente inicial)
  - `agenteactual`: ForeignKey a Persona (agente actual)
  - `estado`: Estado de la solicitud (ver ESTADO_SOLICITUD_BALCON)
  - `tipo`: Tipo (1=Información, 2=Solicitud)
  - `archivo`: Archivo adjunto de solicitud
  - `descripcion`: Descripción de la solicitud
  - `perfil`: ForeignKey a PerfilUsuario
  - `externo`: Si es usuario externo
  - `numero`: Número secuencial
  - `tiempoespera`: Tiempo de espera en minutos
  - `tiempoesperareal`: Tiempo real de espera
  - `solicitud_devuelta`: Si fue devuelta
  - `fecha_expiracion_solicitud`: Fecha de expiración (para correcciones)
  - `solicitudasociada`: ForeignKey a otra Solicitud
- **Estados**:
  - 1: INGRESADO
  - 2: RECHAZADO
  - 3: EN TRÁMITE
  - 4: APROBADO
  - 5: ATENDIDO
  - 6: CORRECCIÓN
  - 7: CERRADA
  - 8: LEIDO
- **Métodos importantes**:
  - `get_codigo()`: Genera código único (ej: SOL-ABC-20241-000001)
  - `ver_servicio()`: Último servicio asignado
  - `traer_departamento()`: Departamento actual
  - `traer_carrera()`: Carrera asociada
  - `puede_calificar_proceso()`: Si puede calificar
  - `respondio_encuesta()`: Si respondió encuesta
  - `puede_gestionar_solicitudes()`: Estados en los que se puede gestionar

#### 12. **HistorialSolicitud** (`balcon/models.py:624-707`)
- **Propósito**: Historial de cambios de estado y asignaciones
- **Campos principales**:
  - `solicitud`: ForeignKey a Solicitud
  - `asignaenvia`: ForeignKey a Persona (quien asigna)
  - `asignadorecibe`: ForeignKey a Persona (quien recibe)
  - `departamentoenvia`: Departamento que envía
  - `departamento`: Departamento asignado
  - `carrera`: Carrera asociada
  - `servicio`: ForeignKey a ProcesoServicio
  - `tiposervicio`: ForeignKey a TipoProcesoServicio
  - `respuestarapida`: ForeignKey a Informacion
  - `observacion`: Observación/comentario
  - `estado`: Estado del historial (ver ESTADO_HISTORIAL_SOLICITUD_BALCON)
  - `archivo`: Archivo adjunto
  - `notificaciones`: Cantidad de notificaciones enviadas
  - `carreradepartamentoenvia`: CarreraDepartamento que envía
  - `carreradepartamentorecibe`: CarreraDepartamento que recibe
- **Estados del historial**:
  - 1: INGRESADO
  - 2: EN TRÁMITE
  - 3: CORRECCIÓN
  - 4: ATENDIDO
  - 5: APROBADO
  - 6: RECHAZADO
  - 7: CERRADA
  - 8: LEIDO
- **Métodos importantes**:
  - `tiempo_desde_asignacion()`: Calcula tiempo desde asignación
  - `color_estado()`: Color según estado

#### 13. **RequisitosSolicitud** (`balcon/models.py:738-741`)
- **Propósito**: Archivos de requisitos subidos por estudiantes
- **Campos**: `solicitud`, `requisito`, `archivo`

#### 14. **ResponsableDepartamento** (`balcon/models.py:358-386`)
- **Propósito**: Responsables de departamentos/carreras
- **Campos principales**:
  - `responsable`: ForeignKey a Persona
  - `alias`: Alias único
  - `departamento`: ForeignKey a Departamento
  - `carreradepartamento`: ForeignKey a CarreraDepartamento
  - `estado`: Activo/Inactivo
  - `principal`: Si es responsable principal
- **Métodos**:
  - `total_solicitud()`: Total de solicitudes en trámite

#### 15. **ServicioDepartamento** (`balcon/models.py:1039-1049`)
- **Propósito**: Configuración de reasignación automática por servicio
- **Campos**:
  - `carreradepartamento`: ForeignKey a CarreraDepartamento
  - `servicio`: ForeignKey a Servicio
  - `reasignar`: Si tiene reasignación directa

#### 16. **EncuestaProceso** (`balcon/models.py:883-964`)
- **Propósito**: Encuestas de satisfacción por proceso
- **Campos principales**:
  - `categoria`: ForeignKey a CategoriaEncuesta
  - `proceso`: ForeignKey a Proceso
  - `valoracion`: Cantidad de estrellas (1-10)
  - `vigente`: Si está vigente
  - `object_id`: ID del objeto relacionado
  - `content_type`: Tipo de contenido
  - `sigla`: Sigla de la encuesta
- **Métodos importantes**:
  - `preguntas(solicitud)`: Preguntas de la encuesta
  - `configuracion_estrellas()`: Configuración para UI

#### 17. **PreguntaEncuestaProceso** (`balcon/models.py:967-1001`)
- **Propósito**: Preguntas de encuestas
- **Campos**: `encuesta`, `descripcion`, `estado`

#### 18. **RespuestaEncuestaSatisfaccion** (`balcon/models.py:1004-1017`)
- **Propósito**: Respuestas de estudiantes a encuestas
- **Campos**: `pregunta`, `solicitud`, `valoracion`, `observacion`

---

## VISTAS ADMINISTRATIVAS

### 1. **adm_balconservicios.py** - Configuración del Sistema

#### Acciones Principales:

**Gestión de Procesos:**
- `addproceso`: Crear nuevo proceso
- `editproceso`: Editar proceso existente
- `delproceso`: Eliminar proceso (soft delete)
- `mostrarproceso`: Activar/desactivar visibilidad para estudiantes
- `mostraradmin`: Activar/desactivar visibilidad para administradores

**Gestión de Categorías:**
- `addcategoriamodal`: Crear categoría
- `editcategoriamodal`: Editar categoría
- `delcat`: Eliminar categoría
- Asociación con coordinaciones

**Gestión de Tipos:**
- `addtipomodal`: Crear tipo
- `edittipomodal`: Editar tipo
- `deltip`: Eliminar tipo

**Gestión de Servicios:**
- `addserviciomodal`: Crear servicio
- `editserviciomodal`: Editar servicio
- `delser`: Eliminar servicio
- `addconfiguraservicio`: Configurar servicio en proceso
- `editservicio`: Editar configuración de servicio
- `delservicio`: Eliminar servicio de proceso

**Gestión de Información:**
- `addinformacion`: Agregar información a servicio
- `editinformacion`: Editar información
- `delinformacion`: Eliminar información
- `bloqueopublicacion`: Activar/desactivar publicación

**Gestión de Requisitos:**
- `addrequisitomodal`: Crear requisito genérico
- `editrequisitomodal`: Editar requisito
- `delreq`: Eliminar requisito
- `addrequisitoservicio`: Asignar requisito a servicio
- `editrequisitoservicio`: Editar requisito de servicio
- `delreqservicio`: Eliminar requisito de servicio

**Gestión de Tipos de Servicio:**
- `addtiposervicio`: Crear tipo de servicio
- `edittiposervicio`: Editar tipo de servicio
- `mostrartipo`: Activar/desactivar visibilidad

**Gestión de Agentes:**
- `addpersonalmodal`: Agregar agente
- `editpersonalmodal`: Editar agente
- `delpersona`: Eliminar agente

**Gestión de Responsables:**
- `addresponsablemodal`: Agregar responsable de departamento
- `editresponsablemodal`: Editar responsable
- `delresponsable`: Eliminar responsable
- `actualizarestadoresponsable`: Actualizar estado/principal

**Gestión de Departamentos:**
- `adddepartamento`: Agregar CarreraDepartamento
- `editdepartamento`: Editar CarreraDepartamento
- `deldepartamento`: Eliminar CarreraDepartamento

**Gestión de Encuestas:**
- `addencuesta`: Crear/editar encuesta de proceso
- `addpregunta`: Agregar pregunta a encuesta
- `editpregunta`: Editar pregunta
- `delpregunta`: Eliminar pregunta
- `estrellasencuesta`: Configurar cantidad de estrellas

**Gestión de Servicios por Departamento:**
- `addserviciodepartamento`: Asignar servicio a departamento
- `editserviciodepartamento`: Editar asignación (reasignar)

**Estadísticas:**
- `versolicitudes`: Ver solicitudes por servicio
- `loadSolicitudesByEstado`: Cargar solicitudes por estado
- `loadGraphicNoveltiesAdmisionByEstado`: Gráficos de novedades de admisión

### 2. **adm_solicitudbalcon.py** - Gestión de Solicitudes

#### Acciones Principales:

**Gestión de Solicitudes:**
- `addsolicitudmodal`: Crear solicitud manualmente (admin)
- `addprocesosol`: Asignar proceso a solicitud
- `cambiaprocesosol`: Cambiar proceso de solicitud

**Respuestas y Resolución:**
- `addrespuestarapida`: Responder con respuesta rápida
- `resolver`: Marcar como resuelto
- `rechazar`: Rechazar solicitud
- `cerrar`: Cerrar solicitud
- `gestionar`: Gestionar solicitud (cambiar estado)

**Reasignaciones:**
- `reasignar`: Reasignar solicitud a otro departamento/responsable
- `reasignarinterno`: Reasignar internamente (mismo departamento)
- `reasignarmasivo`: Reasignar múltiples solicitudes
- `reasignarmasivo2`: Reasignar masivo mejorado
- `enviardepa`: Enviar a departamento del proceso

**Gestión de Agentes:**
- `addagente`: Asignar agente a solicitud

**Gestión de Responsables:**
- `addresponsablemodal`: Agregar responsable
- `editresponsablemodal`: Editar responsable
- `delresponsable`: Eliminar responsable
- `actualizarestadoresponsable`: Actualizar estado
- `responsables`: Obtener lista de responsables por departamento

**Respuestas Masivas:**
- `respondermasivo`: Responder múltiples solicitudes (admisión)
- `respondermasivototal`: Responder todas las solicitudes de un servicio
- `gestionarmasivo`: Gestionar múltiples solicitudes

**Reportes:**
- `reportefiltros`: Exportar reporte Excel
- `descargarhistorialsolicitud`: Descargar PDF del historial

**Alertas:**
- `alertabajoporcentaje`: Enviar alertas por bajo porcentaje de respuesta

**Búsquedas:**
- `buscarpersona3`: Buscar persona para asignación

---

## VISTAS DE ESTUDIANTE

### 1. **alu_solicitudbalcon.py** - Vista Principal de Estudiante

#### Acciones Principales:

**Gestión de Solicitudes:**
- `addsolicitudmodal`: Crear nueva solicitud
- `editsolicitudmodal`: Editar solicitud propia
- `delsolicitud`: Eliminar solicitud (solo estados 1 y 8)

**Información:**
- `informacion`: Ver información general
- `traerinfo`: Obtener información de proceso
- `traercampos`: Obtener procesos por categoría
- `traercategorias`: Obtener categorías disponibles

**Visualización:**
- `misolicitudes`: Ver mis solicitudes
- `verproceso`: Ver historial de solicitud
- `loadFormSolicitudCalificarServicio`: Cargar formulario de encuesta
- `saveSolicitudCalificarServicio`: Guardar respuesta de encuesta

### 2. **alu_solicitudbalconexterno.py** - Vista para Usuarios Externos

#### Acciones Principales:

**Registro:**
- `addregistro`: Registrar usuario externo
- `consultacedula`: Consultar datos por cédula

**Gestión de Solicitudes:**
- `addsolicitud`: Crear solicitud externa
- `editsolicitud`: Editar solicitud externa
- `delsolicitud`: Eliminar solicitud
- `consultasolicitud`: Consultar solicitudes por cédula/email

**Información:**
- `listservicio`: Listar servicios de proceso
- `serviciourl`: Obtener URL del servicio
- `requisitos`: Obtener requisitos de servicio
- `verproceso`: Ver historial

---

## APIs Y SERIALIZERS

### API: **balconservicio.py**

#### Endpoints POST:

1. **getInformationsServices**
   - Obtiene información de servicios por proceso
   - Parámetros: `id` (proceso encriptado)
   - Retorna: Lista de informaciones de servicios

2. **addRequestService**
   - Crea nueva solicitud de servicio
   - Parámetros:
     - `service_id`: ID del servicio
     - `tipo`: Tipo de solicitud (1=Info, 2=Solicitud)
     - `descripcion`: Descripción
     - `file_uprequest`: Archivo de solicitud (si aplica)
     - `file_requirement_{id}`: Archivos de requisitos
     - `solicitud`: ID de solicitud asociada (opcional)
   - Lógica:
     - Verifica si tiene solicitudes pendientes en el mismo proceso
     - Asigna agente (director de carrera o agente libre)
     - Crea solicitud y historial
     - Guarda requisitos
     - Envía notificación

3. **getMyRequests**
   - Obtiene solicitudes del estudiante
   - Retorna: Lista de solicitudes con estados
   - Lógica adicional:
     - Cierra automáticamente solicitudes en corrección expiradas (3 días)
     - Cuenta solicitudes pendientes de encuesta

4. **editRequestService**
   - Edita descripción de solicitud
   - Parámetros: `id`, `descripcion`

5. **correctRequestService**
   - Corrige solicitud rechazada
   - Parámetros: `id`, `descripcion`, `file_uprequest`
   - Cambia estado a EN TRÁMITE (3)
   - Crea nuevo historial

6. **delRequestService**
   - Elimina solicitud
   - Solo permite eliminar en estados 1 (INGRESADO) o 8 (LEIDO)

7. **saveRequestQuestionstoQualify**
   - Guarda respuestas de encuesta
   - Parámetros: `id`, `eAnswersQuestions` (JSON)

#### Endpoints GET:

1. **getViewHistoricalRequestService**
   - Obtiene historial completo de solicitud
   - Parámetros: `id`

2. **getMyRequestService**
   - Obtiene detalles de una solicitud específica
   - Parámetros: `id`

3. **getMyRequestQuestionstoQualify**
   - Obtiene preguntas de encuesta para calificar
   - Parámetros: `id`

4. **Default (sin action)**
   - Obtiene categorías y procesos disponibles
   - Retorna: Categorías con procesos, solicitudes agrupadas por estado

### Serializers: **balconservicio.py**

1. **SolicitudSerializer**: Serializa Solicitud con todos sus detalles
2. **HistorialSolicitudSerializer**: Serializa historial con colores y estados
3. **ProcesoSerializer**: Serializa procesos
4. **CategoriaSerializer**: Serializa categorías con procesos
5. **InformacionSerializer**: Serializa información de servicios
6. **ProcesoServicioSerializer**: Serializa servicios con requisitos
7. **RequisitosSolicitudSerializer**: Serializa requisitos subidos
8. **EncuestaProcesoSerializer**: Serializa encuestas con preguntas

---

## FUNCIONES DE REASIGNACIÓN

### 1. Reasignación Individual (`reasignar`)

**Ubicación**: `adm_solicitudbalcon.py:343-425`

**Proceso**:
1. Obtiene solicitud a reasignar
2. Cambia estado a EN TRÁMITE (3)
3. Determina departamento que envía (del responsable actual)
4. Si no es "regresar_direccion":
   - Obtiene responsable asignado
   - Obtiene departamento del responsable
5. Si es "regresar_direccion":
   - Devuelve al agente inicial
   - Marca `solicitud_devuelta = True`
6. Crea nuevo HistorialSolicitud con:
   - Estado 2 (EN TRÁMITE)
   - Observación de reasignación
   - Archivo adjunto (opcional)
   - Departamentos de envío y recepción
7. Actualiza `agenteactual` de la solicitud
8. Envía notificación al nuevo responsable
9. Envía email de notificación

**Formulario**: `SolicitudBalconReasignarForm`
- `regresar_direccion`: Checkbox para devolver a dirección
- `departamento`: Select de departamentos
- `asignadorecibe`: Select de responsables
- `observacion_reasignar`: Textarea obligatorio
- `archivo_reasignar`: Archivo opcional

### 2. Reasignación Interna (`reasignarinterno`)

**Ubicación**: `adm_solicitudbalcon.py:427-489`

**Proceso**:
1. Verifica que la persona no tenga asignación previa en la solicitud
2. Crea historial con mismo departamento
3. Asigna a persona específica
4. Envía notificaciones

**Formulario**: `SolicitudBalconReasignarInternoForm`
- `asignadorecibe`: Select2 de personas
- `observacion`: Textarea
- `archivo`: Archivo opcional

### 3. Reasignación Masiva (`reasignarmasivo2`)

**Ubicación**: `adm_solicitudbalcon.py:1087-1158`

**Proceso**:
1. Recibe lista de IDs de solicitudes (JSON)
2. Obtiene responsable asignado
3. Determina departamentos
4. Itera sobre cada solicitud:
   - Crea historial de reasignación
   - Actualiza estado a EN TRÁMITE
   - Actualiza agente actual
5. Envía una sola notificación con total de solicitudes reasignadas
6. Envía email masivo

**Características**:
- Permite reasignar múltiples solicitudes a la vez
- Archivo único para todas las solicitudes
- Notificación consolidada

### 4. Reasignación Automática

**Ubicación**: `models.py:692-706` (save de HistorialSolicitud)

**Proceso**:
- Al crear el primer historial de una solicitud
- Si el servicio tiene `ServicioDepartamento` con `reasignar=True`
- Asigna automáticamente al responsable principal del departamento

### 5. Enviar a Departamento (`enviardepa`)

**Ubicación**: `adm_solicitudbalcon.py:491-539`

**Proceso**:
1. Obtiene el proceso de la solicitud
2. Busca responsables del departamento del proceso
3. Selecciona responsable con menos solicitudes
4. Crea historial asignando al departamento
5. Envía notificaciones

---

## CREACIÓN Y CONFIGURACIÓN DE SERVICIOS

### Flujo de Creación Completo:

#### 1. Crear Categoría
- **Acción**: `addcategoriamodal`
- **Formulario**: `CategoriaBalconForm`
- **Campos**: descripción, coordinaciones (ManyToMany), estado
- **Ubicación**: `adm_balconservicios.py:425-444`

#### 2. Crear Tipo
- **Acción**: `addtipomodal`
- **Formulario**: `TipoBalconForm`
- **Campos**: descripción, estado
- **Ubicación**: `adm_balconservicios.py:479-494`

#### 3. Crear Requisito Genérico
- **Acción**: `addrequisitomodal`
- **Formulario**: `RequisitoBalconForm`
- **Campos**: descripción, estado
- **Ubicación**: `adm_balconservicios.py:575-590`

#### 4. Crear Servicio
- **Acción**: `addserviciomodal`
- **Formulario**: `ServicioBalconForm`
- **Campos**: nombre, descripción, opciones sistema (ManyToMany), estado
- **Ubicación**: `adm_balconservicios.py:622-642`

#### 5. Crear Proceso
- **Acción**: `addproceso`
- **Formulario**: `ProcesoForm`
- **Campos**:
  - sigla (única)
  - descripción
  - tipo (ForeignKey)
  - categoría (ForeignKey)
  - departamento (ForeignKey, opcional)
  - subesolicitud (checkbox)
  - interno (checkbox)
  - externo (checkbox)
- **Ubicación**: `adm_balconservicios.py:153-178`

#### 6. Configurar Servicio en Proceso
- **Acción**: `addconfiguraservicio`
- **Formulario**: `ConfiguraServicioBalconForm`
- **Campos**:
  - servicio (ForeignKey)
  - tiempo mínimo
  - tiempo máximo
  - minutos
  - opción sistema
  - URL
- **Ubicación**: `adm_balconservicios.py:526-552`
- **Crea**: `ProcesoServicio`

#### 7. Agregar Requisitos al Servicio
- **Acción**: `addrequisitoservicio`
- **Formulario**: `RequisitoServicioForm`
- **Campos**: requisito, obligatorio, activo
- **Ubicación**: `adm_balconservicios.py:343-362`
- **Crea**: `RequisitosConfiguracion`

#### 8. Agregar Tipos de Servicio
- **Acción**: `addtiposervicio`
- **Formulario**: `TipoProcesoServicioForm`
- **Campos**: nombre, descripción (CKEditor), departamento, mostrar
- **Ubicación**: `adm_balconservicios.py:364-383`
- **Crea**: `TipoProcesoServicio`

#### 9. Agregar Información al Servicio
- **Acción**: `addinformacion`
- **Formulario**: `InformacionBalconForm`
- **Campos**:
  - tipo (RESPUESTA RAPIDA o INFORMATIVA)
  - descripción
  - información (HTML)
  - archivo mostrar
  - archivo descargar
  - mostrar
- **Ubicación**: `adm_balconservicios.py:215-268`
- **Crea**: `Informacion`

#### 10. Configurar Reasignación Automática
- **Acción**: `addserviciodepartamento`
- **Campos**: servicio, carreradepartamento, reasignar (checkbox)
- **Ubicación**: `adm_balconservicios.py:999+`
- **Crea**: `ServicioDepartamento`

#### 11. Configurar Encuesta (Opcional)
- **Acción**: `addencuesta`
- **Formulario**: `EncuestaPreguntaForm`
- **Campos**: categoría, valoración (estrellas), preguntas
- **Ubicación**: `adm_balconservicios.py:952-984`
- **Crea**: `EncuestaProceso` y `PreguntaEncuestaProceso`

---

## FLUJOS DE TRABAJO

### Flujo 1: Creación de Solicitud por Estudiante

1. **Estudiante accede al balcón**
   - Ve categorías disponibles según su coordinación
   - Selecciona categoría
   - Ve procesos de esa categoría

2. **Selecciona proceso**
   - Ve información del proceso
   - Ve servicios disponibles
   - Selecciona servicio

3. **Completa formulario**
   - Descripción de solicitud
   - Archivo de solicitud (si `subesolicitud=True`)
   - Archivos de requisitos (obligatorios y opcionales)

4. **Sistema procesa**
   - Verifica que no tenga solicitudes pendientes en el mismo proceso
   - Asigna agente:
     - Si tiene director de carrera → asigna al director
     - Si no → busca agente libre (menos solicitudes)
   - Crea `Solicitud` con estado INGRESADO (1)
   - Crea `HistorialSolicitud` inicial
   - Si tiene `ServicioDepartamento.reasignar=True` → asigna automáticamente al responsable
   - Guarda `RequisitosSolicitud` (archivos)
   - Genera código único
   - Envía notificación al agente

5. **Agente recibe**
   - Ve solicitud en su panel
   - Puede gestionar, reasignar, responder, etc.

### Flujo 2: Gestión de Solicitud

1. **Agente/Responsable recibe solicitud**
   - Estado: INGRESADO (1) o EN TRÁMITE (3)

2. **Opciones de gestión**:
   
   **a) Responder Rápida**
   - Selecciona respuesta rápida predefinida
   - Cambia estado a APROBADO (4)
   - Crea historial con estado ATENDIDO (4)

   **b) Gestionar**
   - Cambia estado:
     - RECHAZADO (2) → historial estado RECHAZADO (6)
     - APROBADO (4) → historial estado APROBADO (5)
     - CORRECCIÓN (6) → historial estado CORRECCIÓN (3), establece fecha expiración (3 días)
     - ATENDIDO (5) → historial estado ATENDIDO (4)
   - Agrega observación
   - Adjunta archivo (opcional)
   - Envía notificación al estudiante

   **c) Reasignar**
   - Selecciona departamento y responsable
   - O devuelve a dirección original
   - Agrega observación
   - Adjunta archivo (opcional)
   - Crea historial con estado EN TRÁMITE (2)
   - Envía notificación al nuevo responsable

   **d) Rechazar**
   - Agrega observación de rechazo
   - Cambia estado a RECHAZADO (2)
   - Crea historial con estado RECHAZADO (6)
   - Envía notificación al estudiante

   **e) Cerrar**
   - Agrega observación final
   - Cambia estado a CERRADA (7)
   - Crea historial con estado CERRADA (7)
   - Envía notificación al estudiante

3. **Estudiante recibe notificación**
   - Ve cambio de estado
   - Si es CORRECCIÓN → debe corregir en 3 días
   - Si es APROBADO/RECHAZADO/CERRADA → puede calificar

### Flujo 3: Corrección de Solicitud

1. **Solicitud en estado CORRECCIÓN (6)**
   - Estudiante ve solicitud con fecha de expiración
   - Tiene 3 días para corregir

2. **Estudiante corrige**
   - Actualiza descripción
   - Sube nuevo archivo (opcional)
   - Sistema agrega "Correcciones realizadas:" a la descripción
   - Cambia estado a EN TRÁMITE (3)
   - Crea historial con estado EN TRÁMITE (2)
   - Envía notificación al responsable

3. **Si no corrige en 3 días**
   - Sistema cierra automáticamente
   - Agrega texto a observación del historial
   - Cambia estado a CERRADA (7)

### Flujo 4: Encuesta de Satisfacción

1. **Solicitud finalizada**
   - Estados: RECHAZADO (2), APROBADO (4), CERRADA (7)

2. **Sistema verifica**
   - Si proceso tiene encuesta configurada
   - Si estudiante no ha respondido

3. **Estudiante califica**
   - Ve preguntas de encuesta
   - Califica con estrellas (1-valoracion)
   - Agrega observaciones
   - Guarda respuestas

4. **Sistema registra**
   - Crea `RespuestaEncuestaSatisfaccion` por pregunta
   - Marca como respondida

---

## NOTIFICACIONES Y COMUNICACIONES

### Tipos de Notificaciones:

1. **Notificación en Sistema**
   - Función: `notificacion()` de `sga.funciones`
   - Parámetros: título, cuerpo, destinatario, URL, módulo, ID objeto, prioridad, app_label, modelo
   - Se muestra en panel de notificaciones del usuario

2. **Email HTML**
   - Función: `send_html_mail()` de `sga.tasks`
   - Templates:
     - `emails/notificacion_balcon.html`: Notificación general
     - `emails/reasignar_masivo_balcon.html`: Reasignación masiva
     - `emails/alerta_revision_solicitud_balcon.html`: Alerta de revisión
   - Cuenta de correo: `CUENTAS_CORREOS[0][1]` (configurable)

### Eventos que Generan Notificaciones:

1. **Nueva Solicitud**
   - Notifica al agente asignado
   - Email al agente

2. **Reasignación**
   - Notifica al nuevo responsable
   - Email al nuevo responsable

3. **Cambio de Estado**
   - Notifica al estudiante
   - Email al estudiante (si tiene email)

4. **Corrección Requerida**
   - Notifica al estudiante
   - Email con plazo de 3 días

5. **Reasignación Masiva**
   - Notifica al responsable con total
   - Email consolidado

6. **Alerta de Revisión**
   - Notifica a responsables con solicitudes pendientes
   - Email con lista de solicitudes

---

## INTEGRACIÓN FRONTEND (sgaest)

### Arquitectura Frontend

**Tecnología**: SvelteKit (Svelte 4)
**Ubicación**: `src/routes/alu_solicitudbalcon/`
**API Base**: `alumno/balcon_servicios` (endpoint del backend Django)

### Estructura de Componentes

#### 1. **Página Principal** (`index.svelte`)
- **Ruta**: `/alu_solicitudbalcon`
- **Funcionalidad**:
  - Carga inicial de categorías y procesos
  - Muestra carrusel informativo cuando no hay servicio seleccionado
  - Formulario de solicitud dinámico
  - Panel lateral con estado de solicitudes
- **Componentes utilizados**:
  - `Menu`: Navegación por categorías y procesos
  - `CarruselInfo`: Información de servicios disponibles
  - `FormularioSolicitud`: Formulario para crear solicitud
  - `SolicitudesInfo`: Panel de estado de solicitudes
- **APIs llamadas**:
  - `GET alumno/balcon_servicios`: Carga inicial (categorías, solicitudes)
  - `POST alumno/balcon_servicios` con `action: 'getInformationsServices'`: Obtiene servicios de un proceso
  - `POST alumno/balcon_servicios` con `action: 'addRequestService'`: Crea nueva solicitud

#### 2. **Menú de Categorías** (`_menu.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Muestra categorías en acordeón
  - Lista procesos dentro de cada categoría
  - Maneja selección de proceso
  - Emite evento `actionRun` con `action: 'selectItem'`
- **Props**: `eCategorias` (array de categorías con procesos)

#### 3. **Carrusel de Información** (`_carruselinfo.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Muestra lista de servicios disponibles del proceso seleccionado
  - Permite ver archivos adjuntos (mostrar/descargar)
  - Botón "Solicitar" que abre formulario
  - Carrusel de imágenes cuando no hay servicios
- **Props**: `eInformationsServices` (array de servicios con información)
- **Eventos**: Emite `actionRun` con `action: 'openRequestService'`

#### 4. **Formulario de Solicitud** (`_formulario.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Formulario dinámico según servicio seleccionado
  - Campo de descripción obligatorio
  - Selector de solicitud relacionada (opcional)
  - Subida de archivo de solicitud (si `proceso.subesolicitud`)
  - Subida de archivos de requisitos (dinámicos según servicio)
  - Validación de archivos obligatorios
- **Props**: 
  - `eService`: Servicio seleccionado
  - `eRequirements`: Requisitos del servicio
  - `eListaSolicitudes`: Lista de solicitudes relacionadas
- **Validaciones**:
  - Descripción obligatoria
  - Archivo de solicitud obligatorio si `subesolicitud = true`
  - Archivos de requisitos obligatorios según configuración
  - Formato PDF, máximo 4MB
- **Librerías**: FilePond para subida de archivos

#### 5. **Panel de Solicitudes** (`_solicitudesinfo.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Muestra carrusel de solicitudes por estado
  - Estados: En trámite, Pendiente, Aprobado, Corregir, Rechazado
  - Botón para ver todas las solicitudes
- **Props**: `eSolicitudes` (objeto con arrays por estado)

#### 6. **Mis Solicitudes** (`missolicitudes_new.svelte`)
- **Ruta**: `/alu_solicitudbalcon/missolicitudes_new`
- **Funcionalidad**:
  - Tabla completa de todas las solicitudes del estudiante
  - Columnas: N° Solicitud, Fecha, Proceso, Motivo, Evidencias, Estado, Acciones
  - Acciones disponibles:
    - Ver seguimiento (si estado != 1)
    - Eliminar (solo si estado = 1)
    - Calificar servicio (si `puede_calificar_proceso`)
  - Modales para:
    - Editar solicitud (`getMyRequestService`)
    - Ver historial (`getViewHistoricalRequestService`)
    - Calificar servicio (`getMyRequestQuestionstoQualify`)
- **APIs llamadas**:
  - `POST alumno/balcon_servicios` con `action: 'getMyRequests'`: Lista solicitudes
  - `POST alumno/balcon_servicios` con `action: 'delRequestService'`: Elimina solicitud
  - `GET alumno/balcon_servicios` con `action: 'getMyRequestService'`: Detalle de solicitud
  - `GET alumno/balcon_servicios` con `action: 'getViewHistoricalRequestService'`: Historial
  - `GET alumno/balcon_servicios` con `action: 'getMyRequestQuestionstoQualify'`: Encuesta
  - `POST alumno/balcon_servicios` con `action: 'editRequestService'`: Edita solicitud
  - `POST alumno/balcon_servicios` con `action: 'saveRequestQuestionstoQualify'`: Guarda calificación

#### 7. **Seguimiento de Solicitud** (`followup/[id].svelte`)
- **Ruta**: `/alu_solicitudbalcon/followup/{id}`
- **Funcionalidad**:
  - Vista detallada de una solicitud específica
  - Muestra observaciones y formulario de corrección
  - Layout de dos columnas
- **Componentes utilizados**:
  - `ComponentObservaciones`: Timeline y observaciones
  - `FormularioSolicitud`: Formulario de corrección

#### 8. **Observaciones** (`followup/_observaciones.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Timeline visual del historial de la solicitud
  - Muestra último estado y observación
  - Botón para ver archivo adjunto si existe
  - Colores dinámicos según estado
- **Estados visualizados**:
  - Estado 1-2: Naranja (#FF9900) - "Espacio destinado para observaciones"
  - Estado 3: Morado (#9E68DC) - "Motivos de solicitud enviada a corregir"
  - Estado 4: Cian (#0dcaf0) - "Motivos de solicitud cerrada"
  - Estado 5: Verde (#0BA883) - "Motivos de solicitud aprobada"
  - Estado 6: Rojo (#FF0000) - "Motivos de solicitud rechazada"
- **APIs llamadas**:
  - `GET alumno/balcon_servicios` con `action: 'getViewHistoricalRequestService'`: Historial completo

#### 9. **Formulario de Corrección** (`followup/_formulario.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Formulario para corregir solicitud (solo si estado = 6)
  - Muestra alerta para calificar si `puede_calificar_proceso`
  - Subida de archivo corregido
  - Subida de requisitos corregidos
  - Reemplazo de archivos existentes
- **APIs llamadas**:
  - `POST alumno/balcon_servicios` con `action: 'correctRequestService'`: Envía corrección
  - `GET alumno/balcon_servicios` con `action: 'getMyRequestQuestionstoQualify'`: Encuesta
  - `POST alumno/balcon_servicios` con `action: 'saveRequestQuestionstoQualify'`: Guarda calificación

#### 10. **Modal de Archivo** (`followup/_archivo_modal_correccion.svelte`)
- **Tipo**: Componente hijo
- **Funcionalidad**:
  - Modal para visualizar PDFs adjuntos
  - Iframe para mostrar documentos

### Flujos de Usuario en Frontend

#### Flujo 1: Crear Solicitud
1. Usuario selecciona categoría → `Menu` emite evento
2. Usuario selecciona proceso → Carga servicios del proceso
3. `CarruselInfo` muestra servicios disponibles
4. Usuario hace clic en "Solicitar" → Abre `FormularioSolicitud`
5. Usuario completa formulario y sube archivos
6. Envío → `POST addRequestService` → Redirección a mis solicitudes

#### Flujo 2: Ver Mis Solicitudes
1. Carga inicial → `POST getMyRequests`
2. Tabla muestra todas las solicitudes
3. Acciones disponibles según estado
4. Clic en seguimiento → Navega a `followup/[id]`

#### Flujo 3: Seguimiento de Solicitud
1. Carga historial → `GET getViewHistoricalRequestService`
2. `Observaciones` muestra timeline
3. `Formulario` muestra opciones según estado:
   - Estado 6: Formulario de corrección
   - Otros estados: Botón de calificación (si aplica)

#### Flujo 4: Corregir Solicitud
1. Usuario ve solicitud en estado CORRECCIÓN (6)
2. Formulario de corrección visible
3. Usuario sube archivos corregidos
4. Envío → `POST correctRequestService`
5. Redirección a mis solicitudes

#### Flujo 5: Calificar Servicio
1. Usuario ve alerta de calificación
2. Clic en "Calificar Servicio" → Abre modal
3. Modal muestra preguntas de encuesta con estrellas
4. Usuario califica cada pregunta (1-5 estrellas)
5. Usuario puede agregar comentarios opcionales
6. Envío → `POST saveRequestQuestionstoQualify`
7. Cierre de modal y actualización

### Utilidades y Stores

#### Stores Utilizados:
- `loadingStore`: Manejo de estados de carga global
- `toastStore`: Notificaciones toast
- `notificationStore`: Notificaciones persistentes
- `userStore`: Información del usuario autenticado

#### Utilidades:
- `requestUtils.ts`: Funciones `apiGET`, `apiPOST`, `apiPOSTFormData`
- `constants.ts`: Variables de configuración (BASE_API, BASE_API_STATIC)
- `decodetoken.ts`: Decodificación de tokens JWT

### Características Especiales

1. **Notificaciones de Encuesta Pendiente**:
   - Alerta cuando hay solicitudes sin calificar
   - Mensaje personalizado desde backend
   - Duración de 15 segundos, pausable

2. **Validación de Archivos**:
   - FilePond con validación de tipo PDF
   - Tamaño máximo 4MB
   - Validación de archivos obligatorios antes de envío

3. **Responsive Design**:
   - Tabla con columnas ocultas en móvil
   - Botón toggle para mostrar/ocultar columnas extra
   - Layout adaptativo según tamaño de pantalla

4. **Timeline Visual**:
   - Línea de tiempo horizontal con círculos de estado
   - Colores dinámicos según estado
   - Tooltips con información adicional
   - Gradientes en transiciones de estado

5. **Sistema de Calificación**:
   - Componente StarRating de `@ernane/svelte-star-rating`
   - Escala de 1-5 estrellas
   - Comentarios opcionales por pregunta
   - Validación de calificación obligatoria

### Integración con Backend

**Endpoints utilizados**:
- `GET /alumno/balcon_servicios`: Carga inicial
- `POST /alumno/balcon_servicios`: Acciones con parámetro `action`
- `GET /alumno/balcon_servicios`: Acciones de lectura con parámetro `action`

**Formato de Requests**:
- JSON para acciones simples
- FormData para acciones con archivos
- Parámetro `action` define la operación

**Manejo de Errores**:
- Validación de `res.isSuccess`
- Verificación de `res.module_access`
- Redirección si no hay acceso
- Toasts y notificaciones para errores

---

## FUNCIONES AUXILIARES IMPORTANTES

### 1. Generación de Código de Solicitud
- **Método**: `Solicitud.get_codigo()`
- **Formato**: `{TIPO}-{SIGLA}-{AÑO}{MES}-{ID}`
- **Ejemplo**: `SOL-ABC-20241-000001`

### 2. Asignación de Agente
- **Lógica**: Busca agente con menos solicitudes pendientes
- **Prioridad**: Agentes admin primero
- **Ubicación**: `alu_solicitudbalcon.py:89-97`, `api/views/alumno/balconservicio.py:82-89`

### 3. Validación de Solicitudes Pendientes
- **Verifica**: Que no tenga solicitudes en estados 1, 3 o 6 en el mismo proceso
- **Ubicación**: `alu_solicitudbalcon.py:59`, `api/views/alumno/balconservicio.py:93-99`

### 4. Cierre Automático de Correcciones
- **Lógica**: Si solicitud en CORRECCIÓN (6) y pasaron 3 días → CERRADA (7)
- **Ubicación**: `api/views/alumno/balconservicio.py:184-191`

### 5. Cálculo de Tiempo de Espera
- **Método**: `HistorialSolicitud.tiempo_desde_asignacion()`
- **Retorna**: Días y formato legible

### 6. Cache de Solicitudes
- **Clave**: `balconsolicitudes_persona_id{encrypt(persona_id)}`
- **Tiempo**: 60 minutos
- **Ubicación**: `api/views/alumno/balconservicio.py:426-431`

---

## ESTADOS Y TRANSICIONES

### Estados de Solicitud:
```
1. INGRESADO → 3. EN TRÁMITE → 4. APROBADO / 5. ATENDIDO / 7. CERRADA
                ↓
            2. RECHAZADO
                ↓
            6. CORRECCIÓN → 3. EN TRÁMITE (si corrige) / 7. CERRADA (si expira)
                ↓
            8. LEIDO
```

### Estados de Historial:
```
1. INGRESADO → 2. EN TRÁMITE → 3. CORRECCIÓN / 4. ATENDIDO / 5. APROBADO / 6. RECHAZADO / 7. CERRADA
                                    ↓
                                8. LEIDO
```

---

## PERMISOS Y SEGURIDAD

### Decoradores:
- `@login_required`: Requiere autenticación
- `@secure_module`: Verifica permisos del módulo
- `@last_access`: Actualiza último acceso
- `@transaction.atomic()`: Transacciones atómicas

### Validaciones:
- Solo estudiantes pueden crear solicitudes
- Solo responsables pueden gestionar solicitudes de su departamento
- Solo se pueden eliminar solicitudes en estados 1 o 8
- Validación de archivos: máximo 4MB, formatos permitidos

---

## REPORTES Y ESTADÍSTICAS

### Reportes Disponibles:
1. **Excel de Solicitudes** (`reportefiltros`)
   - Columnas: N, Nombre, Cédula, Carrera, Servicio, Tipo, Estado, Fecha, Agente, Dirección, Fecha Asignación

2. **PDF de Historial** (`descargarhistorialsolicitud`)
   - Historial completo de una solicitud
   - Template: `adm_solicitudbalcon/verhistorial_pdf.html`

3. **Estadísticas por Servicio**
   - Total de solicitudes por estado
   - Novedades de admisión (si aplica)

---

## CONFIGURACIONES ESPECIALES

### 1. Reasignación Directa
- Modelo: `ServicioDepartamento`
- Campo: `reasignar` (Boolean)
- Efecto: Asigna automáticamente al responsable principal del departamento

### 2. Solicitud Única
- Campo: `Proceso.unicasolicitud`
- Efecto: Solo permite una solicitud activa por proceso

### 3. Subir Solicitud
- Campo: `Proceso.subesolicitud`
- Efecto: Requiere archivo adjunto obligatorio

### 4. Presidente de Curso
- Campo: `Proceso.presidentecurso`
- Efecto: Solo visible para presidentes de curso

### 5. Usuarios Externos
- Campo: `Proceso.externo`
- Efecto: Visible para usuarios no matriculados
- Vista: `alu_solicitudbalconexterno.py`

---

## CONCLUSIÓN

El sistema de Balcón de Servicios es un sistema completo y robusto que permite:

1. **Gestión completa de servicios** desde la configuración hasta la resolución
2. **Múltiples flujos de trabajo** adaptables a diferentes tipos de procesos
3. **Sistema de reasignaciones** flexible y potente
4. **Notificaciones y comunicaciones** integradas
5. **Encuestas de satisfacción** configurables
6. **APIs REST** para integración con frontend
7. **Reportes y estadísticas** para análisis

El sistema está completamente funcional en el proyecto **academico** y listo para ser integrado con cualquier frontend moderno como el implementado en **BalconDemo**.


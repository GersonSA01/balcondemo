# 🎓 Sistema de Balcón de Servicios - Frontend

## 📋 Descripción

Sistema completo de gestión de solicitudes estudiantiles integrado con Django backend. Permite a los estudiantes navegar por categorías de servicios, ver información detallada, realizar solicitudes y hacer seguimiento de su estado.

## 🏗️ Arquitectura

### Estructura de Carpetas

```
frontend/src/
├── lib/
│   ├── balcon/                    # Componentes del Balcón de Servicios
│   │   ├── BalconServicios.svelte # Componente principal
│   │   ├── Menu.svelte            # Menú de navegación por categorías
│   │   ├── CarruselInfo.svelte    # Carrusel de información de servicios
│   │   ├── Formulario.svelte      # Formulario de solicitudes
│   │   └── SolicitudesInfo.svelte # Estado de solicitudes
│   ├── components/                # Componentes compartidos
│   │   ├── ToastContainer.svelte  # Notificaciones toast
│   │   ├── LoadingOverlay.svelte  # Overlay de carga
│   │   └── NotificationContainer.svelte # Notificaciones
│   ├── stores/                    # Stores de Svelte
│   │   ├── loadingStore.js       # Estado de carga
│   │   ├── toastStore.js         # Toast messages
│   │   └── notificationStore.js  # Notificaciones
│   ├── utils/                     # Utilidades
│   │   ├── constants.js          # Constantes globales
│   │   └── requestUtils.js       # Funciones para peticiones HTTP
│   ├── Chatbot.svelte            # Chatbot RAG (original)
├── App.svelte                     # Componente principal
├── main.js                        # Punto de entrada
└── theme.css                      # Estilos globales
```

## 🚀 Instalación

### Dependencias

```bash
cd frontend
npm install
```

Las dependencias principales son:
- `svelte` - Framework reactivo
- `sveltestrap` - Componentes Bootstrap para Svelte
- `filepond` - Subida de archivos
- `svelte-filepond` - Integración FilePond con Svelte
- `filepond-plugin-file-validate-type` - Validación de tipos de archivo

### Iniciar Desarrollo

```bash
npm run dev
```

El servidor de desarrollo se ejecutará en `http://localhost:5173`

## 📡 API Backend Esperada

El frontend espera los siguientes endpoints en el backend Django:

### 1. GET `/alumno/balcon_servicios`

Obtiene las categorías, servicios y solicitudes del estudiante.

**Respuesta esperada:**

```json
{
  "isSuccess": true,
  "data": {
    "eCategorias": [
      {
        "id": 1,
        "descripcion_minus": "Categoría Académica",
        "procesos": [
          {
            "id": 101,
            "descripcion_minus": "Matriculación"
          }
        ]
      }
    ],
    "eBalconyRequests": {
      "en_tramite": [...],
      "pendiente": [...],
      "aprobado": [...],
      "corregir": [...],
      "rechazado": [...]
    },
    "eListaSolicitudes": [...],
    "cantSolicitudesSinResponderEncuesta": 0,
    "mensajeResponderEncuesta": ""
  }
}
```

### 2. POST `/alumno/balcon_servicios`

Acciones múltiples según el parámetro `action`.

#### Obtener información de servicios

```json
{
  "action": "getInformationsServices",
  "id": 101
}
```

**Respuesta:**

```json
{
  "isSuccess": true,
  "data": {
    "eInformationsServices": [
      {
        "id": 1,
        "descripcion_minus": "Servicio de Matriculación",
        "servicio": {
          "id": 1,
          "display": "Matriculación Online",
          "servicio": {
            "descripcion_minus": "Proceso de matriculación en línea"
          },
          "opcsistema": null,
          "requisitos": [...]
        },
        "archivomostrar": "/path/to/file.pdf",
        "typefilemostrar": ".pdf",
        "archivodescargar": null,
        "informacion": "<p>Información adicional</p>"
      }
    ]
  }
}
```

#### Crear una solicitud

```json
// FormData con:
{
  "action": "addRequestService",
  "service_id": 1,
  "tipo": "2",
  "descripcion": "Descripción de la solicitud",
  "solicitud": 0,  // ID de solicitud relacionada (opcional)
  "file_uprequest": File,  // Si aplica
  "file_requirement_1": File,  // Archivos de requisitos
  ...
}
```

**Respuesta:**

```json
{
  "isSuccess": true,
  "message": "Solicitud creada exitosamente",
  "data": {
    "urlservice": "https://..." // URL opcional para abrir después
  }
}
```

## 🎨 Componentes Principales

### 1. BalconServicios.svelte

Componente principal que coordina todos los subcomponentes.

**Props:** Ninguno (carga datos al montar)

**Eventos:** Ninguno (maneja internamente las acciones)

### 2. Menu.svelte

Menú lateral con acordeón de categorías y procesos.

**Props:**
- `eCategorias` - Array de categorías con sus procesos

**Eventos:**
- `actionRun` - Dispara cuando se selecciona un ítem
  ```javascript
  { action: 'selectItem', data: { item: procesoId } }
  ```

### 3. CarruselInfo.svelte

Muestra información de servicios o un carrusel informativo.

**Props:**
- `eInformationsServices` - Array de servicios a mostrar

**Eventos:**
- `actionRun` - Dispara acciones de solicitud
  ```javascript
  { action: 'openRequestService', data: { item: servicio } }
  ```

### 4. Formulario.svelte

Formulario para crear solicitudes con subida de archivos.

**Props:**
- `eService` - Objeto del servicio seleccionado
- `eRequirements` - Objeto con requisitos del servicio
- `eListaSolicitudes` - Lista de solicitudes relacionadas

**Eventos:**
- `actionRun` - Dispara al cerrar o limpiar
  ```javascript
  { action: 'closeFormularioService' | 'cleanFormularioService', data: { item: serviceId } }
  ```

### 5. SolicitudesInfo.svelte

Panel lateral que muestra el estado de solicitudes.

**Props:**
- `eSolicitudes` - Objeto con arrays de solicitudes por estado

## 🔧 Stores y Utilidades

### Stores

#### loadingStore
```javascript
import { loading } from './lib/stores/loadingStore.js';

// Mostrar loading
loading.setLoading(true, 'Cargando datos...');

// Ocultar loading
loading.setLoading(false);
```

#### toastStore
```javascript
import { addToast } from './lib/stores/toastStore.js';

addToast({
  type: 'success',  // 'success', 'error', 'warning', 'info'
  header: 'Éxito',
  body: 'Operación completada',
  duration: 3000
});
```

#### notificationStore
```javascript
import { addNotification } from './lib/stores/notificationStore.js';

addNotification({
  msg: 'Mensaje importante',
  type: 'warning',
  duration: 5000
});
```

### Utilidades de Peticiones

```javascript
import { apiGET, apiPOST, apiPOSTFormData } from './lib/utils/requestUtils.js';

// GET request
const [data, errors] = await apiGET(fetch, 'endpoint', { param: 'value' });

// POST JSON
const [data, errors] = await apiPOST(fetch, 'endpoint', { key: 'value' });

// POST FormData
const formData = new FormData();
formData.append('file', file);
const [data, errors] = await apiPOSTFormData(fetch, 'endpoint', formData);
```

## 🎨 Personalización de Estilos

Los colores principales del sistema están definidos en los componentes:

- **Azul primario**: `#12216A`
- **Azul secundario**: `#0A4985`
- **Azul claro**: `#253CA6`
- **Naranja acento**: `#FF9900`
- **Fondo claro**: `#F5F6F8`
- **Fondo tarjetas**: `#EEF3FC`

Para cambiar los colores, edita los archivos `.svelte` en `lib/balcon/`.

## 📦 Imágenes Requeridas

El sistema necesita las siguientes imágenes:

```
public/assets/images/background/
├── balcon_info_1.png  # Imagen 1 del carrusel (recomendado: 800x400px)
└── balcon_info_2.png  # Imagen 2 del carrusel (recomendado: 800x400px)
```

## 🔀 Alternancia de Vistas

El componente `App.svelte` permite alternar entre:

1. **Balcón de Servicios** - Sistema completo de solicitudes
2. **Asistente Virtual** - Chatbot RAG original

Para cambiar la vista por defecto, modifica en `App.svelte`:

```javascript
let currentView = 'balcon'; // o 'chatbot'
```

## 🐛 Troubleshooting

### Error: Cannot find module 'sveltestrap'

```bash
npm install sveltestrap --legacy-peer-deps
```

### FilePond no muestra estilos

Verifica que en `main.js` estén importados los estilos:

```javascript
import 'filepond/dist/filepond.min.css';
```

### Errores de CORS

Asegúrate de que el backend Django tenga configurado CORS correctamente:

```python
# settings.py
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_ALLOW_ALL = True  # Solo para desarrollo
```

## 📝 Notas para el Backend

El backend Django debe:

1. Implementar el endpoint `/alumno/balcon_servicios` (GET y POST)
2. Manejar subida de archivos con FormData
3. Retornar respuestas en formato JSON con estructura `{ isSuccess, data, message }`
4. Implementar autenticación de sesión (`credentials: 'same-origin'`)
5. Configurar CSRF para peticiones POST

## 🚀 Producción

Para compilar para producción:

```bash
npm run build
```

Los archivos compilados estarán en `dist/` y deben ser servidos por Django usando `django-vite`.

## 📚 Referencias

- [Svelte Docs](https://svelte.dev/docs)
- [SvelteStrap](https://sveltestrap.js.org/)
- [FilePond](https://pqina.nl/filepond/)
- [Bootstrap Icons](https://icons.getbootstrap.com/)

---

**Versión:** 1.0.0  
**Fecha:** Noviembre 2024  
**Autor:** Sistema adaptado de alu_solicitudbalcon


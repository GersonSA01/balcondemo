<script>
  // Inicializar con saludo genérico dinámico
  let messages = [
    { who: "bot", text: "¡Hola! 👋 Cuéntame tu solicitud en lenguaje natural y te guío al trámite correcto." }
  ];
  let input = "";
  let sending = false;
  let currentCategory = null;
  let currentSubcategory = null;
  let studentData = null;
  let profileType = "estudiante";
  let profileId = null;
  let needsConfirmation = false;
  let needsRelatedRequestSelection = false;
  let relatedRequests = [];
  let selectedRelatedRequestId = "none"; // ID de la solicitud relacionada seleccionada (por defecto "none")
  let abortController = null;
  let conversationBlocked = false; // Flag para bloquear conversación después de handoff automático
  let needsHandoffFile = false; // Flag para mostrar input de archivo
  let selectedFile = null; // Archivo seleccionado
  let fileInputRef = null; // Referencia al input de archivo
  let thinkingStatus = "Pensando"; // Estado dinámico del mensaje de pensamiento
  let thinkingInterval = null; // Intervalo para actualizar el estado dinámico
  let thinkingKey = 0; // Key para forzar re-render y animación suave
  
  // Función exportada para recibir categoría desde el padre
  export function selectCategory(category, subcategory, dataEstudiante = null, newProfileType = null, profileMeta = null) {
    currentCategory = category;
    currentSubcategory = subcategory;
    if (newProfileType) {
      profileType = newProfileType;
    }
    if (dataEstudiante !== undefined) {
      studentData = dataEstudiante;
    }
    if (profileMeta && profileMeta.profileId) {
      profileId = profileMeta.profileId;
    }
    
    const greeting = generateDynamicGreeting(category, subcategory, studentData);
    messages = [{ who: "bot", text: greeting }];
    conversationBlocked = false; // Resetear bloqueo
    needsConfirmation = false;
    needsRelatedRequestSelection = false;
    relatedRequests = [];
    selectedRelatedRequestId = "none";
    
    queueMicrotask(() => {
      const el = document.getElementById("chat-body-inline");
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  export function updateProfileContext(newProfileType = "estudiante", data = null, profileMeta = null) {
    profileType = newProfileType || "estudiante";
    if (data !== null) {
      studentData = data;
    }
    if (profileMeta && profileMeta.profileId) {
      profileId = profileMeta.profileId;
    }
  }

  function generateDynamicGreeting(category, subcategory, dataEstudiante = null) {
    let nombreFuente = dataEstudiante?.credenciales?.nombre_completo;
    if (!nombreFuente && dataEstudiante?.datos_personales) {
      const partes = [
        dataEstudiante.datos_personales.nombres || "",
        dataEstudiante.datos_personales.apellido_paterno || ""
      ].filter(Boolean);
      nombreFuente = partes.join(" ").trim();
    }
    const nombreEstudiante = nombreFuente ? nombreFuente.split(" ")[0] : "";
    const saludo = nombreEstudiante ? `¡Hola ${nombreEstudiante}! 👋` : "¡Hola! 👋";
    
    const greetings = {
      "Academico": {
        "Matriculación": `${saludo} Veo que necesitas ayuda con tu Matriculación. Estoy aquí para guiarte en todo el proceso. ¿Qué necesitas saber?`,
        "Cambio de paralelo": `${saludo} Te ayudaré con tu solicitud de Cambio de paralelo. ¿En qué asignatura necesitas el cambio?`,
        "Cupos por asignatura": `${saludo} Entiendo que necesitas información sobre Cupos por asignatura. ¿De qué materia necesitas conocer la disponibilidad?`,
        "Titulación": `${saludo} ¡Qué emocionante! Estás en el proceso de Titulación. ¿En qué puedo asistirte?`,
        "Rectificación de actividades": `${saludo} Te ayudaré con la Rectificación de actividades. Cuéntame qué necesitas rectificar.`,
        "Recalificación de actividad": `${saludo} Veo que necesitas una Recalificación de actividad. ¿De qué asignatura y actividad se trata?`,
        "Cambio de carrera": `${saludo} Te guiaré en tu proceso de Cambio de carrera. ¿A qué carrera deseas cambiarte?`,
        "Reubicación de salón": `${saludo} Te ayudaré con la Reubicación de salón. ¿Qué situación se te presenta?`,
        "Cambio de ies": `${saludo} Entiendo que estás considerando un Cambio de IES. ¿En qué puedo ayudarte?`
      },
      "Bienestar estudiantil": {
        "Servicio médico": `${saludo} Te guiaré con el Servicio médico. ¿Qué consulta necesitas realizar?`,
        "Servicio psicológico": `${saludo} Bienvenido/a al Servicio psicológico. Estoy aquí para orientarte. ¿Cómo puedo ayudarte?`,
        "Servicio de nutrición": `${saludo} Te ayudaré con el Servicio de nutrición. ¿Qué información necesitas?`,
        "Servicio de trabajo social": `${saludo} Estoy aquí para guiarte con el Servicio de trabajo social. ¿En qué puedo asistirte?`,
        "Beca estudiantil": `${saludo} Te ayudaré con tu solicitud de Beca estudiantil. ¿Qué necesitas saber sobre las becas disponibles?`,
        "Cobertura seguro estudiantil": `${saludo} Te orientaré sobre la Cobertura del seguro estudiantil. ¿Qué consulta tienes?`,
        "Gestión de inclusión y equidad académica": `${saludo} Estoy aquí para ayudarte con Gestión de inclusión y equidad académica. ¿Cómo puedo apoyarte?`,
        "Reportar acoso, discriminación o violencia": `${saludo} Tu bienestar es importante. Estoy aquí para guiarte en cómo Reportar acoso, discriminación o violencia. ¿Qué necesitas?`
      },
      "Consultas varias": {
        "Consultas varias": `${saludo} Estoy aquí para ayudarte con tus Consultas varias. ¿Qué información necesitas?`
      },
      "Financiero": {
        "Valores a cancelar": `${saludo} Te ayudaré con información sobre los Valores a cancelar. ¿Qué necesitas saber?`,
        "Notas de crédito": `${saludo} Te guiaré con el proceso de Notas de crédito. ¿Qué consulta tienes?`
      },
      "Idiomas/ofimatica": {
        "Homologacion módulos ingles": `${saludo} Te ayudaré con la Homologación de módulos de inglés. ¿Qué información necesitas?`,
        "Homologacion módulos de computacion": `${saludo} Te guiaré en la Homologación de módulos de computación. ¿Qué necesitas saber?`,
        "Inscripción a prueba de suficiencia": `${saludo} Te orientaré sobre la Inscripción a prueba de suficiencia. ¿Cómo puedo ayudarte?`,
        "Inscripción a módulos": `${saludo} Te ayudaré con la Inscripción a módulos. ¿Qué módulo te interesa?`,
        "Servicio de biblioteca física y digital": `${saludo} Te guiaré sobre el Servicio de biblioteca física y digital. ¿Qué necesitas?`
      },
      "Vinculación": {
        "Practicas preprofesionales": `${saludo} Te ayudaré con tus Prácticas preprofesionales. ¿Qué información necesitas?`,
        "Proyectos de servicios comunitarios": `${saludo} Te guiaré en los Proyectos de servicios comunitarios. ¿Cómo puedo asistirte?`,
        "Actividades extracurriculares": `${saludo} Te orientaré sobre las Actividades extracurriculares. ¿Qué te interesa saber?`
      }
    };

    // Buscar saludo específico
    if (greetings[category] && greetings[category][subcategory]) {
      return greetings[category][subcategory];
    }

    // Saludo genérico con categoría y subcategoría
    return `${saludo} Veo que necesitas ayuda con ${subcategory} en ${category}. Estoy aquí para guiarte. ¿Qué necesitas saber?`;
  }

  function formatHistoryForBackend() {
    return messages.map(m => ({
      who: m.who,
      text: m.text,
      role: m.who === "bot" ? "bot" : "user",
      content: m.text,
      meta: m.meta
    }));
  }

  function cancelRequest() {
    if (abortController) {
      abortController.abort();
      messages = [...messages, { who:"bot", text:"⚠️ Pensamiento interrumpido por el usuario." }];
      sending = false;
      abortController = null;
      queueMicrotask(() => {
        const el = document.getElementById("chat-body-inline");
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }

  // Manejo de selección de solicitud relacionada
  async function selectRelatedRequest(requestId = null){
    sending = true;
    needsRelatedRequestSelection = false;
    selectedRelatedRequestId = "none"; // Resetear selección
    abortController = new AbortController();
    
    // Después de seleccionar solicitud relacionada, buscar en documentos
    startDocumentSearch();
    
    const response = requestId ? requestId : "no hay solicitud relacionada";
    
    let userMessage = "No hay solicitud relacionada";
    if (requestId) {
      const selectedReq = relatedRequests.find(req => req.id === requestId);
      if (selectedReq) {
        userMessage = selectedReq.display || `Solicitud ${requestId}`;
    } else {
        userMessage = `Solicitud ${requestId}`;
      }
    }
    messages = [...messages, { who:"user", text: userMessage }];
    queueMicrotask(() => {
      const el = document.getElementById("chat-body-inline");
      if (el) el.scrollTop = el.scrollHeight;
    });
    
    try{
      const history = formatHistoryForBackend();
      const requestBody = { 
        message: response,
        history: history
      };
      
      if (currentCategory && currentSubcategory) {
        requestBody.category = currentCategory;
        requestBody.subcategory = currentSubcategory;
      }
      
        if (studentData) {
          requestBody.student_data = studentData;
        }
        if (profileType) {
          requestBody.profile_type = profileType;
        }
        if (profileId) {
          requestBody.perfil_id = profileId;
        }
      
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      });
      const data = await res.json();
      
      // Actualizar el estado de pensamiento según la respuesta del backend
      if (data.thinking_status) {
        stopThinkingStatusUpdate();
        thinkingStatus = data.thinking_status;
      } else if (data.needs_handoff_details || data.handoff_sent) {
        // Si es handoff, mantener el mensaje establecido (ya se estableció antes en send())
        stopThinkingStatusUpdate();
        if (data.handoff_sent) {
          thinkingStatus = "Enviando solicitud a mis compañeros humanos";
        }
      } else {
        stopThinkingStatusUpdate();
        if (data.needs_related_request_selection) {
          startRelatedRequestsSearch();
        } else if (data.has_information || data.source_pdfs || data.fuentes) {
          startDocumentSearch();
        }
      }
      
      // Priorizar response (formato PrivateGPT) sobre message (formato legacy)
      const reply = data.response || data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];
      
      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
        selectedRelatedRequestId = "none"; // Resetear selección a "No hay solicitud relacionada" cuando se reciben nuevas solicitudes
      }
      
      // Detectar si se necesita más detalles de handoff (para solicitudes relacionadas también)
      if (data.needs_handoff_details) {
        conversationBlocked = false;
        needsHandoffFile = data.needs_handoff_file || false;
      } else {
        needsHandoffFile = false;
        selectedFile = null;
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      // Si se envió el handoff exitosamente, limpiar
      if (data.handoff_sent) {
        needsHandoffFile = false;
        selectedFile = null;
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      if (data.confirmed && data.category && data.subcategory) {
        currentCategory = data.category;
        currentSubcategory = data.subcategory;
      }
    }catch(e){
      if (e.name === 'AbortError') return;
      messages = [...messages, { who:"bot", text:"Ocurrió un problema al procesar tu solicitud." }];
    }finally{
      sending = false;
      thinkingStatus = "Pensando"; // Resetear al estado por defecto
      stopThinkingStatusUpdate(); // Asegurar que se detenga el intervalo
      abortController = null;
      queueMicrotask(() => {
        const el = document.getElementById("chat-body-inline");
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }


  async function send(){
    const text = input.trim();
    if (!text || sending) return;
    
    // Validar que si se requiere archivo, esté seleccionado
    if (needsHandoffFile && !selectedFile) {
      alert("Por favor, sube un archivo PDF o imagen antes de enviar tu solicitud.");
      return;
    }
    
    messages = [...messages, { who:"user", text }];
    input = "";
    sending = true;
    abortController = new AbortController();
    
    // Si está enviando handoff con archivo, mostrar mensaje de envío
    if (needsHandoffFile && selectedFile) {
      thinkingKey += 1;
      thinkingStatus = "Enviando solicitud a mis compañeros humanos";
      stopThinkingStatusUpdate(); // Detener cualquier actualización anterior
    } else {
      // Iniciar con interpretación de intención
      startIntentParsing();
    }
    
    await processMessage(text);
    
    // Detener actualización dinámica
    stopThinkingStatusUpdate();
  }
  
  // Función para interpretar intención - solo muestra "Entendiendo el requerimiento del usuario"
  function startIntentParsing() {
    thinkingKey += 1; // Forzar re-render para animación suave
    thinkingStatus = "Entendiendo el requerimiento del usuario";
    // No necesita intervalo, solo un estado
  }
  
  // Función para buscar solicitudes relacionadas - muestra dos estados
  function startRelatedRequestsSearch() {
    let elapsed = 0;
    thinkingInterval = setInterval(() => {
      elapsed += 1;
      thinkingKey += 1; // Forzar re-render para animación suave
      if (elapsed < 3) {
        thinkingStatus = "Analizando tus solicitudes anteriores";
      } else {
        thinkingStatus = "Buscando coincidencias";
      }
    }, 1000);
  }
  
  // Función para buscar en documentos (RAG) - alterna entre dos estados (por tiempo)
  function startDocumentSearch() {
    let elapsed = 0;
    thinkingInterval = setInterval(() => {
      elapsed += 1;
      thinkingKey += 1; // Forzar re-render para animación suave
      // Alternar entre los dos estados cada 3 segundos para que no sea tan repetitivo
      const ragStates = ["Buscando documentos", "Leyendo para dar una mejor respuesta"];
      const index = Math.floor(elapsed / 3) % ragStates.length;
      thinkingStatus = ragStates[index];
    }, 1000);
  }
  
  // Función genérica (mantener por compatibilidad, pero no se usará)
  function startThinkingStatusUpdate() {
    // Por defecto, usar búsqueda de documentos
    startDocumentSearch();
  }
  
  function stopThinkingStatusUpdate() {
    if (thinkingInterval) {
      clearInterval(thinkingInterval);
      thinkingInterval = null;
    }
  }

  async function processMessage(text) {
    
    try {
      const history = formatHistoryForBackend();
      
      // Si hay archivo seleccionado, usar FormData; si no, JSON normal
      let requestBody;
      let headers = {};
      let body;
      
      if (selectedFile && needsHandoffFile) {
        // Usar FormData para enviar archivo
        const formData = new FormData();
        formData.append("message", text);
        formData.append("history", JSON.stringify(history));
        formData.append("file", selectedFile);
        
        if (currentCategory && currentSubcategory) {
          formData.append("category", currentCategory);
          formData.append("subcategory", currentSubcategory);
        }
        
        if (studentData) {
          formData.append("student_data", JSON.stringify(studentData));
        }
        if (profileType) {
          formData.append("profile_type", profileType);
        }
        if (profileId) {
          formData.append("perfil_id", profileId);
        }
        
        body = formData;
        // No establecer Content-Type, el navegador lo hace automáticamente con el boundary
      } else {
        // Usar JSON normal
        requestBody = { 
          message: text,
          history: history
        };
        
        if (currentCategory && currentSubcategory) {
          requestBody.category = currentCategory;
          requestBody.subcategory = currentSubcategory;
        }
        
        if (studentData) {
          requestBody.student_data = studentData;
        }
        
        if (profileType) {
          requestBody.profile_type = profileType;
        }
        
        headers["Content-Type"] = "application/json";
        body = JSON.stringify(requestBody);
      }
      
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: headers,
        body: body,
        signal: abortController.signal
      });
      const data = await res.json();
      
      // Actualizar el estado de pensamiento según la respuesta del backend
      // Si el backend envía thinking_status, usarlo directamente
      if (data.thinking_status) {
        stopThinkingStatusUpdate(); // Detener cualquier actualización anterior
        thinkingStatus = data.thinking_status;
      } else {
        // Si no viene thinking_status, detectar según el tipo de respuesta
        stopThinkingStatusUpdate(); // Detener cualquier actualización anterior
        
        if (data.needs_related_request_selection) {
          // Si necesita selección de solicitudes relacionadas, usar esa función
          startRelatedRequestsSearch();
        } else if (data.has_information || data.source_pdfs || data.fuentes) {
          // Si tiene información o fuentes, está buscando en documentos
          startDocumentSearch();
        }
        // Si necesita confirmación, mantener "Entendiendo el requerimiento del usuario"
      }
      
      // Priorizar response (formato PrivateGPT) sobre message (formato legacy)
      const reply = data.response || data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];
      
      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
        selectedRelatedRequestId = "none"; // Resetear selección a "No hay solicitud relacionada" cuando se reciben nuevas solicitudes
      }
      
      // Detectar handoff enviado y cerrar chat
      if (data.handoff_sent && data.close_chat) {
        // Bloquear la conversación inmediatamente
        conversationBlocked = true;
        // El mensaje ya se mostró, el chat está bloqueado
      }
      
      // Detectar si se necesita más detalles de handoff (para deshabilitar el bloqueo)
      if (data.needs_handoff_details) {
        conversationBlocked = false; // Asegurar que el input esté habilitado
        needsHandoffFile = data.needs_handoff_file || false; // Detectar si se requiere archivo
        // Si se requiere archivo, asegurarse de que el input esté visible desde el primer mensaje
        if (needsHandoffFile && !selectedFile) {
          // El input ya debería estar visible por el {#if needsHandoffFile} en el template
        }
      } else {
        needsHandoffFile = false; // Resetear cuando no se necesita
        selectedFile = null; // Limpiar archivo seleccionado
        // Limpiar input de archivo si existe
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      // Si se envió el handoff exitosamente, limpiar el archivo y ocultar el input
      if (data.handoff_sent) {
        needsHandoffFile = false; // Ocultar input de archivo
        selectedFile = null;
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      if (data.confirmed && data.category && data.subcategory) {
        currentCategory = data.category;
        currentSubcategory = data.subcategory;
      } else if (data.confirmed === false) {
        currentCategory = null;
        currentSubcategory = null;
      }
    } catch(e) {
      if (e.name === 'AbortError') return;
      messages = [...messages, { who:"bot", text:"Ocurrió un problema al procesar tu solicitud." }];
    } finally {
      sending = false;
      thinkingStatus = "Pensando"; // Resetear al estado por defecto
      stopThinkingStatusUpdate(); // Asegurar que se detenga el intervalo
      abortController = null;
      queueMicrotask(() => {
        const el = document.getElementById("chat-body-inline");
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }

  function handleKey(e){
    if (e.key === "Enter" && !e.shiftKey){
      e.preventDefault();
      send();
    }
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) {
      // Validar tamaño (4MB = 4 * 1024 * 1024 bytes)
      const maxSize = 4 * 1024 * 1024;
      if (file.size > maxSize) {
        alert(`El archivo es demasiado grande. El tamaño máximo es 4MB. Tu archivo tiene ${(file.size / 1024 / 1024).toFixed(2)}MB.`);
        e.target.value = ""; // Limpiar input
        selectedFile = null;
        return;
      }
      // Validar tipo de archivo
      const allowedTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
      if (!allowedTypes.includes(file.type)) {
        alert('Tipo de archivo no permitido. Solo se aceptan PDF, JPG, JPEG o PNG.');
        e.target.value = ""; // Limpiar input
        selectedFile = null;
        return;
      }
      selectedFile = file;
    }
  }

  async function confirmUser(confirmed){
    sending = true;
    needsConfirmation = false;
    const response = confirmed ? "si" : "no";
    abortController = new AbortController();
    
    // Si el usuario confirma, iniciar búsqueda de solicitudes relacionadas
    if (confirmed) {
      startRelatedRequestsSearch();
    } else {
      // Si rechaza, volver a interpretar intención
      startIntentParsing();
    }
    
    messages = [...messages, { who:"user", text: response }];
    queueMicrotask(() => {
      const el = document.getElementById("chat-body-inline");
      if (el) el.scrollTop = el.scrollHeight;
    });
    
    try{
      const history = formatHistoryForBackend();
      const requestBody = { 
        message: response,
        history: history
      };
      
      if (currentCategory && currentSubcategory) {
        requestBody.category = currentCategory;
        requestBody.subcategory = currentSubcategory;
      }
      
        if (studentData) {
          requestBody.student_data = studentData;
        }
        if (profileType) {
          requestBody.profile_type = profileType;
        }
        if (profileId) {
          requestBody.perfil_id = profileId;
        }
      
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      });
      const data = await res.json();
      
      // Actualizar el estado de pensamiento según la respuesta del backend
      if (data.thinking_status) {
        stopThinkingStatusUpdate();
        thinkingStatus = data.thinking_status;
      } else {
        stopThinkingStatusUpdate();
        if (data.needs_related_request_selection) {
          startRelatedRequestsSearch();
        } else if (data.has_information || data.source_pdfs || data.fuentes) {
          startDocumentSearch();
        }
      }
      
      // Priorizar response (formato PrivateGPT) sobre message (formato legacy)
      const reply = data.response || data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];

      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
        selectedRelatedRequestId = "none"; // Resetear selección a "No hay solicitud relacionada" cuando se reciben nuevas solicitudes
      }
      
      // Detectar si se necesita más detalles de handoff (para confirmaciones también)
      if (data.needs_handoff_details) {
        conversationBlocked = false;
        needsHandoffFile = data.needs_handoff_file || false;
      } else {
        needsHandoffFile = false;
        selectedFile = null;
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      // Si se envió el handoff exitosamente, limpiar
      if (data.handoff_sent) {
        needsHandoffFile = false;
        selectedFile = null;
        if (fileInputRef) {
          fileInputRef.value = "";
        }
      }
      
      if (data.confirmed && data.category && data.subcategory) {
        currentCategory = data.category;
        currentSubcategory = data.subcategory;
      }
    }catch(e){
      if (e.name === 'AbortError') return;
      messages = [...messages, { who:"bot", text:"Ocurrió un problema al procesar tu solicitud." }];
    }finally{
      sending = false;
      abortController = null;
      queueMicrotask(() => {
        const el = document.getElementById("chat-body-inline");
        if (el) el.scrollTop = el.scrollHeight;
      });
    }
  }


</script>

<div class="chat-inline-container">
  <!-- Header del chat -->
  <div class="chat-header">
    <div style="display:flex; align-items:center; flex:1;">
      <span class="header-title">
        {#if currentCategory && currentSubcategory}
          {currentCategory} > {currentSubcategory}
        {:else if currentSubcategory}
          {currentSubcategory}
        {:else if currentCategory}
          {currentCategory}
        {:else}
          Asistente Virtual
        {/if}
      </span>
    </div>
  </div>

  <!-- Cuerpo del chat -->
  <div id="chat-body-inline" class="chat-body">
    {#each messages as m, idx}
      <div class="msg {m.who}">
        <div class="bubble">
          {#if m.who === "bot" && m.meta?.needs_related_request_selection && m.meta?.related_requests && m.meta.related_requests.length > 0}
            <!-- Formato mejorado para solicitudes relacionadas -->
            <div class="related-requests-container">
              <div class="related-requests-intro">{m.text.split('\n')[0]}</div>
              <div class="related-requests-list">
                {#each m.meta.related_requests as req, index}
                  {@const fecha = req.fecha_formateada || ''}
                  {@const descripcion = (req.descripcion || '').trim()}
                  {@const codigo = req.codigo || req.codigo_generado || `Solicitud ${req.id}`}
                  <div class="related-request-item">
                    <div class="related-request-header">
                      <span class="related-request-title">{index + 1}. {codigo}</span>
                      {#if fecha}
                        <span class="related-request-date">{fecha}</span>
                      {/if}
                    </div>
                    {#if descripcion}
                      <div class="related-request-description">{descripcion}</div>
                    {/if}
                  </div>
                {/each}
              </div>
              <div class="related-requests-footer">
                ¿Deseas relacionar tu solicitud actual con alguna de estas? Si ninguna es relevante, puedes continuar sin relacionar.
              </div>
            </div>
          {:else}
            <div class="message-text">{m.text}</div>
          {/if}
          
          {#if m.who === "bot" && m.meta?.fuentes && m.meta.fuentes.length > 0}
            <div class="pdf-sources">
              <div class="pdf-sources-label">📄 Fuentes consultadas:</div>
              {#each m.meta.fuentes as fuente}
                {@const archivo = fuente.archivo || fuente.file_name || ''}
                {@const paginas = fuente.paginas || (fuente.pagina ? [fuente.pagina] : [])}
                {@const archivoNombre = archivo.split('/').pop().replace('.pdf', '').replace(/_/g, ' ')}
                <div class="pdf-source-item">
                  <a 
                    href="/api/pdf/{archivo}" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    class="pdf-link"
                  >
                    {archivoNombre}
                  </a>
                  {#if paginas.length > 0}
                    <span class="pdf-pages">
                      {paginas.length === 1 ? `(página ${paginas[0]})` : `(páginas ${paginas.join(', ')})`}
                    </span>
                  {/if}
                </div>
              {/each}
            </div>
          {:else if m.who === "bot" && m.meta?.source_pdfs && m.meta.source_pdfs.length > 0}
            <div class="pdf-sources">
              <div class="pdf-sources-label">📄 Fuentes consultadas:</div>
              {#each m.meta.source_pdfs as pdfPath}
                <a 
                  href="/api/pdf/{pdfPath}" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  class="pdf-link"
                >
                  {pdfPath.split('/').pop().replace('.pdf', '').replace(/_/g, ' ')}
                </a>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    {/each}

    <!-- Mensaje de "Pensando..." -->
    {#if sending}
      <div class="msg bot">
        <div class="bubble thinking-bubble">
          <div class="processing-text">
            {#key thinkingKey}
              <span class="thinking-text">{thinkingStatus}<span class="dots">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
              </span></span>
            {/key}
          </div>
        </div>
      </div>
    {/if}
  </div>

  <!-- Input del chat -->
  <div class="chat-input">
      {#if conversationBlocked}
        <!-- Conversación bloqueada después de handoff -->
        <div class="input-row">
          <textarea rows="2" value="" disabled
            placeholder="Tu solicitud ha sido enviada. Mantente atento a la respuesta."></textarea>
          <button class="send-btn" disabled>
            Enviado
          </button>
        </div>
        <div class="blocked-notice">
          ✅ Tu solicitud fue enviada exitosamente. Un agente se pondrá en contacto contigo pronto.
        </div>
      {:else if needsConfirmation}
        <div class="input-row">
          <textarea rows="2" value="" disabled
            placeholder="Por favor confirma tu solicitud"></textarea>
        </div>
        <div class="confirmation-buttons">
          <button class="confirm-btn yes" on:click={() => confirmUser(true)} disabled={sending}>
            Sí
          </button>
          <button class="confirm-btn no" on:click={() => confirmUser(false)} disabled={sending}>
            No
          </button>
        </div>
    {:else if needsRelatedRequestSelection}
      <!-- Mostrar select de selección de solicitudes relacionadas -->
      <div class="related-request-selection-container">
        <select 
          bind:value={selectedRelatedRequestId}
          disabled={sending}
          class="related-request-select">
          <option value="none">No hay solicitud relacionada</option>
          {#each relatedRequests as req, index}
            <option value={req.id}>
              {req.codigo || req.codigo_generado || req.id}
            </option>
          {/each}
        </select>
        <button 
          class="related-request-submit-btn" 
          on:click={() => {
            if (selectedRelatedRequestId === "none") {
              selectRelatedRequest(null);
            } else if (selectedRelatedRequestId) {
              // Convertir a número si es posible, sino mantener como string
              const requestId = isNaN(selectedRelatedRequestId) 
                ? selectedRelatedRequestId 
                : parseInt(selectedRelatedRequestId, 10);
              selectRelatedRequest(requestId);
            }
          }}
          disabled={sending}>
          Continuar
        </button>
      </div>
    {:else}
        <div class="input-row">
          <textarea rows="2" bind:value={input}
            placeholder="Escribe tu mensaje..."
            on:keydown={handleKey}
            disabled={sending}></textarea>
          <div class="input-actions">
            {#if needsHandoffFile}
              <label for="handoff-file-input" class="file-upload-btn" title="Subir archivo">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="17 8 12 3 7 8"></polyline>
                  <line x1="12" y1="3" x2="12" y2="15"></line>
                </svg>
              </label>
              <input
                id="handoff-file-input"
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                bind:this={fileInputRef}
                on:change={handleFileSelect}
                disabled={sending}
                class="file-input"
              />
            {/if}
            <button class="send-btn-icon" on:click={send} disabled={sending || (needsHandoffFile && !selectedFile)} title="Enviar">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
        {#if needsHandoffFile && selectedFile}
          <div class="file-selected-info">
            <span>✓ {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)}MB)</span>
            <button class="remove-file-btn-small" on:click={() => { selectedFile = null; if (fileInputRef) fileInputRef.value = ""; }}>
              ✕
            </button>
          </div>
        {/if}
      {/if}

      {#if sending && !conversationBlocked}
        <div class="processing-indicator" aria-live="polite">
          <button class="cancel-btn" on:click={cancelRequest}>
            Cancelar
          </button>
        </div>
    {/if}
  </div>
</div>

<style>

:root{
  /* Paleta del SGA/ECampus */
  --navy-900:#0f2a57;
  --blue-100:#e6f0ff;
  --blue-500:#1b66d1;
  --orange-500:#1b66d1;
  --orange-600:#0f4a8f;
  --gray-050:#f6f7fb;
  --gray-200:#e4e7ee;
  --gray-500:#6d7382;
  --white:#fff;
}

/* Contenedor inline del chat */
.chat-inline-container{
  background:var(--white);
  border:1px solid var(--gray-200);
  border-radius:22px;
  box-shadow:0 10px 30px rgba(20,35,70,.06);
  display:flex; flex-direction:column;
  height:600px; overflow:hidden;
}

/* Header */
.chat-header{
  display:flex; align-items:center; justify-content:space-between;
  background:#0f2a57; color:#fff;
  padding:14px 20px; font-weight:700; letter-spacing:.2px;
  border-radius:22px 22px 0 0;
}
.header-title{font-size:1.1rem; color:#fff}

/* Body */
.chat-body{
  background:
    radial-gradient(1200px 200px at 50% -80px, rgba(27,102,209,.08), transparent 60%),
    linear-gradient(180deg,#ffffff,#f6f9ff);
  flex:1; overflow:auto; padding:16px;
}
.chat-body::-webkit-scrollbar{width:8px}
.chat-body::-webkit-scrollbar-thumb{background:#dde3ea; border-radius:10px}

/* Mensajes */
.msg{display:flex; margin:10px 0}
.msg .bubble{
  max-width:75%;
  padding:12px 14px;
  border-radius:14px;
  border:1px solid var(--gray-200);
  background:#fff;
  line-height:1.45; word-break:break-word;
}
.message-text{
  white-space:pre-line;
}

/* Usuario = azul oscuro */
.msg.user{justify-content:flex-end}
.msg.user .bubble{
  background:#1b66d1;
  color:#fff;
  border-color:#1b66d1;
}
.msg.user .message-text{
  color:#fff;
}

/* Bot = blanco/gris claro */
.msg.bot .bubble{
  background:#fff;
  border-color:#e4e7ee;
  color:#0f2136;
}

/* Select de solicitudes relacionadas */
.related-request-selection-container{
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.related-request-select{
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 500;
  background: #fff;
  color: #0f2136;
  cursor: pointer;
  transition: all 0.2s;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%230f2136' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 40px;
}
.related-request-select:hover{
  border-color: #1b66d1;
  background-color: #f6f7fb;
}
.related-request-select:focus{
  outline: none;
  border-color: #1b66d1;
  box-shadow: 0 0 0 2px rgba(27,102,209,.1);
}
.related-request-select:disabled{
  opacity: 0.5;
  cursor: not-allowed;
  background-color: #f6f7fb;
}
.related-request-submit-btn{
  width: 100%;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 700;
  background: #1b66d1;
  color: #fff;
  border: 0;
  cursor: pointer;
  transition: all 0.2s;
}
.related-request-submit-btn:hover:not(:disabled){
  background: #0f4a8f;
}
.related-request-submit-btn:disabled{
  opacity: 0.5;
  cursor: not-allowed;
}

/* Input inferior */
.chat-input{background:#fbfcff; border-top:1px solid var(--gray-200); padding:16px; border-radius:0 0 22px 22px}
.input-row{
  display:flex; 
  align-items:flex-end; 
  gap:8px; 
  margin-bottom:0;
}
.chat-input textarea{
  flex:1; 
  min-height:44px; 
  max-height:120px; 
  resize:none;
  padding:12px 14px; 
  border-radius:10px; 
  border:1px solid var(--gray-200);
  background:#fff; 
  font:inherit; 
  color:#0f2136; 
  outline:none;
  font-size:0.95rem;
  line-height:1.5;
}
.chat-input textarea:focus{
  border-color:#1b66d1;
  box-shadow:0 0 0 2px rgba(27,102,209,.1);
}
.chat-input textarea::placeholder{
  color:#6d7382;
}

.input-actions{
  display:flex; 
  align-items:flex-end; 
  gap:6px;
  height:44px;
}

.file-upload-btn{
  display:flex; 
  align-items:center; 
  justify-content:center;
  width:44px; 
  height:44px;
  border-radius:10px;
  border:1px solid var(--gray-200);
  background:#fff;
  color:#6d7382;
  cursor:pointer;
  transition:all 0.2s;
  padding:0;
  flex-shrink:0;
}
.file-upload-btn:hover{
  background:#f6f7fb;
  border-color:#1b66d1;
  color:#1b66d1;
}

.send-btn-icon{
  display:flex; 
  align-items:center; 
  justify-content:center;
  width:44px; 
  height:44px;
  border-radius:10px;
  background:#1b66d1;
  color:#fff;
  border:0;
  cursor:pointer;
  transition:all 0.2s;
  padding:0;
  flex-shrink:0;
}
.send-btn-icon:hover:not(:disabled){
  background:#0f4a8f;
}
.send-btn-icon:disabled{
  opacity:.5; 
  cursor:not-allowed;
}

.file-selected-info{
  display:flex; align-items:center; justify-content:space-between;
  padding:8px 12px;
  background:#e6f0ff;
  border:1px solid #cfe0ff;
  border-radius:8px;
  margin-bottom:12px;
  font-size:0.9rem;
  color:#0f2136;
}
.remove-file-btn-small{
  background:transparent;
  border:0;
  color:#991b1b;
  cursor:pointer;
  font-size:1rem;
  padding:0 4px;
  font-weight:700;
}
.remove-file-btn-small:hover{
  color:#dc2626;
}

/* Confirmación sí/no */
.confirmation-buttons{display:flex; gap:8px; margin-top:8px}
.confirm-btn{flex:1; padding:12px 14px; border-radius:10px; font-weight:700; cursor:pointer; border:0}
.confirm-btn.yes{background:#1b66d1; color:#fff}
.confirm-btn.yes:hover{background:#0f4a8f}
.confirm-btn.no{background:var(--gray-050); color:#0f2136; border:1px solid var(--gray-200)}
.confirm-btn.no:hover{background:#eef2f7}

/* Aviso de conversación bloqueada */
.blocked-notice{
  margin-top:10px;
  padding:10px 14px;
  border-radius:10px;
  background:#fff7ed;
  border:1px solid rgba(249,115,22,.25);
  color:#92400e;
  font-size:.9rem;
  font-weight:600;
  text-align:center;
  line-height:1.4;
}

/* Pensando… */
.thinking-bubble{display:flex; align-items:center; gap:8px}
.processing-text{display:inline-flex; align-items:center; font-weight:700; color:#0f2136}
.thinking-text{
  display:inline-flex;
  align-items:center;
  animation: textFade 0.5s ease-in-out;
}
@keyframes textFade{
  0%{opacity:0.4}
  100%{opacity:1}
}
.processing-text .dots{
  display:inline-flex;
  gap:4px;
  margin-left:8px;
  vertical-align:middle;
  align-items:center;
}
.processing-text .dot{
  width:4px;
  height:4px;
  border-radius:999px;
  background:#c96f22;
  animation:bounce 1.2s infinite ease-in-out;
  display:inline-block;
}
.processing-text .dot:nth-child(2){animation-delay:.15s}
.processing-text .dot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0); opacity:.5} 40%{transform:translateY(-4px); opacity:1}}
.processing-indicator{display:flex; justify-content:flex-end; gap:10px; margin-top:8px}
.cancel-btn{padding:6px 12px; font-size:.85rem; font-weight:700; border-radius:10px;
  background:#fee2e2; color:#991b1b; border:1px solid #fecaca; cursor:pointer}
.cancel-btn:hover{background:#fca5a5; border-color:#f87171}

/* Fuentes PDF dentro de respuestas */
.pdf-sources{margin-top:12px; padding-top:10px; border-top:1px solid #dde3ea; display:flex; flex-direction:column; gap:8px}
.pdf-sources-label{font-size:.78rem; font-weight:700; color:#0f2136; margin-bottom:4px}
.pdf-source-item{
  display:flex; align-items:center; gap:8px; flex-wrap:wrap
}
.pdf-link{
  display:inline-flex; align-items:center; font-size:.82rem; font-weight:700;
  color:#1b66d1; text-decoration:none; padding:4px 8px; border-radius:8px;
}
.pdf-link:hover{background:var(--blue-100); text-decoration:underline}
.pdf-pages{
  font-size:.75rem; color:var(--gray-500); font-style:italic
}

/* Enlaces de archivo renderizados dentro del mensaje del usuario */
.inline-file-link{color:#0f2136; font-weight:700; text-decoration:underline}
.inline-file-link:hover{color:#1b66d1}

/* Solicitudes relacionadas - Formato mejorado */
.related-requests-container{
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.related-requests-intro{
  font-size: 0.95rem;
  color: #0f2136;
  font-weight: 500;
  margin-bottom: 4px;
}
.related-requests-list{
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.related-request-item{
  background: #f8f9fa;
  border: 1px solid #e4e7ee;
  border-radius: 10px;
  padding: 12px 14px;
}
.related-request-header{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.related-request-title{
  font-weight: 700;
  font-size: 0.95rem;
  color: #0f2136;
  flex: 1;
  min-width: 200px;
}
.related-request-date{
  font-size: 0.85rem;
  color: #6d7382;
  font-weight: 500;
  white-space: nowrap;
}
.related-request-description{
  font-size: 0.9rem;
  color: #4a5568;
  line-height: 1.5;
  margin-top: 6px;
  padding-left: 4px;
  word-wrap: break-word;
}
.related-requests-footer{
  font-size: 0.9rem;
  color: #6d7382;
  font-style: italic;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid #e4e7ee;
}

/* Sección de subida de archivo */
.file-upload-section{
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f9fafb;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
}
.file-label{
  flex: 1;
  font-size: 0.9rem;
  color: #0f2136;
  cursor: pointer;
  font-weight: 600;
}
.file-input{
  display: none;
}
.file-label:hover{
  color: #1b66d1;
}
.remove-file-btn{
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 0.85rem;
  cursor: pointer;
  font-weight: 700;
}
.remove-file-btn:hover{
  background: #fca5a5;
  border-color: #f87171;
}


</style>


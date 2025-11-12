<script>
  // Inicializar con saludo genérico
  let messages = [
    { who: "bot", text: "¡Hola! 👋 Cuéntame tu solicitud en lenguaje natural y te guío al trámite correcto." }
  ];
  let input = "";
  let sending = false;
  let currentCategory = null;
  let currentSubcategory = null;
  let studentData = null;
  let needsConfirmation = false;
  let needsRelatedRequestSelection = false;
  let relatedRequests = [];
  let abortController = null;
  let conversationBlocked = false; // Flag para bloquear conversación después de handoff automático
  let needsHandoffFile = false; // Flag para mostrar input de archivo
  let selectedFile = null; // Archivo seleccionado
  let fileInputRef = null; // Referencia al input de archivo

  // Función exportada para recibir categoría desde el padre
  export function selectCategory(category, subcategory, dataEstudiante = null) {
    currentCategory = category;
    currentSubcategory = subcategory;
    studentData = dataEstudiante;
    
    const greeting = generateDynamicGreeting(category, subcategory, dataEstudiante);
    messages = [{ who: "bot", text: greeting }];
    conversationBlocked = false; // Resetear bloqueo
    needsConfirmation = false;
    needsRelatedRequestSelection = false;
    relatedRequests = [];
    
    queueMicrotask(() => {
      const el = document.getElementById("chat-body-inline");
      if (el) el.scrollTop = el.scrollHeight;
    });
  }

  function generateDynamicGreeting(category, subcategory, dataEstudiante = null) {
    const nombreEstudiante = dataEstudiante?.credenciales?.nombre_completo?.split(' ')[0] || "";
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
    abortController = new AbortController();
    
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
      
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      });
      const data = await res.json();
      const reply = data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];
      
      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
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
    
    await processMessage(text);
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
      const reply = data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];
      
      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
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
      
      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: { "Content-Type":"application/json" },
        body: JSON.stringify(requestBody),
        signal: abortController.signal
      });
      const data = await res.json();
      const reply = data.message || "No pude entenderte, ¿puedes reformular?";
      messages = [...messages, { who:"bot", text: reply, meta: data }];
      
      needsConfirmation = data.needs_confirmation || false;
      needsRelatedRequestSelection = data.needs_related_request_selection || false;
      if (data.related_requests) {
        relatedRequests = data.related_requests;
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
      <span class="status-dot"></span>
      <span class="header-title">
        {#if currentCategory && currentSubcategory}
          {currentCategory} › {currentSubcategory}
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
          <div class="message-text">{m.text}</div>
          
          {#if m.who === "bot" && m.meta?.source_pdfs && m.meta.source_pdfs.length > 0}
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
            <span>Pensando</span>
            <span class="dots">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </span>
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
      <!-- Mostrar botones de selección de solicitudes relacionadas -->
      <div class="input-row">
        <textarea rows="2" value="" disabled
          placeholder="Selecciona una solicitud relacionada"></textarea>
      </div>
      <div class="related-requests-buttons">
        {#each relatedRequests as req, index}
          <button 
            class="related-request-btn" 
            on:click={() => selectRelatedRequest(req.id)} 
            disabled={sending}>
            {index + 1}. {req.display || req.id}
          </button>
        {/each}
        <button 
          class="related-request-btn no-related" 
          on:click={() => selectRelatedRequest(null)} 
          disabled={sending}>
          No hay solicitud relacionada
        </button>
      </div>
    {:else}
        <div class="input-row">
          <textarea rows="2" bind:value={input}
            placeholder="Escribe tu solicitud…"
            on:keydown={handleKey}
            disabled={sending}></textarea>
          <button class="send-btn" on:click={send} disabled={sending || (needsHandoffFile && !selectedFile)}>
            {sending ? "..." : "Enviar"}
          </button>
        </div>
        {#if needsHandoffFile}
          <div class="file-upload-section">
            <label for="handoff-file-input" class="file-label">
              {#if selectedFile}
                ✓ {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)}MB)
              {:else}
                📎 Subir PDF o imagen (máx. 4MB)
              {/if}
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
            {#if selectedFile}
              <button class="remove-file-btn" on:click={() => { selectedFile = null; if (fileInputRef) fileInputRef.value = ""; }}>
                ✕
              </button>
            {/if}
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
  --orange-500:#ff8b2a;
  --orange-600:#e97400;
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
  background:var(--navy-900); color:#fff;
  padding:12px 16px; font-weight:700; letter-spacing:.2px;
}
.status-dot{
  width:10px; height:10px; border-radius:50%;
  background:#47d16a; margin-right:10px;
  box-shadow:0 0 0 3px rgba(71,209,106,.25);
}
.header-title{font-size:1rem}

/* Body */
.chat-body{
  background:
    radial-gradient(1200px 200px at 50% -80px, rgba(255,139,42,.08), transparent 60%),
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

/* Usuario = azul claro */
.msg.user{justify-content:flex-end}
.msg.user .bubble{
  background:var(--blue-100);
  border-color:#cfe0ff;
}

/* Bot = naranja */
.msg.bot .bubble{
  background:linear-gradient(180deg, rgba(255,139,42,.12), rgba(255,139,42,.08));
  border-color:rgba(233,148,63,.45);
}

/* Botones de solicitudes relacionadas */
.related-requests-buttons{
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 8px;
}
.related-request-btn{
  padding: 10px 14px;
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  background: #fff;
  color: #0f2136;
}
.related-request-btn:hover{
  background: #f3f5f9;
  border-color: var(--orange-500);
}
.related-request-btn.no-related{
  background: #f3f5f9;
  border-color: #e5e7eb;
  color: var(--gray-500);
}
.related-request-btn.no-related:hover{
  background: #e5e7eb;
  border-color: #d1d5db;
}
.related-request-btn:disabled{
  opacity: 0.6;
  cursor: not-allowed;
}

/* Input inferior */
.chat-input{background:#fbfcff; border-top:1px solid var(--gray-200); padding:12px}
.input-row{display:flex; align-items:flex-start; gap:10px}
.chat-input textarea{
  flex:1; min-height:44px; max-height:120px; resize:vertical;
  padding:12px 14px; border-radius:12px; border:1px solid var(--gray-200);
  background:#fff; font:inherit; color:#0f2136; outline:none;
}
.chat-input textarea:focus{border-color:var(--orange-500);
  box-shadow:0 0 0 3px rgba(255,139,42,.18)}
.send-btn{
  background:var(--orange-500); color:#fff; border:0; border-radius:12px;
  padding:12px 18px; font-weight:700; cursor:pointer;
}
.send-btn:hover:not(:disabled){background:var(--orange-600)}
.send-btn:disabled{opacity:.7; cursor:not-allowed}

/* Confirmación sí/no */
.confirmation-buttons{display:flex; gap:8px; margin-top:8px}
.confirm-btn{flex:1; padding:12px 14px; border-radius:10px; font-weight:700; cursor:pointer; border:0}
.confirm-btn.yes{background:var(--orange-500); color:#fff}
.confirm-btn.yes:hover{background:var(--orange-600)}
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
.processing-text{display:inline-flex; align-items:center; gap:8px; font-weight:700; color:#0f2136}
.processing-text .dots{display:inline-flex; gap:6px}
.processing-text .dot{width:6px; height:6px; border-radius:999px; background:#c96f22; animation:bounce 1.2s infinite ease-in-out}
.processing-text .dot:nth-child(2){animation-delay:.15s}
.processing-text .dot:nth-child(3){animation-delay:.3s}
@keyframes bounce{0%,80%,100%{transform:translateY(0); opacity:.5} 40%{transform:translateY(-4px); opacity:1}}
.processing-indicator{display:flex; justify-content:flex-end; gap:10px; margin-top:8px}
.cancel-btn{padding:6px 12px; font-size:.85rem; font-weight:700; border-radius:10px;
  background:#fee2e2; color:#991b1b; border:1px solid #fecaca; cursor:pointer}
.cancel-btn:hover{background:#fca5a5; border-color:#f87171}

/* Fuentes PDF dentro de respuestas */
.pdf-sources{margin-top:12px; padding-top:10px; border-top:1px solid #dde3ea; display:flex; flex-direction:column; gap:6px}
.pdf-sources-label{font-size:.78rem; font-weight:700; color:#0f2136}
.pdf-link{
  display:inline-flex; align-items:center; font-size:.82rem; font-weight:700;
  color:var(--orange-600); text-decoration:none; padding:4px 8px; border-radius:8px;
}
.pdf-link:hover{background:var(--blue-100); text-decoration:underline}

/* Enlaces de archivo renderizados dentro del mensaje del usuario */
.inline-file-link{color:#0f2136; font-weight:700; text-decoration:underline}
.inline-file-link:hover{color:var(--orange-600)}

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
  color: var(--orange-600);
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


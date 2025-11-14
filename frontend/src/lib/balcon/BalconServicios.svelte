<script>
    import { onMount } from 'svelte';
    import { addToast } from '../stores/toastStore.js';
    import { apiGET, browserGet, browserSet } from '../utils/requestUtils.js';
    import { loading } from '../stores/loadingStore.js';
    import Menu from './Menu.svelte';
    import SolicitudesInfo from './SolicitudesInfo.svelte';
    import ChatbotInline from '../ChatbotInline.svelte';

    // Estado
    let eCategorias = [];
    let eSolicitudes = {};
    let dataLoaded = false;
    let chatbotComponent;
    let showChatbot = false;
    let selectedCategory = null;
    let selectedSubcategory = null;

    let usuarios = [];
    let usuariosLoading = false;
    let selectedUserId = '';
    let availableProfiles = [];
    let selectedProfileId = '';
    let activeProfileMeta = null;
    let profileContext = null;
    let profileLoading = false;
    let profileDisplayName = '';
    const profileCache = new Map();
    const PROFILE_STORAGE_KEY = 'balconPerfilSeleccionado';

    function resetConversationState() {
        selectedCategory = null;
        selectedSubcategory = null;
        showChatbot = false;
    }

    async function loadUsuarios() {
        usuariosLoading = true;
        try {
            const [payload, errors] = await apiGET(fetch, 'api/usuarios/');
            if (errors.length) {
                throw new Error(errors[0]?.error || 'No se pudieron obtener los usuarios disponibles.');
            }
            usuarios = payload?.usuarios ?? [];
        } catch (error) {
            console.error('[BalconServicios] Error cargando usuarios:', error);
            addToast({
                type: 'danger',
                title: 'Error al cargar usuarios',
                description: error.message || 'No se pudo obtener el listado de usuarios de prueba.'
            });
            usuarios = [];
        } finally {
            usuariosLoading = false;
        }
    }

    function updateAvailableProfiles() {
        const usuario = usuarios.find((item) => item.cedula === selectedUserId);
        availableProfiles = usuario?.perfiles ?? [];
    }

    // Función para formatear fecha y hora desde ISO a formato legible
    function formatFechaHora(fechaISO) {
        if (!fechaISO) return { fecha: '', hora: '' };
        try {
            const fecha = new Date(fechaISO);
            const dia = String(fecha.getDate()).padStart(2, '0');
            const mes = String(fecha.getMonth() + 1).padStart(2, '0');
            const anio = fecha.getFullYear();
            const horas = String(fecha.getHours()).padStart(2, '0');
            const minutos = String(fecha.getMinutes()).padStart(2, '0');
            return {
                fecha: `${dia}/${mes}/${anio}`,
                hora: `${horas}:${minutos}`
            };
        } catch (e) {
            return { fecha: '', hora: '' };
        }
    }

    // Función para mapear estado_display a las claves del objeto eSolicitudes
    function mapEstadoToKey(estadoDisplay) {
        if (estadoDisplay === null || estadoDisplay === undefined) return null;
        
        // Convertir a string si es un número u otro tipo
        let estadoStr = String(estadoDisplay).trim();
        if (!estadoStr) return null;
        
        const estadoLower = estadoStr.toLowerCase();
        
        // Mapeo de estados comunes
        if (estadoLower.includes('trámite') || estadoLower.includes('tramite') || estadoLower === 'atendido' || estadoLower === 'ingresado') {
            return 'en_tramite';
        }
        if (estadoLower.includes('pendiente') || estadoLower === 'pendiente') {
            return 'pendiente';
        }
        if (estadoLower.includes('aprobado') || estadoLower === 'aprobado') {
            return 'aprobado';
        }
        if (estadoLower.includes('corregir') || estadoLower.includes('corrección') || estadoLower.includes('correccion')) {
            return 'corregir';
        }
        if (estadoLower.includes('rechazado') || estadoLower === 'rechazado') {
            return 'rechazado';
        }
        // Por defecto, si no coincide, se pone en trámite
        return 'en_tramite';
    }

    // Función para procesar y agrupar solicitudes por estado
    function processSolicitudes(solicitudes) {
        if (!solicitudes || !Array.isArray(solicitudes) || solicitudes.length === 0) {
            return {};
        }

        const grouped = {
            en_tramite: [],
            pendiente: [],
            aprobado: [],
            corregir: [],
            rechazado: []
        };

        solicitudes.forEach(solicitud => {
            // Priorizar estado_display sobre estado (estado es numérico, estado_display es string)
            const estadoValue = solicitud.estado_display || solicitud.estado;
            const estadoKey = mapEstadoToKey(estadoValue);
            if (!estadoKey) return;

            const { fecha, hora } = formatFechaHora(solicitud.fecha_creacion);
            const nombreServicio = (solicitud.descripcion || solicitud.tipo || 'Sin descripción').toLowerCase();

            grouped[estadoKey].push({
                id: solicitud.id,
                nombre_servicio_minus: nombreServicio,
                fecha_creacion_v2: fecha,
                hora_creacion_v2: hora,
                codigo: solicitud.codigo,
                descripcion: solicitud.descripcion,
                tipo: solicitud.tipo,
                estado: solicitud.estado || solicitud.estado_display
            });
        });

        // Eliminar arrays vacíos
        Object.keys(grouped).forEach(key => {
            if (grouped[key].length === 0) {
                delete grouped[key];
            }
        });

        return grouped;
    }

    function applyProfilePayload(payload) {
        profileContext = payload?.contexto ?? null;
        activeProfileMeta = payload?.perfil ?? null;
        const nombreBase = payload?.usuario?.nombre || profileContext?.credenciales?.nombre_completo || '';
        const tipoPerfil = activeProfileMeta?.tipo || '';
        const rolEtiqueta = activeProfileMeta?.rol ? activeProfileMeta.rol.replace(/_/g, ' ') : '';
        const detalles = [tipoPerfil, rolEtiqueta].filter(Boolean).join(' · ');
        profileDisplayName = detalles ? `${nombreBase} — ${detalles}` : nombreBase;

        // Procesar solicitudes del perfil seleccionado
        if (profileContext?.solicitudes) {
            eSolicitudes = processSolicitudes(profileContext.solicitudes);
        } else {
            eSolicitudes = {};
        }
    }

    async function loadProfileContextFor(userId, profileId) {
        if (!userId || !profileId) {
            return;
        }

        const cacheKey = `${userId}:${profileId}`;
        const cached = profileCache.get(cacheKey);
        if (cached) {
            applyProfilePayload(cached);
            browserSet(PROFILE_STORAGE_KEY, { userId, profileId }, 'local');
            profileLoading = false;
            return;
        }

        profileLoading = true;
        profileContext = null;
        activeProfileMeta = null;
        profileDisplayName = '';
        try {
            const [payload, errors] = await apiGET(fetch, 'api/estudiante/', { usuario: userId, perfil: profileId });
            if (errors.length) {
                throw new Error(errors[0]?.error || 'No se pudo cargar la información del perfil seleccionado.');
            }
            if (!payload?.contexto) {
                throw new Error('La respuesta no contiene el contexto necesario.');
            }
            applyProfilePayload(payload);
            profileCache.set(cacheKey, payload);
            browserSet(PROFILE_STORAGE_KEY, { userId, profileId }, 'local');
        } catch (error) {
            console.error('[BalconServicios] Error cargando contexto del perfil:', error);
            addToast({
                type: 'danger',
                title: 'Error al cargar perfil',
                description: error.message || 'No se pudo cargar la información del perfil seleccionado.'
            });
            profileContext = null;
            activeProfileMeta = null;
            // No limpiar selectedProfileId aquí para mantener la selección en el select
            // selectedProfileId = '';
        } finally {
            profileLoading = false;
        }
    }

    function handleUserSelection(userId) {
        selectedUserId = userId;
        selectedProfileId = '';
        profileContext = null;
        activeProfileMeta = null;
        profileDisplayName = '';
        eSolicitudes = {}; // Limpiar solicitudes al cambiar usuario
        resetConversationState();
        updateAvailableProfiles();
        browserSet(PROFILE_STORAGE_KEY, null, 'local');

        if (selectedUserId && availableProfiles.length === 0) {
            addToast({
                type: 'info',
                title: 'Sin perfiles activos',
                description: 'El usuario seleccionado no tiene perfiles activos disponibles para pruebas.'
            });
        }

        if (selectedUserId && availableProfiles.length === 1) {
            const unicoPerfil = availableProfiles[0];
            // Usar setTimeout para asegurar que el DOM se actualice primero
            setTimeout(() => {
                handleProfileSelection(String(unicoPerfil.id));
            }, 0);
        }
    }

    async function handleProfileSelection(profileId) {
        if (!selectedUserId) {
            addToast({
                type: 'warning',
                title: 'Selecciona un usuario',
                description: 'Debes elegir un usuario antes de seleccionar un perfil.'
            });
            return;
        }

        // Convertir a string para consistencia
        const profileIdStr = profileId ? String(profileId) : '';

        if (!profileIdStr) {
            selectedProfileId = '';
            profileContext = null;
            activeProfileMeta = null;
            profileDisplayName = '';
            eSolicitudes = {}; // Limpiar solicitudes al deseleccionar perfil
            resetConversationState();
            browserSet(PROFILE_STORAGE_KEY, { userId: selectedUserId, profileId: '' }, 'local');
            return;
        }

        // Comparar como strings
        if (profileIdStr === selectedProfileId && profileContext) {
            return;
        }

        // Asignar antes de cargar para que el select se actualice inmediatamente
        selectedProfileId = profileIdStr;
        await loadProfileContextFor(selectedUserId, profileIdStr);
        resetConversationState();
    }

    function restoreFromStorage() {
        const saved = browserGet(PROFILE_STORAGE_KEY, 'local');
        if (saved?.userId) {
            const usuario = usuarios.find((item) => item.cedula === saved.userId);
            if (usuario) {
                selectedUserId = saved.userId;
                updateAvailableProfiles();
                if (saved.profileId && availableProfiles.some((p) => String(p.id) === String(saved.profileId))) {
                    selectedProfileId = String(saved.profileId);
                    return { userId: saved.userId, profileId: String(saved.profileId) };
                }
            }
        }
        return null;
    }

    // Cargar categorías desde el API
    async function loadCategorias() {
        try {
            const [payload, errors] = await apiGET(fetch, 'api/taxonomia/');
            if (errors.length) {
                throw new Error(errors[0]?.error || 'No se pudieron cargar las categorías.');
            }
            // Convertir el formato del API al formato esperado por el componente Menu
            const categorias = payload?.categorias || [];
            eCategorias = categorias.map((cat, index) => ({
                id: index + 1,
                descripcion_minus: cat.titulo?.toLowerCase() || '',
                display: cat.titulo || '',
                procesos: (cat.items || []).map((item, procIndex) => ({
                    id: (index + 1) * 100 + procIndex + 1,
                    descripcion_minus: item.toLowerCase(),
                    descripcion: item
                }))
            }));
        } catch (error) {
            console.error('[BalconServicios] Error cargando categorías:', error);
            addToast({
                type: 'danger',
                title: 'Error al cargar categorías',
                description: error.message || 'No se pudieron cargar las categorías de servicios.'
            });
            eCategorias = [];
        }
    }

    // Cargar datos iniciales
    onMount(async () => {
        loading.setLoading(true, 'Cargando datos...');
        
        // Cargar usuarios y categorías en paralelo
        await Promise.all([
            loadUsuarios(),
            loadCategorias()
        ]);

        updateAvailableProfiles();

        // Restaurar perfil guardado si existe
        const restored = restoreFromStorage();
        if (restored) {
            await loadProfileContextFor(restored.userId, restored.profileId);
        }
        
        loading.setLoading(false);
        dataLoaded = true;
    });


    // Manejar eventos de los componentes hijos
    const actionRun = async (event) => {
        const detail = event.detail;
        const action = detail.action;
        const data = detail.data;

        if (action === 'selectItem') {
            if (!profileContext) {
                addToast({
                    type: 'warning',
                    title: 'Selecciona un perfil',
                    description: 'Debes elegir un usuario y uno de sus perfiles antes de iniciar una conversación.'
                });
                return;
            }

            // Encontrar la categoría y subcategoría seleccionadas
            const procesoId = data.item;
            let categoria = null;
            let subcategoria = null;
            
            for (const cat of eCategorias) {
                const proceso = cat.procesos.find(p => p.id === procesoId);
                if (proceso) {
                    categoria = cat.display;
                    subcategoria = proceso.descripcion;
                    break;
                }
            }
            
            // Activar el chatbot con la categoría seleccionada
            selectedCategory = categoria;
            selectedSubcategory = subcategoria;
            showChatbot = true;
            
            // Activar el chatbot pasándole los datos
            if (chatbotComponent && categoria && subcategoria) {
                chatbotComponent.selectCategory(categoria, subcategoria, profileContext, {
                    profileType: activeProfileMeta?.rol || 'perfil',
                    userId: selectedUserId,
                    profileId: selectedProfileId
                });
            }
        }
    };

    // Reactividad: Actualizar solicitudes cuando cambie el contexto del perfil
    $: if (profileContext?.solicitudes && !profileLoading) {
        eSolicitudes = processSolicitudes(profileContext.solicitudes);
    }

    $: if (!profileLoading && chatbotComponent && profileContext && typeof chatbotComponent.updateProfileContext === 'function') {
        chatbotComponent.updateProfileContext(activeProfileMeta?.rol || 'perfil', profileContext, {
            profileType: activeProfileMeta?.rol || 'perfil',
            userId: selectedUserId,
            profileId: selectedProfileId
        });
    }
</script>

<svelte:head>
    <title>Balcón con GPT-PRIVATE</title>
</svelte:head>

<div class="balcon-container">
    <div class="header-section">
        <div class="title-wrapper">
        <h2 class="page-title">Balcón con GPT-PRIVATE</h2>
        <p class="page-subtitle">Para agilizar tu solicitud, selecciona la categoría y subcategoría correspondientes.</p>
            {#if profileDisplayName}
                <p class="profile-context">Perfil activo: {profileDisplayName}</p>
            {/if}
        </div>
        <div class="profile-controls">
            <div class="profile-selector">
                <label for="user-select">Usuario (PRUEBA)</label>
                <div class="selector-control">
                    <select
                        id="user-select"
                        value={selectedUserId}
                        on:change={(event) => handleUserSelection(event.target.value)}
                        disabled={usuariosLoading}
                    >
                        <option value="">Selecciona un usuario</option>
                        {#each usuarios as usuario}
                            <option value={usuario.cedula}>
                                {usuario.nombre} ({usuario.cedula})
                            </option>
                        {/each}
                    </select>
                    {#if usuariosLoading}
                        <span class="profile-loading">Cargando…</span>
                    {/if}
                </div>
            </div>

            {#if selectedUserId}
                <div class="profile-selector">
                    <label for="profile-select">Perfil (PRUEBA)</label>
                    <div class="selector-control">
                        <select
                            id="profile-select"
                            value={selectedProfileId}
                            on:change={(event) => handleProfileSelection(event.target.value)}
                            disabled={profileLoading || availableProfiles.length === 0}
                        >
                            <option value="">Selecciona un perfil</option>
                            {#each availableProfiles as perfil}
                                <option value={String(perfil.id)}>
                                    {perfil.tipo} ({perfil.rol})
                                </option>
                            {/each}
                        </select>
                        {#if profileLoading}
                            <span class="profile-loading">Cargando…</span>
                        {/if}
                    </div>
                </div>
            {/if}
        </div>
    </div>

    {#if dataLoaded}
        <div class="main-content-wrapper">
            <div class="content-grid">
                <!-- Columna izquierda: Menú de categorías -->
                <div class="sidebar-left">
                    <Menu on:actionRun={actionRun} {eCategorias} />
                </div>

                <!-- Columna central: Chatbot o mensaje de bienvenida -->
                <div class="content-center">
                    {#if showChatbot}
                        <!-- Mostrar el Chatbot cuando se selecciona una subcategoría -->
                        <div class="chatbot-container">
                            <ChatbotInline bind:this={chatbotComponent} />
                        </div>
                    {:else}
                        <!-- Mensaje de bienvenida -->
                        <div class="welcome-card">
                            <div class="welcome-content">
                                <i class="bi bi-chat-dots welcome-icon"></i>
                                <h3 class="welcome-title">Bienvenido al Asistente Virtual</h3>
                                <p class="welcome-text">
                                    Selecciona una categoría y subcategoría del menú lateral para comenzar.
                                </p>
                                <p class="welcome-text">
                                    Nuestro asistente te ayudará con tus consultas académicas, trámites y más.
                                </p>
                            </div>
                        </div>
                    {/if}
                </div>

                <!-- Columna derecha: Estado de solicitudes -->
                <div class="sidebar-right">
                    <SolicitudesInfo {eSolicitudes} />
                </div>
            </div>
        </div>
    {:else}
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Cargando...</span>
            </div>
        </div>
    {/if}
</div>

<style>
    .balcon-container {
        padding: 1rem 0;
    }

    .header-section {
        margin-bottom: 2rem;
        padding: 0 1rem;
        display: flex;
        flex-wrap: wrap;
        align-items: flex-start;
        gap: 1.5rem;
    }

    .title-wrapper {
        flex: 1 1 320px;
    }

    .page-title {
        font-size: 2rem;
        font-weight: bold;
        color: #12216A;
        margin-bottom: 0.5rem;
    }

    .page-subtitle {
        font-size: 1rem;
        color: #707070;
        margin-bottom: 0;
    }

    .profile-context {
        margin-top: 0.5rem;
        font-size: 0.9rem;
        color: #4a5568;
        font-weight: 500;
    }

    .profile-controls {
        display: flex;
        flex-wrap: wrap;
        gap: 1rem;
        align-items: flex-end;
        min-width: 320px;
    }

    .profile-selector {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        min-width: 220px;
    }

    .profile-selector label {
        font-size: 0.9rem;
        font-weight: 600;
        color: #12216A;
    }

    .selector-control {
        position: relative;
        display: flex;
        align-items: center;
    }

    .profile-selector select {
        width: 100%;
        padding: 0.6rem 1rem;
        padding-right: 2.75rem;
        border-radius: 12px;
        border: 1px solid #D3DBE3;
        font-weight: 600;
        color: #12216A;
        background-color: #fff;
        appearance: none;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2312216A' d='M6 8L2 4h8z'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right 1rem center;
        cursor: pointer;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }

    .profile-selector select:hover:not(:disabled) {
        border-color: #12216A;
    }

    .profile-selector select:focus {
        outline: none;
        border-color: #12216A;
        box-shadow: 0 0 0 3px rgba(18, 33, 106, 0.15);
    }

    .profile-selector select:disabled {
        opacity: 0.7;
        cursor: not-allowed;
        background-color: #f5f7fb;
    }

    .profile-loading {
        position: absolute;
        right: 1rem;
        font-size: 0.8rem;
        color: #707070;
    }

    .main-content-wrapper {
        width: 100%;
        padding: 0 1rem;
    }

    .content-grid {
        display: grid;
        grid-template-columns: 280px 1fr 320px;
        gap: 1.5rem;
        max-width: 1400px;
        margin: 0 auto;
    }

    @media (max-width: 1200px) {
        .content-grid {
            grid-template-columns: 250px 1fr 280px;
            gap: 1rem;
        }
    }

    @media (max-width: 992px) {
        .content-grid {
            grid-template-columns: 1fr;
            gap: 1.5rem;
        }
        
        .sidebar-left,
        .sidebar-right {
            order: 2;
        }
        
        .content-center {
            order: 1;
        }
    }

    .sidebar-left {
        min-width: 0;
    }

    .content-center {
        min-width: 0;
        display: flex;
        flex-direction: column;
    }

    .sidebar-right {
        min-width: 0;
    }

    .chatbot-container {
        min-height: 600px;
        width: 100%;
    }

    .welcome-card {
        min-height: 600px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px dashed #D3DBE3;
        border-radius: 22px;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 2rem;
    }

    .welcome-card:hover {
        border-color: #12216A;
        transition: border-color 0.3s ease;
    }

    .welcome-content {
        text-align: center;
        max-width: 500px;
    }

    .welcome-icon {
        font-size: 4rem;
        color: #12216A;
        margin-bottom: 1rem;
    }

    .welcome-title {
        color: #12216A;
        font-size: 1.75rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }

    .welcome-text {
        color: #707070;
        font-size: 1rem;
        margin-bottom: 0.5rem;
    }
</style>


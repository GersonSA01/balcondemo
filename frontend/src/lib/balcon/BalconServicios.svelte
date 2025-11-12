<script>
    import { onMount } from 'svelte';
    import { addToast } from '../stores/toastStore.js';
    import { apiPOST, apiGET, browserGet } from '../utils/requestUtils.js';
    import { loading } from '../stores/loadingStore.js';
    import { addNotification } from '../stores/notificationStore.js';
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

    // Cargar datos iniciales (DATOS DE PRUEBA - QUEMADOS)
    onMount(async () => {
        loading.setLoading(true, 'Cargando datos...');
        
        // Simular carga (opcional - puedes quitar esto)
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Datos quemados para pruebas
        eCategorias = [
            {
                id: 1,
                descripcion_minus: "académico",
                display: "Académico",
                procesos: [
                    { id: 101, descripcion_minus: "matriculación", descripcion: "Matriculación" },
                    { id: 102, descripcion_minus: "cambio de paralelo", descripcion: "Cambio de Paralelo" },
                    { id: 103, descripcion_minus: "titulación", descripcion: "Titulación" }
                ]
            },
            {
                id: 2,
                descripcion_minus: "bienestar estudiantil",
                display: "Bienestar Estudiantil",
                procesos: [
                    { id: 201, descripcion_minus: "servicio médico", descripcion: "Servicio Médico" },
                    { id: 202, descripcion_minus: "servicio psicológico", descripcion: "Servicio Psicológico" },
                    { id: 203, descripcion_minus: "beca estudiantil", descripcion: "Beca Estudiantil" }
                ]
            },
            {
                id: 3,
                descripcion_minus: "financiero",
                display: "Financiero",
                procesos: [
                    { id: 301, descripcion_minus: "valores a cancelar", descripcion: "Valores a Cancelar" },
                    { id: 302, descripcion_minus: "notas de crédito", descripcion: "Notas de Crédito" }
                ]
            }
        ];
        
        eSolicitudes = {
            en_tramite: [
                {
                    id: 1,
                    nombre_servicio_minus: "matriculación online",
                    fecha_creacion_v2: "15/10/2024",
                    hora_creacion_v2: "09:30"
                }
            ],
            aprobado: [
                {
                    id: 2,
                    nombre_servicio_minus: "cambio de paralelo",
                    fecha_creacion_v2: "10/10/2024",
                    hora_creacion_v2: "14:20"
                }
            ]
        };
        
        loading.setLoading(false);
        dataLoaded = true;
    });

    // Manejar eventos de los componentes hijos
    const actionRun = async (event) => {
        const detail = event.detail;
        const action = detail.action;
        const data = detail.data;

        if (action === 'selectItem') {
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
                chatbotComponent.selectCategory(categoria, subcategoria, null);
            }
        }
    };
</script>

<svelte:head>
    <title>Balcón con GPT-PRIVATE</title>
</svelte:head>

<div class="balcon-container">
    <div class="header-section">
        <h2 class="page-title">Balcón de Servicios</h2>
        <p class="page-subtitle">Para agilizar tu solicitud, selecciona la categoría y subcategoría correspondientes.</p>
    </div>

    {#if dataLoaded}
        <div class="container-fluid">
            <div class="row">
                <!-- Columna izquierda: Menú de categorías -->
                <div class="col-lg-3 col-md-3 col-12">
                    <Menu on:actionRun={actionRun} {eCategorias} />
                </div>

                <!-- Columna central: Chatbot o mensaje de bienvenida -->
                <div class="col-lg-6 col-md-6 col-12 mx-0">
                    {#if showChatbot}
                        <!-- Mostrar el Chatbot cuando se selecciona una subcategoría -->
                        <div class="chatbot-container">
                            <ChatbotInline bind:this={chatbotComponent} />
                        </div>
                    {:else}
                        <!-- Mensaje de bienvenida -->
                        <div class="card welcome-card">
                            <div class="card-body text-center p-5">
                                <i class="bi bi-chat-dots" style="font-size: 4rem; color: #12216A;"></i>
                                <h3 class="mt-3 mb-2" style="color: #12216A;">Bienvenido al Asistente Virtual</h3>
                                <p class="text-muted">
                                    Selecciona una categoría y subcategoría del menú lateral para comenzar.
                                </p>
                                <p class="text-muted">
                                    Nuestro asistente te ayudará con tus consultas académicas, trámites y más.
                                </p>
                            </div>
                        </div>
                    {/if}
                </div>

                <!-- Columna derecha: Estado de solicitudes -->
                <div class="col-lg-3 col-md-3 col-12">
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
        text-align: left;
        padding: 0 1rem;
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

    .chatbot-container {
        min-height: 500px;
    }

    .welcome-card {
        min-height: 500px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px dashed #D3DBE3;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    }

    .welcome-card:hover {
        border-color: #12216A;
        transition: border-color 0.3s ease;
    }
</style>


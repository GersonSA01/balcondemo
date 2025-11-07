<script>
	import { createEventDispatcher, onMount } from 'svelte';	    
    let item = 0;
	export let eCategorias;
	const DEBUG = import.meta.env.DEV;

	onMount(async () => {
		// Inicialización o lógica adicional
	});

	const dispatch = createEventDispatcher();

	const actionLoad = (link) => {		
        item = link;
		dispatch('actionRun', { action: 'selectItem', data: { item: item } });
	};
</script>

<!-- Menú -->
<div class="menu-container">
    <h5 class="menu-title">Categorías</h5>
    <nav class="navbar navbar-expand-md navbar-light mb-4 mb-lg-0 p-0 sidenav h-100 align-items-start">                        
        <div class="navbar-collapse" id="sidenav">
            <div class="navbar-nav flex-column m-0 p-0">
                <div class="accordion accordion-flush" id="items">
                    {#each eCategorias as eCategoria, index }
                    <div class="accordion-item ">
                        <div class="accordion-header ">
                            <button
                                class="accordion-button accordion-btn-white collapsed"
                                type="button"
                                data-bs-toggle="collapse" 
                                data-bs-target="#{eCategoria.id}"
                                aria-expanded="false"
                            >
								                <h4 class="mb-0" style="color: #253CA6;">{eCategoria.descripcion_minus}</h4> <i class="custom-chevron" style="display: inline-block; float: right;"></i>
                            </button>
                        </div>
                        <div id="{eCategoria.id}" class="accordion-collapse collapse" data-bs-parent="#items" aria-expanded="true">
                            <div class="accordion-body m-0 p-0 ">
                                <div class="list-group list-group-flush mt-2">
                                    {#each eCategoria.procesos as eProceso }
                                    <li class="list-group-item p-0 mx-3">
                                        <a
                                            href="#{eProceso.id}"
                                            class="list-group-item-white pb-2 d-flex justify-content-between {item === eProceso.id ? 'active' : ''}"
                                            on:click={() => actionLoad(eProceso.id)}
                                        >
                                            {eProceso.descripcion_minus} <i class="fe fe-chevron-right  {item === eProceso.id ? 'chevron-active' : ''}" />                                            
                                        </a>
                                    </li>
                                    {/each}
                                </div>
                            </div>
                        </div>
                    </div>
                    {/each}
                </div>
            </div>
        </div>
    </nav>
</div>

<!-- Estilos -->
<style>
    /* Título "Categorías" */
    .menu-title {
        font-size: 1.25rem;
        font-weight: bold;
        color: #12216A; 
        margin-bottom: 0.2rem;
    }

    /* Estilos del contenedor del menú */
    .menu-container .navbar {
        background-color: #F5F6F8 !important;
        padding: 1rem;
    }
	
	.accordion-item {
        background-color: #F5F6F8 !important;       
    }

	.accordion-body {
        background-color: #F5F6F8;
        box-shadow: inset 0 -1px 0 #d6eaf8;
        color: #253CA6;
    }

    .accordion-btn-white {
        background-color: #CADFF2 !important; 
		color: #253CA6 !important;
    }

    /* Estilo cuando una categoría no está activa */
    .accordion-button.collapsed {
        background-color: #EDF2F8 !important; 
    }

    .accordion-button {
        outline: none !important;
        box-shadow: none !important; /* Si el borde es un efecto de sombra */
    }

    .accordion-button:focus,
    .accordion-button:active {
        outline: none !important;
        box-shadow: none !important;
    }

    /* Subcategorías (ítems) */
    .list-group-item {
        background-color: #F5F6F8 !important; /* Fondo blanco para subcategorías */
        color: #1c3247; /* Texto azul oscuro */
        font-size: 0.875rem;
        border: none;
    }

    .list-group-item-white {
        background-color: #F5F6F8 !important;
        color: #1C3247 !important;     
    }

    .list-group-item-white:hover {        
        color: #346695 !important;
        font-weight: bold !important;     
    }

    .list-group-item-white.active {    
		color: #12216A !important; 
        font-weight: bold !important;
    }

    /* Flecha activa */
    .chevron-active {
        color: #fe9900 !important; /* Color de la flecha en anaranjado cuando está activa */
    }

	/* Eliminar la flecha predeterminada */
	.accordion-button {
        display: flex;
        align-items: center; /* Asegura que los elementos estén centrados verticalmente */
        justify-content: space-between; /* Hace que el texto esté a la izquierda y la flecha a la derecha */
        background-color: #CADFF2 !important; 
    }

	.accordion-button::after {
		display: none !important; /* Asegura que las flechas predeterminadas no se muestren */
	}

    .custom-chevron::after {
        content: "\25BC";
        font-size: 0.8rem;
        color: #253CA6;          
        transition: transform 0.3s ease;
    }

    /* Cambiar la flecha a hacia arriba cuando está expandido */
    .accordion-button:not(.collapsed) .custom-chevron::after {
        content: "\25B2";  /* Rotar la flecha cuando está expandido */
    }
    
</style>
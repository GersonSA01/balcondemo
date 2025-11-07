<script>
	import { createEventDispatcher, onMount } from 'svelte';
	import { Carousel, CarouselItem, Tooltip } from 'sveltestrap';
	import { variables } from '$lib/utils/constants';
	import ComponentViewPDF from '$components/viewPDF.svelte';

	let activeItem = 0;
	let actionItem = '';
	let items = [
		{ src: '/assets/images/background/balcon_info_1.png', alt: 'Imagen 1' },
		{ src: '/assets/images/background/balcon_info_2.png', alt: 'Imagen 2' }
	];
	export let eInformationsServices;

	const dispatch = createEventDispatcher();

	const actionRun = (action, index) => {
		activeItem = index;
		actionItem = action;
		dispatch('actionRun', { action: actionItem, data: { item: activeItem } });
	};

	const mToggleModal = () => (mOpenModal = !mOpenModal);
	let aDataModal;
	let modalDetalleContent;
	let mOpenModal = false;
	let mTitleModal;
	let mClassModal = 'modal-dialog modal-dialog-centered modal-dialog-scrollable  modal-fullscreen-lg-down';
	let mSizeModal = 'lg';

	const view_pdf = (url, title) => {
		aDataModal = { url: url };
		modalDetalleContent = ComponentViewPDF;
		mOpenModal = !mOpenModal;
		mTitleModal = title;
		mClassModal = 'modal-dialog modal-dialog-centered modal-dialog-scrollable  modal-fullscreen-lg-down';
		mSizeModal = 'xl';
	};

</script>

<div class="py-1">				
	{#if eInformationsServices.length > 0}	
		<div class="py-4">						
			<ul class="result-list">
				{#each eInformationsServices as eInformationService, index}
					<li class="list-group-item mb-3">
						<div class="col-12 result-info d-flex justify-content-between align-items-center">
							<div class="col-9 text-left">
								<h5 class="service-title">{eInformationService.descripcion_minus}</h5>
								<p class="service-description">
									{eInformationService.servicio.servicio.descripcion_minus}
								</p>
								{#if eInformationService.archivomostrar }									
									{#if eInformationService.typefilemostrar != '.pdf' }
										{#if eInformationService.typefilemostrar == '.docx' || eInformationService.typefilemostrar == '.doc' }
											<a
												href="{eInformationService.archivomostrar}"
												class="text-primary fs-3"
												id="Tooltip_typefilemostrar_id_{eInformationService.id}"
												download
											><i class="bi bi-file-word"></i></a>
											<Tooltip target="Tooltip_typefilemostrar_id_{eInformationService.id}" placement="top">Formato de la solicitud</Tooltip>
										{:else}
											<a
												href="javascript:;"
												on:click={() => view_pdf(eInformationService.archivomostrar, 'Ver imagen')}
												class="text-dark-info fs-3"
												id="Tooltip_typefilemostrar_id_{eInformationService.id}"
											><i class="bi bi-file-image"></i></a>
											<Tooltip target="Tooltip_typefilemostrar_id_{eInformationService.id}" placement="top">Ver imagen</Tooltip>
										{/if}
									{:else}
										<a
											href="javascript:;"
											on:click={() => view_pdf(eInformationService.archivomostrar, 'Ver archivo')}
											class="text-danger fs-3"
											id="Tooltip_typefilemostrar_id_{eInformationService.id}"
										><i class="bi bi-file-pdf"></i></a>
										<Tooltip target="Tooltip_typefilemostrar_id_{eInformationService.id}" placement="top">Ver archivo</Tooltip>
									{/if}									
								{/if}
								{#if eInformationService.archivodescargar }									
									{#if eInformationService.typefiledescargar != '.pdf' }
										<a
											href="javascript:;"
											on:click={() => view_pdf(eInformationService.archivodescargar, 'Ver imagen')}
											class="text-dark-info fs-3"
											id="Tooltip_typefiledescargar_id_{eInformationService.id}"	
										><i class="bi bi-file-image"></i></a>
										<Tooltip target="Tooltip_typefiledescargar_id_{eInformationService.id}" placement="top">Ver archivo para descargar</Tooltip>											
									{:else}
										<a
											href="javascript:;"
											on:click={() => view_pdf(eInformationService.archivodescargar, 'Ver archivo')}
											class="text-danger fs-3"
											id="Tooltip_typefiledescargar_id_{eInformationService.id}"
										><i class="bi bi-file-pdf"></i></a>
										<Tooltip target="Tooltip_typefiledescargar_id_{eInformationService.id}" placement="top">Ver archivo para descargar</Tooltip>											
									{/if}									
								{/if}
								{#if eInformationService.informacion}
								<button class="btn btn-ver-mas" type="button"
										data-bs-toggle="collapse"
										data-bs-target="#collapseOne{eInformationService.id}" aria-expanded="true"
										aria-controls="collapseOne{eInformationService.id}">
										<i class="bi bi-eye"></i> Ver más
								</button>
								<div id="collapseOne{eInformationService.id}" class="collapse">
									{@html eInformationService.informacion}
								</div>
								{/if}
								
							</div>
							<div class="col-3 text-end">
								{#if eInformationService.servicio.opcsistema}									
									<a class="btn btn-primary solicitar-btn"
									id="Tooltip_btnir_id_{eInformationService.id}"
									href="{eInformationService.servicio.opcsistema.modulo.api?'':variables.BASE_API}/{ eInformationService.servicio.opcsistema.modulo.url }"									
									title=""><i class="fe fe-arrow-right" aria-hidden="true"></i> Ir </a>
									<Tooltip target="Tooltip_btnir_id_{eInformationService.id}" placement="top">Ir a {eInformationService.servicio.servicio.nombre_minus}</Tooltip>
																											
								{:else}
									<a class="btn btn-primary solicitar-btn" href="javascript:void(0);" on:click={() => actionRun('openRequestService', eInformationService.servicio)}>
										+ Solicitar
									</a>
								{/if}
								
							</div>
						</div>
					</li>
				{/each}
			</ul>	
		</div>		
	{:else}
		<div class="py-0 mx-0">		
			<Carousel activeIndex={activeItem} dark>
				<!-- Indicadores del carrusel (puntos) -->
				<ol class="carousel-indicators mb-2">
					{#each items as item, i}
						<li class="{activeItem === i ? 'active' : ''}" on:click={() => actionRun('selectCarrusel', i)}> </li>
					{/each}
				</ol>
		
				<div class="carousel-inner">					
					{#each items as item, i}
						<CarouselItem>
							<!-- Solo mostramos la imagen activa -->
							<div class="card card-hover mb-lg-4 m-0 {activeItem === i ? 'd-block' : 'd-none'}">
								<img src={item.src} alt={item.alt} class="img-fluid w-100 rounded-top-md" />
							</div>
						</CarouselItem>
					{/each}
				</div>
			</Carousel>
		</div>	
	{/if}	
		
</div>

{#if mOpenModal}
	<svelte:component
		this={modalDetalleContent}
		aData={aDataModal}
		{mOpenModal}
		mToggle={mToggleModal}
		mTitle={mTitleModal}
		mClass={mClassModal}
		mSize={mSizeModal}
		on:actionRun={actionRun}
	/>
{/if}

<style>
    .carousel-inner{
		margin-bottom: 3rem;
	}
	
	.carousel-indicators {
        position: absolute;
        bottom: -20px; 
        left: 47%;
        transform: translateX(-100%);
        display: flex;
        justify-content: center;
        list-style: none;
    }

    .carousel-indicators li {
        background-color: #D3DBE3;
        border-radius: 50%;
        width: 10px;
        height: 10px;
        margin: 0 5px;
        cursor: pointer;
    }

    .carousel-indicators .active {
        background-color: #0A4985; 
    }

	/* estilos para subcategorias */
	.result-list {
		padding: 0;
		list-style-type: none;
	}

	.list-group-item {		
		background-color: #EEF3FC;
		border: none;
		padding: 1rem;
		border-radius: 10px;
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
	}

	.result-info {
		padding: 1.5rem 1rem;	
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.service-title {
		font-size: 1rem;
		color: #12216A; /* Color azul para el título */
		font-weight: 600;
		margin-bottom: 0.5rem;
	}

	.service-description {
		font-size: 0.875rem;
		color: #707070;
		margin: 0;
	}

	.solicitar-btn {
		background-color: #0A4985; 
		color: #FFFFFF;		
		border-radius: 10px; /* Botón redondeado */		
		font-size: 0.8rem;					
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
		transition: background-color 0.3s ease;
	}

	.solicitar-btn:hover {
		background-color: #083b6e; /* Cambio de color en hover */
		font-weight: bold;
	}	

	.btn-ver-mas {
		color: #253CA6;
	}

	.btn-ver-mas:hover {
		color: #FF9900;
	}

</style>


<script lang="ts">
	import Swal from 'sweetalert2';
	import { addToast } from '$lib/store/toastStore';
	import { browserGet, apiPOSTFormData, apiPOST, apiGET } from '$lib/utils/requestUtils';
	import { onMount } from 'svelte';
	import { loading } from '$lib/store/loadingStore';
	import { converToAscii, action_print_ireport } from '$lib/helpers/baseHelper';
	import { addNotification } from '$lib/store/notificationStore';
	import { Spinner, Tooltip } from 'sveltestrap';
	
	import { createEventDispatcher, onDestroy } from 'svelte';
	import CompArchivoModal from './_archivo_modal_correccion.svelte';

	const dispatch = createEventDispatcher();

	export let eSolicitud;
	let eHistories = [];
	let dataExtras = {};
	let eLastHistory = {};
	let eEstadoSolicitud = 0;
	let file_url = 0;
	let tiene_file = false;
	let estadosSol = [3, 4, 5, 6]
	let eColorEstadoSolicitud = '#0BA883';
	let eNombreEstadoSolicitud = 'Espacio destinado para observaciones';
	let aDataModal;
	let mOpenModal = false;
	let mTitleModal;
	let mClassModal =
		'modal-dialog modal-dialog-centered modal-dialog-scrollable  modal-fullscreen-lg-down';
	let mSizeModal = 'lg';
	const mToggleModal = () => (mOpenModal = !mOpenModal);
	let modalDetalleContent;

	onMount(async () => {
		loading.setLoading(true, 'Cargando, espere por favor...');
		const [res, errors] = await apiGET(fetch, 'alumno/balcon_servicios', {
			action:'getViewHistoricalRequestService',
			id: eSolicitud.id
		});
		loading.setLoading(false, 'Cargando, espere por favor...');
		if (errors.length > 0) {
			addNotification({
				msg: errors[0].error,
				type: 'error'
			});
		} else {
			if (!res.isSuccess) {
				addNotification({
					msg: res.message,
					type: 'error'
				});
			} else {				
				eHistories = res.data.eBalconyRequestHistories;		
				// console.log(eHistories);
				if (eHistories.length > 0) {
					eLastHistory = eHistories[eHistories.length - 1];
					titleEstadoSolicitud(eLastHistory);
				}	
				
			}
		}
	});
	const actionRun = (event) => {
		dispatch('actionRun', { action: event.detail.action, value: event.detail.value });
	};

	const verActaAceptar = (solicitud) => {
		const data = {
			pdfUrl: solicitud,
		};
			mOpenModal = !mOpenModal;
			aDataModal = data;
			modalDetalleContent = CompArchivoModal;
			mTitleModal = 'ARCHIVO ADJUNTO';
			mSizeModal = 'xl';

	};

	const titleEstadoSolicitud = (event) => {
		eEstadoSolicitud = event.estado
		file_url = event.archivo
		tiene_file = false
		if (file_url){
			tiene_file = true
		}
		if(eEstadoSolicitud === 1 || eEstadoSolicitud === 2){
			eNombreEstadoSolicitud = 'Espacio destinado para observaciones';	
			eColorEstadoSolicitud = '#FF9900';		
		}else if(eEstadoSolicitud === 3){
			eNombreEstadoSolicitud = 'Motivos de solicitud enviada a corregir';
			eColorEstadoSolicitud = '#9E68DC';
		}else if(eEstadoSolicitud === 4){
			eNombreEstadoSolicitud = 'Motivos de solicitud cerrada';
			eColorEstadoSolicitud = '#0dcaf0';
		}else if(eEstadoSolicitud === 5){
			eNombreEstadoSolicitud = 'Motivos de solicitud aprobada';
			eColorEstadoSolicitud = '#0BA883';
		}else if(eEstadoSolicitud === 6){
			eNombreEstadoSolicitud = 'Motivos de solicitud rechazada';
			eColorEstadoSolicitud = '#FF0000';
		}
	};	


</script>

<div>

	<div class="container">
		<div class="timeline-container">
			{#each eHistories as step, index}
				<div class="timeline-item {index} {eHistories.length - 1} {index > 0 && index === eHistories.length - 2 ? 'penultimo': index > 0 && index < eHistories.length - 1 ? 'intermediate' : ''}">
					<div class="step-title-container {index > 0 && index < eHistories.length - 1 ? 'intermediate' : ''}">
						<p class="step-title" style="color:{index === 0 ? '#FF9900' : index === eHistories.length - 1 ? step.color : '#12216A'}"><strong>{index === 0 ? 'Recepción en el sistema' : step.departamento ? step.departamento : 'Dirección de ' + step.direccion }</strong></p>
					</div>

					<div class="circle-line-container {index > 0 && index < eHistories.length - 2 ? 'intermediate' : ''} {eHistories.length === 1 ? 'uniquehistory' : ''}">
						<div class="circle" style="background-color: {step.color};" id="{`tooltip-circle-${step.id}`}"></div>
						{#if index > 0 && index < eHistories.length - 1}
						<Tooltip target={`tooltip-circle-${step.id}`} placement="top"><p>{#if step.departamento }{step.departamento}{:else}{step.direccion}{/if}<br>{step.fecha_creacion_v2} <br> {step.hora_creacion_v2}</p></Tooltip>
						{/if}
						{#if index < eHistories.length - 1}
							<div class="line" style="{index === eHistories.length - 2 ?  `background:linear-gradient(to right, #ffa500 60%, #ffc04c, #e3e69a, #e3e69a, ${step.color});` : ''}"></div>
						{/if}
					</div>

					<div class="timeline-content {index > 0 && index < eHistories.length - 1 ? 'intermediate' : ''}" style="color: #12216A;">
						<p>{step.fecha_creacion_v2} <br> {step.hora_creacion_v2}</p>
						{#if step.estado > 0}
							<span class="badge" style="background-color: {step.color};">{step.estado_display}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>

	<br>
	<div class="solicitudes-container mb-3">
		<h5 class="solicitud-title mx-3">
			{eNombreEstadoSolicitud}
			{#if tiene_file}
				<button
					on:click={() => verActaAceptar(file_url)}
					class="btn btn-warning rounded-5 btn-xs ms-1"
					type="button"
					title="Acta Aceptación">
					<i class="bi bi-file-pdf" /> Ver documento adjunto
				</button>
			{/if}
		</h5>
		{#if eHistories.length > 0 }
			<div class="solicitudes-box ms-3">
				<p class="solicitudes-empty-text">
					{#each eHistories as step, index}
						{#if eHistories.length - 1 === index}
							{#if estadosSol.includes(step.estado)}
								{step.observacion}
							{:else}
								<p class="solicitudes-empty-text">
									Tu solicitud aún se encuentra en proceso. Si surge alguna observación, la verás reflejada en esta sección de comentarios.
								</p>
							{/if}
						{/if}
					{/each}
				</p>
			</div>     		
		{:else}			  
			<div class="solicitudes-box ms-3">
				<p class="solicitudes-empty-text">
					Tu solicitud aún se encuentra en proceso. Si surge alguna observación, la verás reflejada en esta sección de comentarios.
				</p>
			</div>        
		{/if}
	</div>
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
	.solicitud-title {
        font-size: 1.25rem;
        font-weight: bold;
        color: #12216A;         
        text-align: left;
    }

    .titulo-solicitudes {
        font-size: 1.5rem;
        color: #12216A; /* Azul oscuro para el título */
        text-align: center;
        margin-bottom: 2rem;
    }

    .estado-solicitudes {
        margin-bottom: 2rem; /* Separación entre los grupos de solicitudes */
    }

	.solicitudes-box {
        background-color: #F5F8FB;
        border-radius: 12px;		        
        text-align: left;
        color: #707070; /* Color gris suave */
		max-height: 435px; /* Ajusta esta altura según sea necesario */
  		overflow-y: auto;  /* Activa la barra de desplazamiento vertical */
  		padding-right: 30px;
    }
	

    .solicitudes-empty-text {
        font-size: 0.875rem;
        color: #707070; /* Texto en gris */
    }

	
  /* Linea de tiempo - Contenedor siempre horizontal */   
	.timeline-container {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		width: 100%;
		padding: 10px;
		gap: 10px;
	}

	.timeline-item {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		flex: 1;
	}

	.step-title-container {
		height: 50px;
		display: flex;
		align-items: center;
	}

	.step-title {
		margin-bottom: 10px;
		max-height: 40px;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.gradient-line {		
		background: linear-gradient(to right, #ffa500 60%, #ffc04c, #e3e69a, #9ed8a1, #00614B);
	}

	.circle-line-container {
		display: flex;
		align-items: center;
		position: relative;
		width: 100%;
		margin-left: 80%;
	}

	.uniquehistory{		
		width: 50%;
		margin-left: 10% !important;
	}

	.circle {
		width: 25px;
		height: 25px;
		border-radius: 50%;
		
		border: 3.5px solid #E3E6E9;
		z-index: 1;
	}

	.circle.green {
		background-color: #00614B;
		border-color: #0BA883;
	}

	.line {
		flex-grow: 1;
		height: 8px;
		background-color: #ffa500;
		margin-left: -10px;
		margin-right: -10px;
	}

	.timeline-content {
		margin-top: 10px;
		min-height: 50px;
	}

	.badge {
		margin-top: 1px;
		font-size: 12px;
		padding: 5px 10px;
		border-radius: 5px;
	}

	/* Responsive */
	@media (max-width: 576px) {		
		.step-title-container.intermediate {
			visibility: hidden;	
			width: 2%;		
		}
		.timeline-content.intermediate {
			visibility: hidden;
			width: 2%;
		}
		.timeline-item.intermediate {
			width: 2%;
		}
		.timeline-item.penultimo{
			width: 2%;
			margin-right: 0%;
		}

		.timeline-item.penultimo .line {
			margin-right: -40px !important;
			background-color: #ffa500;
		}

	}

</style>
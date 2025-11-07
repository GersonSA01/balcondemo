<script context="module" lang="ts">
	import type { Load } from '@sveltejs/kit';
	import { session, page, navigating } from '$app/stores';	

	export const load: Load = async ({ params, fetch }) => {
		const id = params.id;		
		const ds = browserGet('dataSession');			
		let eSolicitud = {};	
		let eHistories = [];		
		let eLastHistory = {};
		let eRequirements = {};						

		if (ds != null || ds != undefined) {
			const dataSession = JSON.parse(ds);
			const [res, errors] = await apiGET(fetch, 'alumno/balcon_servicios', {				
				action: 'getViewHistoricalRequestService',
				id: id
			});
			if (errors.length > 0) {
				addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
				return {
					status: 302,
					redirect: '/'
				};
			} else {
				if (!res.isSuccess) {
					addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
					if (!res.module_access) {
						return {
							status: 302,
							redirect: '/alu_solicitudbalcon/missolicitudes'
						};
					}
				} else {								
					eSolicitud = res.data.eBalconyRequest;
					eHistories = res.data.eBalconyRequestHistories;	
					// console.log(eHistories);
					if (eHistories.length > 0) {
						eLastHistory = eHistories[eHistories.length - 1];
						// console.log(eLastHistory);
					}		
					
				}
			}
		} else {
			return {
				status: 302,
				redirect: '/alu_solicitudbalcon'
			};
		}

		return {
			props: {				
				eSolicitud, eRequirements,			
			}
		};
	};
</script>

<script lang="ts">
	import { apiGET, apiPOST, browserGet, browserSet } from '$lib/utils/requestUtils';
	import { variables } from '$lib/utils/constants';
	import { goto } from '$app/navigation';
	import { addToast } from '$lib/store/toastStore';
	import { loading } from '$lib/store/loadingStore';
	import { onMount } from 'svelte';
	import { addNotification } from '$lib/store/notificationStore';
	import { decodeToken } from '$lib/utils/decodetoken';
	import type { UserResponse } from '$lib/interfaces/user.interface';
	import FormularioSolicitud from './_formulario.svelte';
	import ComponentObservaciones from './_observaciones.svelte';
	import BreadCrumb from '$components/BreadCrumb/BreadCrumb.svelte';	
	export let eSolicitud;
	export let eRequirements;
	let nombreServicio = eSolicitud.nombre_servicio_minus;	
	// console.log('nuevo eService');
	// console.log(eSolicitud);
	let total_pedidos = 0;
	let itemsBreadCrumb = [{ text: 'Balcón servicio', active: true, href: '/alu_solicitudbalcon' }, 
						   { text: 'Mis Solicitudes', active: true, href: '/alu_solicitudbalcon/missolicitudes' }, 
						   { text: nombreServicio, active: true, href: undefined }];
    let backBreadCrumb = { href: '/alu_solicitudbalcon/missolicitudes_new', text: '<i class="bi bi-chevron-left"></i> Regresar' };
	$: loading.setNavigate(!!$navigating);
	$: loading.setLoading(!!$navigating, 'Cargando, espere por favor...');
	onMount(async () => {});

	const actionRun = (event) => {
		if (event.detail.action === 'totalPedidos'){
			total_pedidos = event.detail.value;
		}
	};


</script>

<svelte:head>
	<title>Seguimiento de solicitud</title>
</svelte:head>
{#if eSolicitud}
	<BreadCrumb title="{nombreServicio}" subtitle="Consulta en qué etapa se encuentra tu solicitud y sigue su progreso desde la recepción hasta la aprobación final." items={itemsBreadCrumb} back={backBreadCrumb} />
	<div class="p-2">		
		<div class="row">							
			<div class="col-lg-6 col-md-6 col-12 mx-0">				
				<ComponentObservaciones on:actionRun={actionRun} {eSolicitud} />
			</div>
			<div class="col-lg-6 col-md-6 col-12 mx-0">				
				<FormularioSolicitud on:actionRun={actionRun} {eSolicitud} {eRequirements}/>
			</div>								
		</div>
	</div>
{/if}

<script context="module" lang="ts">
    import type { Load } from '@sveltejs/kit';
    export const load: Load = async ({ fetch }) => {
        let eBalconyRequests = [];
        const ds = browserGet('dataSession');
        //console.log(ds);
        if (ds != null || ds != undefined) {
            loading.setLoading(true, 'Cargando, espere por favor...');
            const [res, errors] = await apiPOST(fetch, 'alumno/balcon_servicios', {action:'getMyRequests'});
            loading.setLoading(false, 'Cargando, espere por favor...');
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
                            redirect: '/'
                        };
                    }
                } else {
                    eBalconyRequests = res.data['eBalconyRequests'];
                }
            }
        }

        return {
            props: {
                eBalconyRequests
            }
        };
    };
</script>
<script lang="ts">
    import { addToast } from "$lib/store/toastStore";
    import { apiPOSTFormData, apiPOST, browserGet, apiGET} from "$lib/utils/requestUtils";
    // import Swal from 'sweetalert2';
    // import { onMount } from 'svelte';
    // import { variables } from '$lib/utils/constants';
    import BreadCrumb from '$components/BreadCrumb/BreadCrumb.svelte';
    import { loading } from '$lib/store/loadingStore';
    // import FilePond, { registerPlugin, supported } from 'svelte-filepond';
    // import FilePondPluginFileValidateType from 'filepond-plugin-file-validate-type';
    //import { Fancybox, Carousel, Panzoom } from "@fancyapps/ui";
    //import '@fancyapps/ui/dist/fancybox.css';
    // import StarRating from '@ernane/svelte-star-rating';
    import { createEventDispatcher, onDestroy } from 'svelte';
    const dispatch = createEventDispatcher();
    import { goto } from '$app/navigation';
    import { navigating } from '$app/stores';
    // import { addNotification } from '$lib/store/notificationStore';
    // import {Modal, ModalBody, ModalFooter, ModalHeader, Tooltip} from 'sveltestrap';
    // import {FilePondFile} from "filepond";
    export let eBalconyRequests;
    let titulo_solicitud = 'Seguimiento de solicitud'
    let itemsBreadCrumb = [{ text: 'Balcón servicio', active: true, href: '/alu_solicitudbalcon' },{ text: 'Mis Solicitudes', active: true, href: '/alu_solicitudbalcon/missolicitudes' }, { text: titulo_solicitud, active: true, href: undefined }];
    let backBreadCrumb = { href: '/alu_solicitudbalcon/missolicitudes', text: '<i class="bi bi-chevron-left"></i> Regresar' };
    $: loading.setNavigate(!!$navigating);
    $: loading.setLoading(!!$navigating, 'Cargando, espere por favor...');
    console.log(eBalconyRequests);
    // let mSizeRequestService = 'lg';
    // let mOpenRequestService = false;
    // let request_id = '';
    // let eRequestServiceObservation = '';
    // let textService = '';
    // let eService = {};
    // let eRequirements = {};
    // let eBalconyRequest = {};
    // let eBalconyRequestHistories = [];
    // let eSurveysProcess = [];
    // let modal_view = false;
    // let modal_action_view = false;
    // let title_modal = '';
    // Fancybox.bind("[data-fancybox]", {
    //     // Your options go here
    // });
    // const mToggleRequestService = () => (mOpenRequestService = !mOpenRequestService );

    // const CloseRequestService = () =>{
    //     mOpenRequestService = false;
    // }
    // const saveRequestService = async () => {
    //     console.log(eBalconyRequest);
    //     const $frmRequestService = document.querySelector('#frmRequestService');
    //     const formData = new FormData($frmRequestService);
    //     formData.append('action', 'editRequestService');
    //     if (!eRequestServiceObservation) {
    //         addNotification({
    //             msg: 'Favor complete el campo de descripción',
    //             type: 'error',
    //             target: 'newNotificationToast'
    //         });
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         return;
    //     }
    //     loading.setLoading(true, 'Guardando la información, espere por favor...');
    //     const [res, errors] = await apiPOSTFormData(fetch, 'alumno/balcon_servicios', formData);

    //     if (errors.length > 0) {
    //         addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         return;
    //     } else {
    //         if (!res.isSuccess) {
    //             addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
    //             if (!res.module_access) {
    //                 goto('/');
    //             }
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             return;
    //         } else {
    //             addToast({ type: 'success', header: 'Exitoso', body: 'Se guardo correctamente los datos' });
    //             dispatch('actionRun', { action: 'nextProccess', value: 1 });
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             mOpenRequestService = false;
    //             action_init_load();
    //         }
    //     }
    // }

    // const action_init_load = async () => {
    //     const ds = browserGet('dataSession');
    //     //console.log(ds);
    //     if (ds != null || ds != undefined) {
    //         loading.setLoading(true, 'Cargando, espere por favor...');
    //         const [res, errors] = await apiPOST(fetch, 'alumno/balcon_servicios', {action:'getMyRequests'});
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         if (errors.length > 0) {
    //             addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
    //             return {
    //                 status: 302,
    //                 redirect: '/'
    //             };
    //         } else {
    //             if (!res.isSuccess) {
    //                 addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
    //                 if (!res.module_access) {
    //                     return {
    //                         status: 302,
    //                         redirect: '/'
    //                     };
    //                 }
    //             } else {
    //                 eBalconyRequests = res.data['eBalconyRequests'];
    //             }
    //         }
    //     }

    // }
    // const deleteRequestService = async (eRequest)=>{
    //     Swal.fire({
    //         html: `            
    //             <div class="mx-15 px-1" style="border-left: 4px solid #e9ecef;border-left-color: #FE9900; ">
    //                 <h3 class="h3 fw-bold" style="color: #1c3247;">Cancelar solicitud</h3>				
    //             </div>                        
    //             ¿Está seguro de eliminar el registro <span style="color: #12216A;"> ${eRequest.descripcion}</span>?                        
    //         `,
    //         icon: 'warning',
    //         showCancelButton: true,
    //         confirmButtonColor: '#12216A',
    //         cancelButtonColor: '#E53F3C',
    //         confirmButtonText: 'Sí, eliminar',
    //         cancelButtonText: 'Cancelar',
    //     }).then( async (result) => {
    //         if (result.isConfirmed) {
    //             const [res, errors] = await apiPOST(fetch, 'alumno/balcon_servicios',{action: 'delRequestService', id: eRequest.id});
    //             if (errors.length > 0) {
    //                 addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
    //                 loading.setLoading(false, 'Cargando, espere por favor...');
    //                 return;
    //             } else {
    //                 if (!res.isSuccess) {
    //                     addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
    //                     if (!res.module_access) {
    //                         goto('/');
    //                     }
    //                     loading.setLoading(false, 'Cargando, espere por favor...');
    //                     return;
    //                 } else {
    //                     addToast({ type: 'success', header: 'Exitoso', body: 'Se elimino correctamente el registro' });
    //                     loading.setLoading(false, 'Cargando, espere por favor...');
    //                     action_init_load();
    //                 }
    //             }
    //         }else{
    //             addToast({ type: 'success', header: 'Notificación', body: 'Genial salvaste el registro' });
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             //action_init_load();
    //         }
    //     });
    // }
    // const asignarConfigStars = (eSurveyProcess)=>{
    //     const config = {
    //         readOnly: false,
    //         countStars: eSurveyProcess.valoracion,
    //         range: {
    //             min: 0,
    //             max: eSurveyProcess.valoracion,
    //             step: 1
    //         },
    //         score: 0,
    //         //showScore: true,
    //         starConfig: {
    //             size: 30,
    //             fillColor: '#F9ED4F',
    //             strokeColor: "#BB8511"
    //         }
    //     }
    //     return config;
    // }
    // const openModalBalconyRequestService = async (eRequest, action, titulo, modalMedida='lg') =>{
    //     title_modal = titulo;
    //     //console.log(ds);
    //     //eBalconyRequest = eRequest;
    //     mSizeRequestService = modalMedida;
    //     modal_action_view = action
    //     const ds = browserGet('dataSession');
    //     if (ds != null || ds != undefined) {
    //         loading.setLoading(true, 'Cargando, espere por favor...');
    //         const [res, errors] = await apiGET(fetch, 'alumno/balcon_servicios', {action:action, id:eRequest.id});
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         if (errors.length > 0) {
    //             addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
    //             return {
    //                 status: 302,
    //                 redirect: '/'
    //             };
    //         } else {
    //             if (!res.isSuccess) {
    //                 addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
    //                 if (!res.module_access) {
    //                     return {
    //                         status: 302,
    //                         redirect: '/'
    //                     };
    //                 }
    //             } else {
    //                 switch (action) {
    //                     case 'getMyRequestService':
    //                         eBalconyRequest = res.data['eBalconyRequest'];
    //                         eRequestServiceObservation = eBalconyRequest.descripcion;
    //                         eBalconyRequestHistories = [];
    //                         eSurveysProcess = [];
    //                         break;
    //                     case 'getViewHistoricalRequestService':
    //                         eBalconyRequest = res.data['eBalconyRequest'];
    //                         eBalconyRequestHistories = res.data['eBalconyRequestHistories'];
    //                         eSurveysProcess = [];
    //                         break;
    //                     case 'getMyRequestQuestionstoQualify':
    //                         eBalconyRequest = res.data['eBalconyRequest'];
    //                         eSurveysProcess = res.data['eSurveysProcess'];
    //                         eBalconyRequestHistories = [];
    //                         break;

    //                 }
    //                 mOpenRequestService = true;
    //                 // modal_view = true;
    //                 // console.log(eBalconyRequestHistories)
    //             }
    //         }
    //     }


    // }
    // const saveQualifyRequestService = async () => {
    //     console.log(eBalconyRequest);
    //     const $frmRequestService = document.querySelector('#frmRequestService');
    //     const formData = new FormData($frmRequestService);
    //     formData.append('id', eBalconyRequest.id);
    //     formData.append('action', 'saveRequestQuestionstoQualify');
    //     let valor_calificacion = '';
    //     let observacion = '';
    //     let eAnswersQuestions = [];
    //     for (const eSurvey of eSurveysProcess) {
    //         console.log('Servicio Calificado', eSurvey);
    //         for (const eQuestion of eSurvey.preguntas) {
    //             console.log('Servicio Calificado', eQuestion.configuracion.score);
    //             valor_calificacion = eQuestion.configuracion.score;
    //             observacion = eQuestion.configuracion.observacion;
    //             if(valor_calificacion == 0){
    //                 addNotification({
    //                     msg: `Favor debe calificar la pregunta "${eQuestion.descripcion}"`,
    //                     type: 'error',
    //                     target: 'newNotificationToast'
    //                 });
    //                 loading.setLoading(false, 'Cargando, espere por favor...');
    //                 return;
    //             }
    //             eAnswersQuestions.push({
    //                 id :eQuestion.id,
    //                 valoracion: valor_calificacion,
    //                 observacion: observacion,
    //             })
    //         }
    //     }
    //     formData.append('eAnswersQuestions', JSON.stringify(eAnswersQuestions));
    //     loading.setLoading(true, 'Guardando la información, espere por favor...');
    //     const [res, errors] = await apiPOSTFormData(fetch, 'alumno/balcon_servicios', formData);

    //     if (errors.length > 0) {
    //         addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         return;
    //     } else {
    //         if (!res.isSuccess) {
    //             addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
    //             if (!res.module_access) {
    //                 goto('/');
    //             }
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             return;
    //         } else {
    //             addToast({ type: 'success', header: 'Exitoso', body: 'Se guardo correctamente los datos' });
    //             dispatch('actionRun', { action: 'nextProccess', value: 1 });
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             mOpenRequestService = false;
    //             action_init_load();
    //         }
    //     }
    // }
    // console.log('Questions', eSurveysProcess)
</script>

<BreadCrumb title={titulo_solicitud} subtitle="Consulta en qué etapa se encuentra tu solicitud y sigue su progreso desde la recepción hasta la aprobación final." items={itemsBreadCrumb} back={backBreadCrumb} />
<div class="row">
    <div class="col-md-12">Ejemplo de la pagina                                             
    </div>
</div>
<!-- <Modal isOpen={mOpenRequestService}
       toggle={mToggleRequestService}
       size={mSizeRequestService}
       class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-fullscreen-md-down"
       backdrop="static"
       fade={false}>
    <ModalHeader toggle={mToggleRequestService}>
        <h4><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-list-ul" viewBox="0 0 16 16">
            <path fill-rule="evenodd" d="M5 11.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm-3 1a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0 4a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0 4a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/>
        </svg>  <b>{title_modal}</b></h4>
    </ModalHeader>
    <ModalBody>

        {#if modal_action_view == 'getMyRequestService'}
            <form id="frmRequestService">
                <div class="card-body">
                    <div class="col-md-12">
                        <label for="eRequestServiceObservation" class="form-label fw-bold">
                            <i title="Campo obligatorio" class="bi bi-exclamation-circle-fill" style="color: red"></i> Descripción:
                        </label>
                        <textarea
                                rows="3"
                                cols="100"
                                type="text"
                                class="form-control"
                                name="descripcion"
                                id="eRequestServiceObservation"
                                bind:value={eRequestServiceObservation}/>
                        <input type="hidden" name="id" value="{eBalconyRequest.id}">
                    </div>
                </div>
            </form>
        {:else if modal_action_view == 'getViewHistoricalRequestService'}
                <table class="table table-bordered">
                    <tbody>
                    <tr>
                        <td colspan="2">
                            <i class="bi bi-upc"></i> {eBalconyRequest.codigo}
                            {#if eBalconyRequest.estado == 1 || eBalconyRequest.estado == 3 }
                                <span class="badge rounded-pill bg-warning">{eBalconyRequest.estado_display}</span>
                            {:else if eBalconyRequest.estado == 4}
                                <span class="badge rounded-pill bg-success">{eBalconyRequest.estado_display}</span>
                            {:else if eBalconyRequest.estado == 2}
                                <span class="badge rounded-pill bg-danger">{eBalconyRequest.estado_display}</span>
                            {:else}
                                <span class="badge rounded-pill bg-info">{eBalconyRequest.estado_display}</span>
                            {/if}
                        </td>
                    </tr>
                    <tr>
                        <td><b>Solicitante:</b> {eBalconyRequest.solicitante} </td>
                        <td><b>Agente:</b> {eBalconyRequest.agente} </td>
                    </tr>
                    </tbody>
                </table>
                <ul class="timeline">
                    {#each eBalconyRequestHistories as eBalconyRequestHistory, indexBalconyRequestHistory}
                        <li  class="{(indexBalconyRequestHistory + 1)  % 2 == 0 ? 'timeline-inverted' : ''}">
                            {@html eBalconyRequestHistory.observacion}
                            <div class="timeline-badge primary">
                                <a>
                                    {#if eBalconyRequestHistory.estado == 1}
                                        <i class="fe fe-plus-circle"></i>
                                    {:else if eBalconyRequestHistory.estado == 2}
                                        <i class="fe fe-clock"></i>
                                    {:else if eBalconyRequestHistory.estado == 3}
                                        <i class="fe fe-user"></i>
                                    {:else if eBalconyRequestHistory.estado == 4}
                                        <i class="fe fe-clock"></i>
                                    {:else }
                                        <i class="fe fe-clock"></i>
                                    {/if}
                                </a>
                            </div>
                            <div class="timeline-panel">
                                <div class="timeline-body">
                                    <b><i class="bi bi-calendar"></i> { eBalconyRequestHistory.fecha_creacion }</b>
                                    {#if eBalconyRequestHistory.estado == 1 }
                                        <span class="badge bg-light-dark">{ eBalconyRequestHistory.estado_display }</span>
                                    {:else if eBalconyRequestHistory.estado == 2 }
                                        <span class="badge bg-info">{ eBalconyRequestHistory.estado_display }</span>
                                    {:else if eBalconyRequestHistory.estado == 3 }
                                        <span class="badge bg-success">{ eBalconyRequestHistory.estado_display }</span>
                                    {:else}
                                        <span class="badge bg-secondary">{ eBalconyRequestHistory.estado_display }</span>
                                    {/if}
                                    {#if eBalconyRequestHistory.asignaenvia}
                                        <p><b><i class="fe fe-user"></i> ¿Quién Asigna? </b><br>{eBalconyRequestHistory.asignaenvia }</p>
                                    {/if}
                                    {#if eBalconyRequestHistory.asignadorecibe }
                                        <p><b><i class="fe fe-user"></i> ¿A quién fue asignado? </b><br>{ eBalconyRequestHistory.asignadorecibe }</p>
                                    {/if }
                                    {#if eBalconyRequestHistory.proceso }
                                        <p><b><i class="mdi mdi-cog"></i> Proceso:</b><br>{ eBalconyRequestHistory.proceso }</p>
                                    {/if}
                                    {#if eBalconyRequestHistory.departamento }
                                        <p><b><i class="bi bi-building"></i> Dirección:</b><br>{eBalconyRequestHistory.departamento }</p>
                                    {/if}
                                    {#if eBalconyRequestHistory.servicio }
                                        <p><b><i class="mdi mdi-hand-clap"></i> Servicio:</b><br>{ eBalconyRequestHistory.servicio }</p>
                                    {/if}
                                    {#if eBalconyRequestHistory.respuestarapida }
                                        <p><b><i class="bi bi-award-fill"></i> Respuesta Rapida:</b><br>{ eBalconyRequestHistory.respuestarapida }</p>
                                    {/if}
                                    {#if eBalconyRequestHistory.observacion }
                                        <p><b><i class="bi bi-file-text"></i> Observación:</b><br> {@html eBalconyRequestHistory.observacion }</p>
                                    {/if}
                                </div>
                                <div class="timeline-footer">
                                    {#if eBalconyRequestHistory.archivo}
                                        <a

                                                href="{variables.BASE_API}{eBalconyRequestHistory.archivo}"
                                                class="btn btn-primary tu"
                                                target="_blank"
                                        > <i class="fe fe-download" aria-hidden="true"></i>
                                            Ver Archivo
                                        </a>
                                    {/if}
                                </div>
                            </div>
                        </li>
                    {/each}
                    <li class="clearfix" style="float: none;"></li>
                </ul>
        {:else if modal_action_view == 'getMyRequestQuestionstoQualify'}
            <form id="frmRequestService">
            {#each eSurveysProcess as eSurveyProcess, indexeSurveyProcess}
                <table class="table">
                    <tbody>
                    {#each eSurveyProcess.preguntas as eQuestion, indexeQuestion}
                        <tr>
                            <th colspan="2">{indexeQuestion + 1}.- ¿{eQuestion.descripcion}?</th>
                        </tr>
                        <tr>
                            <td style="vertical-align: middle; text-align: center">
                                <!--                                <StarRating config={asignarConfigStars(eSurveyProcess)}  id="question{eQuestion.id}"/>-->
                                <!-- <StarRating config={eQuestion.configuracion} />
                            </td>
                            <td>
                                <textarea  class="form-control"
                                           bind:value={eQuestion.configuracion.observacion }
                                           rows="1"
                                           placeholder="Escribir un comentario (opcional)"></textarea>
                            </td>
                        </tr>
                    {/each}
                    </tbody>
                </table>
            {/each}
            </form>
        {/if}
    </ModalBody>
    <ModalFooter>
            <div class="d-grid gap-2 d-md-flex justify-content-md-end">
                {#if modal_action_view == 'getMyRequestService'}
                    <button type="button" class="btn btn-success" on:click={()=> saveRequestService()} >
                        <i class="fe fe-save" aria-hidden="true"></i>  Guardar
                    </button>
                    <a color="danger" class="btn btn-danger" on:click={() => CloseRequestService()}>
                        <i class="fe fe-minus-square" aria-hidden="true"></i>  Cancelar
                    </a>
                {:else  if modal_action_view == 'getMyRequestQuestionstoQualify'}
                    <button type="button" class="btn btn-success" on:click={()=> saveQualifyRequestService()} >
                        <i class="fe fe-check-square" aria-hidden="true"></i>  Guardar calificación
                    </button>
                {:else}
                    <a color="info" class="btn  btn-light" on:click={() => CloseRequestService()}>
                        <i class="fe fe-minus-square" aria-hidden="true"></i>  Cancelar
                    </a>
                {/if}
            </div>
    </ModalFooter>
</Modal> --> 

<!-- <svelte:head>
    <link href="/static/css/timeline/timeline.css" rel="stylesheet" />
</svelte:head> -->
<style>
    .table-transform{
        background: #D1E3F3 !important;
    }
    .text-light > tr > th > p{
        color: #182F44;
    }
    .bg-warning{
        background: #FFC96B;
    }
    .bg-success{
        background: #209884;
    }
    .bg-danger{
        background: #E93939;
    }
    .bg-info{
        background: #9E68DC;
    }
    .table-transform th{
        color: #182F44;
    } 
    .options_balcon{
        color: #D1E3F3;
    }

    .active_option {
        color: #182F44; 
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

    .stars > svg:hover{
        background: #0a53be;
    }
</style>
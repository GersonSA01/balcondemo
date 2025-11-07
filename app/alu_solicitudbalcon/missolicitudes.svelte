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
    import Swal from 'sweetalert2';
    import { onMount } from 'svelte';
    import { variables } from '$lib/utils/constants';
    import BreadCrumb from '$components/BreadCrumb/BreadCrumb.svelte';
    import { loading } from '$lib/store/loadingStore';
    import FilePond, { registerPlugin, supported } from 'svelte-filepond';
    import FilePondPluginFileValidateType from 'filepond-plugin-file-validate-type';
    //import { Fancybox, Carousel, Panzoom } from "@fancyapps/ui";
    //import '@fancyapps/ui/dist/fancybox.css';
    import StarRating from '@ernane/svelte-star-rating';
    import { createEventDispatcher, onDestroy } from 'svelte';
    const dispatch = createEventDispatcher();
    import { goto } from '$app/navigation';
    import { navigating } from '$app/stores';
    import { addNotification } from '$lib/store/notificationStore';
    import {Modal, ModalBody, ModalFooter, ModalHeader, Tooltip} from 'sveltestrap';
    import {FilePondFile} from "filepond";
    export let eBalconyRequests;
    let itemsBreadCrumb = [{ text: 'Balcón servicio', active: true, href: '/alu_solicitudbalcon' },{ text: 'Mis Solicitudes', active: true, href: undefined }];
    let backBreadCrumb = { href: '/alu_solicitudbalcon', text: '<i class="bi bi-chevron-left"></i> Regresar' };
    $: loading.setNavigate(!!$navigating);
    $: loading.setLoading(!!$navigating, 'Cargando, espere por favor...');
    console.log(eBalconyRequests);
    let mSizeRequestService = 'lg';
    let mOpenRequestService = false;
    let request_id = '';
    let eRequestServiceObservation = '';
    let textService = '';
    let eService = {};
    let eRequirements = {};
    let eBalconyRequest = {};
    let eBalconyRequestHistories = [];
    let eSurveysProcess = [];
    let modal_view = false;
    let modal_action_view = false;
    let title_modal = '';
    // Fancybox.bind("[data-fancybox]", {
    //     // Your options go here
    // });
    const mToggleRequestService = () => (mOpenRequestService = !mOpenRequestService );

    const CloseRequestService = () =>{
        mOpenRequestService = false;
    }
    const saveRequestService = async () => {
        console.log(eBalconyRequest);
        const $frmRequestService = document.querySelector('#frmRequestService');
        const formData = new FormData($frmRequestService);
        formData.append('action', 'editRequestService');
        if (!eRequestServiceObservation) {
            addNotification({
                msg: 'Favor complete el campo de descripción',
                type: 'error',
                target: 'newNotificationToast'
            });
            loading.setLoading(false, 'Cargando, espere por favor...');
            return;
        }
        loading.setLoading(true, 'Guardando la información, espere por favor...');
        const [res, errors] = await apiPOSTFormData(fetch, 'alumno/balcon_servicios', formData);

        if (errors.length > 0) {
            addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
            loading.setLoading(false, 'Cargando, espere por favor...');
            return;
        } else {
            if (!res.isSuccess) {
                addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
                if (!res.module_access) {
                    goto('/');
                }
                loading.setLoading(false, 'Cargando, espere por favor...');
                return;
            } else {
                addToast({ type: 'success', header: 'Exitoso', body: 'Se guardo correctamente los datos' });
                dispatch('actionRun', { action: 'nextProccess', value: 1 });
                loading.setLoading(false, 'Cargando, espere por favor...');
                mOpenRequestService = false;
                action_init_load();
            }
        }
    }

    const action_init_load = async () => {
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

    }
    const deleteRequestService = async (eRequest)=>{
        Swal.fire({
            html: `            
                <div class="mx-15 px-1" style="border-left: 4px solid #e9ecef;border-left-color: #FE9900; ">
                    <h3 class="h3 fw-bold" style="color: #1c3247;">Cancelar solicitud</h3>				
                </div>                        
                ¿Está seguro de eliminar el registro <span style="color: #12216A;"> ${eRequest.descripcion}</span>?                        
            `,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#12216A',
            cancelButtonColor: '#E53F3C',
            confirmButtonText: 'Sí, eliminar',
            cancelButtonText: 'Cancelar',
        }).then( async (result) => {
            if (result.isConfirmed) {
                const [res, errors] = await apiPOST(fetch, 'alumno/balcon_servicios',{action: 'delRequestService', id: eRequest.id});
                if (errors.length > 0) {
                    addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
                    loading.setLoading(false, 'Cargando, espere por favor...');
                    return;
                } else {
                    if (!res.isSuccess) {
                        addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
                        if (!res.module_access) {
                            goto('/');
                        }
                        loading.setLoading(false, 'Cargando, espere por favor...');
                        return;
                    } else {
                        addToast({ type: 'success', header: 'Exitoso', body: 'Se elimino correctamente el registro' });
                        loading.setLoading(false, 'Cargando, espere por favor...');
                        action_init_load();
                    }
                }
            }else{
                addToast({ type: 'success', header: 'Notificación', body: 'Genial salvaste el registro' });
                loading.setLoading(false, 'Cargando, espere por favor...');
                //action_init_load();
            }
        });
    }
    const asignarConfigStars = (eSurveyProcess)=>{
        const config = {
            readOnly: false,
            countStars: eSurveyProcess.valoracion,
            range: {
                min: 0,
                max: eSurveyProcess.valoracion,
                step: 1
            },
            score: 0,
            //showScore: true,
            starConfig: {
                size: 30,
                fillColor: '#F9ED4F',
                strokeColor: "#BB8511"
            }
        }
        return config;
    }
    const openModalBalconyRequestService = async (eRequest, action, titulo, modalMedida='lg') =>{
        title_modal = titulo;
        //console.log(ds);
        //eBalconyRequest = eRequest;
        mSizeRequestService = modalMedida;
        modal_action_view = action
        const ds = browserGet('dataSession');
        if (ds != null || ds != undefined) {
            loading.setLoading(true, 'Cargando, espere por favor...');
            const [res, errors] = await apiGET(fetch, 'alumno/balcon_servicios', {action:action, id:eRequest.id});
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
                    switch (action) {
                        case 'getMyRequestService':
                            eBalconyRequest = res.data['eBalconyRequest'];
                            eRequestServiceObservation = eBalconyRequest.descripcion;
                            eBalconyRequestHistories = [];
                            eSurveysProcess = [];
                            break;
                        case 'getViewHistoricalRequestService':
                            eBalconyRequest = res.data['eBalconyRequest'];
                            eBalconyRequestHistories = res.data['eBalconyRequestHistories'];
                            eSurveysProcess = [];
                            break;
                        case 'getMyRequestQuestionstoQualify':
                            eBalconyRequest = res.data['eBalconyRequest'];
                            eSurveysProcess = res.data['eSurveysProcess'];
                            eBalconyRequestHistories = [];
                            break;

                    }
                    mOpenRequestService = true;
                    // modal_view = true;
                    // console.log(eBalconyRequestHistories)
                }
            }
        }


    }
    const saveQualifyRequestService = async () => {
        console.log(eBalconyRequest);
        const $frmRequestService = document.querySelector('#frmRequestService');
        const formData = new FormData($frmRequestService);
        formData.append('id', eBalconyRequest.id);
        formData.append('action', 'saveRequestQuestionstoQualify');
        let valor_calificacion = '';
        let observacion = '';
        let eAnswersQuestions = [];
        for (const eSurvey of eSurveysProcess) {
            console.log('Servicio Calificado', eSurvey);
            for (const eQuestion of eSurvey.preguntas) {
                console.log('Servicio Calificado', eQuestion.configuracion.score);
                valor_calificacion = eQuestion.configuracion.score;
                observacion = eQuestion.configuracion.observacion;
                if(valor_calificacion == 0){
                    addNotification({
                        msg: `Favor debe calificar la pregunta "${eQuestion.descripcion}"`,
                        type: 'error',
                        target: 'newNotificationToast'
                    });
                    loading.setLoading(false, 'Cargando, espere por favor...');
                    return;
                }
                eAnswersQuestions.push({
                    id :eQuestion.id,
                    valoracion: valor_calificacion,
                    observacion: observacion,
                })
            }
        }
        formData.append('eAnswersQuestions', JSON.stringify(eAnswersQuestions));
        loading.setLoading(true, 'Guardando la información, espere por favor...');
        const [res, errors] = await apiPOSTFormData(fetch, 'alumno/balcon_servicios', formData);

        if (errors.length > 0) {
            addToast({ type: 'error', header: 'Ocurrio un error', body: errors[0].error });
            loading.setLoading(false, 'Cargando, espere por favor...');
            return;
        } else {
            if (!res.isSuccess) {
                addToast({ type: 'error', header: 'Ocurrio un error', body: res.message });
                if (!res.module_access) {
                    goto('/');
                }
                loading.setLoading(false, 'Cargando, espere por favor...');
                return;
            } else {
                addToast({ type: 'success', header: 'Exitoso', body: 'Se guardo correctamente los datos' });
                dispatch('actionRun', { action: 'nextProccess', value: 1 });
                loading.setLoading(false, 'Cargando, espere por favor...');
                mOpenRequestService = false;
                action_init_load();
            }
        }
    }
    console.log('Questions', eSurveysProcess);

    function toggleExtraColumns(rowIndex) {
        
        document.querySelectorAll(".extra-header").forEach((header) => {
            header.classList.toggle("d-none");
            header.classList.toggle("d-sm-none");
        });
        
        const row = document.querySelectorAll("tbody tr")[rowIndex];
        
        row.querySelectorAll(".extra-column").forEach((column) => {
            console.log(column);
            column.classList.toggle("d-none");
            column.classList.toggle("d-sm-none");
        });
    }

</script>
<svelte:head>
	<title>Mis solicitudes </title>
</svelte:head>

<BreadCrumb title="Mis solicitudes" subtitle="Revisa el estado y los detalles de cada una de tus solicitudes. Aquí podrás consultar el historial, evidencias y la resolución de cada trámite." items={itemsBreadCrumb} back={backBreadCrumb} />
<!--<a href="http://media.w3.org/2010/05/sintel/trailer.mp4" data-fancybox>-->
<!--    Video-->
<!--</a>-->
<!--<a-->
<!--        data-fancybox-->
<!--        data-type="pdf"-->
<!--        href="http://127.0.0.1:8000/media/solicitudbalcon/solicitud_20221121104413.pdf"-->
<!--&gt;Click me</a-->
<!--&gt;-->
<div class="row mx-2">
    <div class="col-md-12 table-responsive">                                
        <table class="table mb-0 table-hover">
            <thead class="table-transform">
                <tr>
                    <th scope="col" class="text-center d-md-none d-lg-none d-xl-none">+/-</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize" style="text-align: center;width: 5rem;">N° Solicitud</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize" style="text-align: center;width: 15rem;">Fecha</th>                    
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize" style="text-align: center;width: 40rem;">Motivo</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize d-sm-none d-sm-table-cell d-md-table-cell extra-header" style="text-align: center;width: 5rem;">Solicitud</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize d-sm-none d-sm-table-cell d-md-table-cell extra-header" style="text-align: center;width: 10rem;">Requisitos</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize" style="text-align: center;width: 10rem;">Estado</th>
                    <th scope="col" class="border-top-0 text-center align-middle text-capitalize d-sm-none d-sm-table-cell d-md-table-cell extra-header " style="text-align: center;width: 10rem;">Url</th>
                    <th  class="border-top-0 text-center align-middle text-capitalize" style="text-align: center;width: 10rem;">Acciones</th>
                </tr>
            </thead>
            <tbody class="table-light">
                {#each eBalconyRequests as eRequest, index}
                    <tr>
                        <td class="text-center p-0 m-0 align-middle d-md-none d-lg-none d-xl-none">                                
                            <button class="btn btn-sm btn-outline-secondary toggle-btn" on:click={() => toggleExtraColumns(index)}> +/- </button>
                        </td>
                        <td class="fs-6 p-0 m-0 align-middle" style="text-align: center;">
                            <p class="mb-1 ">
                                {eRequest.numero_display}
                            </p>
                        </td>
                        <td class="fs-6 p-0 m-0 align-middle" style="text-align: center;">{eRequest.fecha_creacion_v2}<br>{eRequest.hora_creacion_v2}</td>                       
                        <td class="fs-6 text-wrap p-0 m-0 align-middle text-capitalize">{eRequest.descripcion}</td>
                        <td class="fs-6 p-0 m-0 align-middle d-sm-none d-sm-table-cell d-md-table-cell extra-column" style="text-align: center;">
                            {#if eRequest.archivo}
                                {#if eRequest.typefile != '.pdf' }
                                    <a data-fancybox="image" class="btn tu text-dark-info fs-3"
                                        id="{`tooltip-doc-request${eRequest.id}`}"
                                        href="{ eRequest.archivo }">
                                        <i class="bi bi-file-image"></i>
                                    </a>
                                {:else}
                                    <a data-fancybox data-type="pdf" data-preload="false"  class="btn tu text-danger fs-3"
                                        id="{`tooltip-doc-request${eRequest.id}`}"
                                        href="{variables.BASE_API}{ eRequest.archivo }">
                                        <i class="bi bi-file-pdf"></i>
                                    </a>
                                {/if}
                                <Tooltip target={`tooltip-doc-request${eRequest.id}`} placement="top">
                                    Ver solicitud
                                </Tooltip>
                            {/if}
                        </td>
                        <td class="fs-6 p-0 m-0 align-middle d-sm-none d-sm-table-cell d-md-table-cell extra-column" style="text-align: center;">
                            {#each eRequest.requisitos as requisito}
                                <a data-fancybox data-type="pdf" class="btn-sm tu text-danger fs-3"
                                    id="{`tooltip-doc-request-req${requisito.id}`}"
                                    href="{variables.BASE_API}{requisito.archivo }">
                                    <i class="bi bi-file-pdf"></i>
                                </a>
                                    <Tooltip target={`tooltip-doc-request-req${requisito.id}`} placement="top">
                                        Ver <span class="text-lowercase">{requisito.descripcion}</span>
                                    </Tooltip>
                            {/each}
                        </td>
                        <td  class="fs-6 p-0 m-0 align-middle" style="text-align: center;">
                            {#if eRequest.estado == 1 || eRequest.estado == 3 }
                                <span class="badge bg-warning">{eRequest.estado_display}</span>
                            {:else if eRequest.estado == 4}
                                <span class="badge bg-success">{eRequest.estado_display}</span>
                            {:else if eRequest.estado == 2}
                                <span class="badge bg-danger">{eRequest.estado_display}</span>
                            {:else}
                                <span class="badge bg-info">{eRequest.estado_display}</span>
                            {/if}                                                                                                                              
                        </td>
                        <td class="fs-6 p-0 m-0 align-middle d-sm-none d-sm-table-cell d-md-table-cell extra-column" style="text-align: center;">
                            {#if eRequest.urlservice != null && eRequest.urlservice != ''}
                                <a class="btn btn-sm solicitar-btn"
                                                target="_blank"
                                                id="{`tooltip-ver-request${eRequest.id}`}"
                                                href="{eRequest.urlservice}">
                                                <i class="bi bi-link"></i>
                                            </a>
                                            <Tooltip target={`tooltip-ver-request${eRequest.id}`}
                                                        placement="top">
                                                Redireccionar a url
                                            </Tooltip>
                                {/if}
                        </td>
                        <td class="fs-6 p-0 m-0 align-middle" style="text-align: center;">
                            {#if eRequest.puede_calificar_proceso}
                                    <a class="fs-6 btn btn-warning btn-sm p-1" href="javascript:void(0)"
                                    on:click={() => openModalBalconyRequestService(eRequest, 'getMyRequestQuestionstoQualify', 'CALIFICAR SERVICIO', 'lg' )}>
                                        <span class="bi bi-stars" aria-hidden="true"></span>
                                        Calificar Servicio
                                </a>
                            {:else}                                                                                            
                            
                            <!-- <div class="dropdown dropstart">
                                <a class="btn-icon btn btn-ghost btn-sm rounded-circle dropdown-toggle"
                                    href="#" role="button" id="dropdownMenuLink" data-bs-toggle="dropdown" aria-expanded="false">
                                    <i class="fe fe-more-vertical s-Lh7wy2yC8v9c"></i>
                                </a>
                                <ul class="dropdown-menu" aria-labelledby="dropdownMenuLink" style=""> -->
                                    
                                        <!-- <li>
                                            <button class="btn btn-sm"
                                                on:click={() => openModalBalconyRequestService(eRequest, 'getMyRequestService', 'EDITAR SOLICITUD')}
                                                >
                                                <span class="fe fe-edit" aria-hidden="true"></span> Editar
                                            </button>
                                        </li> -->                                            
                                        
                                        <a  class="fs-3" href="/alu_solicitudbalcon/followup/{eRequest.id}" id="{`tooltip-ver-seguimiento${eRequest.id}`}" >
                                            <img src="{variables.BASE_API_STATIC}/images/iconos/seguimiento_balcon.svg" alt="" style="width: 20px;"/>
                                        </a>
                                        <Tooltip target={`tooltip-ver-seguimiento${eRequest.id}`} placement="top">Seguimiento de solicitud</Tooltip>
                                        <!-- <a class="fs-3 top-0 end-0" id="{`tooltip-ver-seguimiento${eRequest.id}`}" 
                                            on:click={() => { 
                                                if (eRequest.detalle && eRequest.estado != 1) {
                                                    openModalBalconyRequestService(eRequest, 'getViewHistoricalRequestService', 'VER SEGUIMIENTO')
                                                }
                                            }}    
                                        >
                                            <img src="{variables.BASE_API_STATIC}/images/iconos/seguimiento_balcon.svg" alt="" style="width: 25%;"/>
                                        </a>
                                        <Tooltip target={`tooltip-ver-seguimiento${eRequest.id}`} placement="top">Seguimiento de solicitud</Tooltip>  -->
                                        
                                        <a class="fs-3 options_balcon {eRequest.estado === 1 ? 'active_option' : ''}" id="{`tooltip-eliminar${eRequest.id}`}"                                                     
                                            on:click={() => { 
                                                if (eRequest.estado === 1) {
                                                    deleteRequestService(eRequest);
                                                }
                                            }}>
                                            <i class="fe fe-trash" aria-hidden="true"></i>
                                        </a>   
                                        <Tooltip target={`tooltip-eliminar${eRequest.id}`} placement="top">Cancelar solicitud</Tooltip>                                         
                                                                                                                                                                                                                                        
                                    
                                    <!--{#if eRequest.puede_calificar_proceso}-->
                                    <!--    <li>-->
                                    <!--        <button class="dropdown-item" on:click={() => openModalBalconyRequestService(eRequest, 'getMyRequestQuestionstoQualify', 'CALIFICAR SERVICIO', 'lg' )}>-->
                                    <!--            <span class="bi bi-stars" aria-hidden="true"></span> Calificar Servicio-->
                                    <!--        </button>-->
                                    <!--    </li>-->
                                    <!--{/if}-->
                                <!-- </ul>
                            </div> -->
                            {/if}
                        </td>
                    </tr>
                {/each}
            </tbody>
        </table>                     
    </div>
</div>
<Modal isOpen={mOpenRequestService}
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
                                <StarRating config={eQuestion.configuracion} />
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
</Modal>

<!-- <svelte:head>
    <link href="/static/css/timeline/timeline.css" rel="stylesheet" />
</svelte:head> -->
<style>
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
        background: #D1E3F3 !important;
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
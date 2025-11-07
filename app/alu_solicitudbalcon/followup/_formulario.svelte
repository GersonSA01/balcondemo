<script>
	import { createEventDispatcher, onMount } from 'svelte';	  
    import { addToast } from "$lib/store/toastStore";
    import { apiPOSTFormData, apiPOST, browserGet, apiGET} from "$lib/utils/requestUtils";
    import FilePond, { registerPlugin, supported } from 'svelte-filepond';  
    import { loading } from '$lib/store/loadingStore';
    import { goto } from '$app/navigation';
    import { addNotification } from '$lib/store/notificationStore';
    import { variables } from '$lib/utils/constants';
  import { Modal, ModalBody, ModalFooter, ModalHeader } from 'sveltestrap';
  import StarRating from '@ernane/svelte-star-rating';
    let item = 0;
    let actionItem = '';
	export let eSolicitud;
    export let eRequirements;
    export let eBalconyRequests;
    let filePondInstances = {}; 
	let nameDocumento = 'fileDocumento';
    let eRequestServiceObservation = eSolicitud.descripcion;
    let pondDocumento;
    let mOpenFormularioRequestService = true;
    let ePuedeCalificar = eSolicitud.puede_calificar_proceso;
    let mSizeRequestService = 'lg';
    let title_modal = '';
    let modal_action_view = false;
    let eBalconyRequest = {};
    let eBalconyRequestHistories = [];
    let eSurveysProcess = [];
    let mOpenRequestService = false;

	onMount(async () => {		
	});

    // console.log('eSolicitud form');
    // console.log(eSolicitud);
    // console.log('eRequirements');
    // console.log(eRequirements);
    const mToggleRequestService = () => (mOpenRequestService = !mOpenRequestService );

    const CloseRequestService = () =>{
        mOpenRequestService = false;
    }
	const dispatch = createEventDispatcher();

    const actionLoad = (action, link) => {		
        item = link;
        actionItem = action       
        dispatch('actionRun', { action: actionItem, data: { item: item } });
      };

    const action_init_load = async () => {
        const ds = browserGet('dataSession');
        // console.log(ds);
        debugger;
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

    function handleFileChange(eDetRequisito, file) {
        // Aquí puedes actualizar eDetRequisito.archivo con el nuevo archivo
        eDetRequisito.archivo = URL.createObjectURL(file.file);
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
        // console.log(eBalconyRequest);
        const $frmRequestService = document.querySelector('#frmRequestService');
        const formData = new FormData($frmRequestService);
        formData.append('id', eBalconyRequest.id);
        formData.append('action', 'saveRequestQuestionstoQualify');
        let valor_calificacion = '';
        let observacion = '';
        let eAnswersQuestions = [];
        for (const eSurvey of eSurveysProcess) {
            // console.log('Servicio Calificado', eSurvey);
            for (const eQuestion of eSurvey.preguntas) {
                // console.log('Servicio Calificado', eQuestion.configuracion.score);
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
                location.reload()
                // action_init_load();
            }
        }
    }

    const saveRequestService = async () => {
        // console.log(eSolicitud);
        const $frmRequestService = document.querySelector('#frmRequestService');
        const formData = new FormData($frmRequestService);
        formData.append('action', 'correctRequestService');
        if (!eRequestServiceObservation) {
            addNotification({
                msg: 'Favor complete el campo de descripción',
                type: 'error',
                target: 'newNotificationToast'
            });
            loading.setLoading(false, 'Cargando, espere por favor...');
            return;
        }
        let fileDocumento = pondDocumento.getFiles();
            if (fileDocumento.length == 0) {
                addNotification({
                    msg: 'Debe subir un archivo',
                    type: 'error',
                    target: 'newNotificationToast'
                });
                loading.setLoading(false, 'Cargando, espere por favor...');
                return;
            }
            if (fileDocumento.length > 1) {
                addNotification({
                    msg: 'Archivo de documento debe ser único',
                    type: 'error',
                    target: 'newNotificationToast'
                });
                loading.setLoading(false, 'Cargando, espere por favor...');
                return;
            }
            let eFileDocumento = undefined;
            if (pondDocumento && pondDocumento.getFiles().length > 0) {
                eFileDocumento = pondDocumento.getFiles()[0];
            }
            formData.append('file_uprequest', eFileDocumento.file);
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
                // dispatch('actionRun', { action: 'nextProccess', value: 1 });
                loading.setLoading(false, 'Cargando, espere por favor...');
                goto('/alu_solicitudbalcon/missolicitudes_new');
                // mOpenFormularioRequestService = false;
                // action_init_load();
            }
        }
    }

    // const ClearRequestService = () =>{
    //     mOpenFormularioRequestService = false;
    // }

</script>

<div class="formulario-solicitud">
    {#if ePuedeCalificar}
        <div class="califica-box col-12 result-info d-flex align-items-center mb-6">        
            <div class="col-9 text-left">
                <img src="{variables.BASE_API_STATIC}/images/iconos/seguimiento_balcon_estrellas.svg" alt="" style="width: 25%;"/>
                <h5 class="califica-title">¡Tu opinión nos impulsa a mejorar!</h5>
                <p class="califica-text">Nos importa lo que piensas. Al finalizar tu solicitud, tómate un momento para evaluar nuestro servicio.</p>
            </div>
            <div class="col-3 text-end">
                <a class="btn btn-primary califica-btn" href="javascript:void(0)"  on:click={() => openModalBalconyRequestService(eSolicitud, 'getMyRequestQuestionstoQualify', 'CALIFICAR SERVICIO', 'lg' )}>
                    <span class="bi bi-stars" aria-hidden="true"></span> Calificar Servicio
                </a>
            </div>
        </div>  
    {:else}
        {#if !(eSolicitud.estado === 6)}
            <div class="card card-hover mb-lg-4 mt-3">
                <img src='/assets/images/background/balcon_info_2.png' alt='Imagen 1' class="img-fluid w-100 rounded-top-md" />
            </div>
        {/if}
    {/if}

    {#if eSolicitud.estado === 6}
        <div class="mx-4 px-1" style="border-left: 4px solid #e9ecef;border-left-color: #FE9900; ">
            <h3 class="h3 fw-bold" style="color: #1c3247;">Corrección de la solicitud</h3>
        </div>
        <form id="frmRequestService" on:submit|preventDefault={saveRequestService}>
            <div class="card-body">
                <div class="col-md-12">
                    <label for="eRequestServiceObservation" class="form-label fw-bold mx-3 mt-2">
                        Descripción*:
                    </label>
                    <textarea
                            rows="5"
                            cols="100"
                            class="form-control"
                            name="descripcion"
                            id="eRequestServiceObservation"
                            placeholder="Solicitud inicial: {eRequestServiceObservation}"/>
                    <input type="hidden" name="id" value="{eSolicitud.id}">

                    <label for="ePersonaFileDocumento" class="form-label fw-bold mx-3 mt-2">
                        Archivo*:
                    </label>
                    <FilePond
                        class="pb-0 mb-0 "
                        id="ePersonaFileDocumento"
                        bind:this={pondDocumento}
                        name="fileDocumento"
                        labelIdle={['<span class="filepond--label"><i class="bi bi-file-earmark-arrow-up" style="font-size: 150%;"></i> Arrastre y suelte el archivo o haga clic aquí.</span>']}
                        allowMultiple={true}
                        maxFiles="1"
                    />
                    {#if eSolicitud.archivo }
                        <p class="mx-3 mt-2">
                            Archivo existente: <a class="btn text-info p-0 m-0" href="{variables.BASE_API}{ eSolicitud.archivo }">Ver archivo</a>
                        </p>
                    {/if}
                    <p class="fst-italic mx-3 mt-2">Recuerda que el archivo debe ser en formato PDF y tener un peso máximo 4 Mb. {#if eSolicitud.archivo}<strong> Subir un nuevo archivo reemplazará el actual.</strong>{/if}</p>
                    {#if eSolicitud.requisitos.length > 0 }
                    <hr>
                    <label for="ePersonaFileDocumentoRequisitos" class="form-label fw-bold mx-3">
                        REQUISITOS:
                    </label>
                    <div class="col-md-12 mb-3">
                        {#each eSolicitud.requisitos as eDetRequisito}
                            <div class="col-md-12 mb-3">
                                <label for="eRequestServiceDocument{eDetRequisito.id}" class="form-label fw-bold mx-3 mt-2">
                                    {eDetRequisito.requisito.requisito.descripcion_minus}
                                    {#if eDetRequisito.requisito.obligatorio}*{/if}:
                                </label>

                                <FilePond
                                    class="pb-0 mb-0"
                                    id="eRequestServiceDocument{eDetRequisito.id}"
                                    bind:this={filePondInstances[eDetRequisito.id]}
                                    {nameDocumento}
                                    name="file_{eDetRequisito.id}"
                                    labelIdle={['<span class="filepond--label"><i class="bi bi-file-earmark-arrow-up" style="font-size: 150%;"></i> Arrastre y suelte el archivo o haga clic aquí.</span>']}
                                    allowMultiple={false}
                                    credits=""
                                    acceptedFileTypes={['application/pdf']}
                                    labelInvalidField="El campo contiene archivos no válidos"
                                    maxFiles="1"
                                    maxParallelUploads="1"
                                    onaddfile={({ detail }) => handleFileChange(eDetRequisito, detail)}
                                />
                                {#if eDetRequisito.archivo }
                                <p class="mx-3 mt-2">
                                    Archivo existente: <a class="btn text-info p-0 m-0" href="{variables.BASE_API}{ eDetRequisito.archivo }">Ver archivo</a>
                                </p>
                                {/if}
                                <p class="fst-italic mx-3 mt-2">Recuerda que el archivo debe ser en formato PDF y tener un peso máximo de 4 MB.
                                    {#if eDetRequisito.archivo}<strong> Subir un nuevo archivo reemplazará el actual.</strong>{/if}
                                </p>
                            </div>
                        {/each}
                    </div>
                {/if}


                </div>
            </div>


        <div class="text-muted mb-6">
            <div class="d-grid gap-2 d-md-flex justify-content-md-center">
<!--                <a class="btn btn-danger px-5" on:click={() => actionLoad('closeFormularioService', eService.id)}> Cerrar</a>-->
                <button type="submit" class="btn enviar-btn px-5">Enviar</button>
            </div>
        </div>
        </form>
    {:else}
        {#if ePuedeCalificar}
            <div class="card card-hover mb-lg-4 mt-3">
                <img src='/assets/images/background/balcon_info_2.png' alt='Imagen 1' class="img-fluid w-100 rounded-top-md" />
            </div>
        {/if}

    {/if}
</div>
<Modal isOpen={mOpenRequestService} toggle={mToggleRequestService} size={mSizeRequestService} class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-fullscreen-md-down" backdrop="static" fade={false}>
    <ModalHeader toggle={mToggleRequestService}>
        <h4>
            <i class="bi bi-stars"/>
            <b>{title_modal}</b>
        </h4>
    </ModalHeader>
    <ModalBody>
        <h5> <strong>¿Qué tan satisfecho(a) está con...?</strong> </h5>
    {#if modal_action_view == 'getMyRequestQuestionstoQualify'}
        <form id="frmRequestService">
            {#each eSurveysProcess as eSurveyProcess, indexeSurveyProcess}
                <table class="table">
                    <tbody>
                        {#each eSurveyProcess.preguntas as eQuestion, indexeQuestion}
                            <tr>
                                <th colspan="2">{indexeQuestion + 1}.- {eQuestion.descripcion}</th>
                            </tr>
                            <tr>
                                <td style="vertical-align: middle; text-align: center">
                                    <!-- Contenedor principal -->
                                    <div style="display: flex; align-items: center; justify-content: center; gap: 10px; position: relative;">
                                        <!-- Texto "NADA SATISFECHO" -->
                                        <div style="text-align: right; width: 100px; display: flex; align-items: center; justify-content: flex-end;">
                                            <span style="font-size: 12px;">NADA SATISFECHO</span>
                                        </div>

                                        <!-- Contenedor de estrellas y números -->
                                        <div style="display: inline-block; text-align: center; position: relative;">
                                            <!-- StarRating component -->
                                            <StarRating
                                                config={eQuestion.configuracion}
                                            />

                                            <!-- Números debajo de cada estrella -->
                                            <div style="position: absolute; top: 35px; left: 0; width: 100%; display: flex; justify-content: space-around;">
                                                {#each Array(5) as _, i}
                                                    <div style="text-align: center;">
                                                        <!-- Número -->
                                                        <span style="font-size: 12px; display: block;">{i + 1}</span>
                                                    </div>
                                                {/each}
                                            </div>
                                        </div>

                                        <!-- Texto "TOTALMENTE SATISFECHO" -->
                                        <div style="text-align: left; width: 100px; display: flex; align-items: center; justify-content: flex-start;">
                                            <span style="font-size: 12px;">TOTALMENTE SATISFECHO</span>
                                        </div>
                                    </div>
                                    <br>
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
                <button type="button" class="btn btn-success" on:click={() => saveRequestService()}>
                    <i class="fe fe-save" aria-hidden="true"></i> Guardar
                </button>
                <a class="btn btn-danger" on:click={() => CloseRequestService()}>
                    <i class="fe fe-minus-square" aria-hidden="true"></i> Cancelar
                </a>
            {:else if modal_action_view == 'getMyRequestQuestionstoQualify'}
                <button type="button" class="btn btn-success" on:click={() => saveQualifyRequestService()}>
                    <i class="fe fe-check-square" aria-hidden="true"></i> Guardar calificación
                </button>
            {:else}
                <a class="btn btn-light" on:click={() => CloseRequestService()}>
                    <i class="fe fe-minus-square" aria-hidden="true"></i> Cancelar
                </a>
            {/if}
        </div>
    </ModalFooter>
</Modal>
<!-- Estilos -->
<style>

    .califica-title {
        font-size: 1.25rem;
        font-weight: bold;
        color: #12216A;        
    }
   
	.califica-box {
        background-color: #EEF8FE;        		
        padding: 1.5rem;        
        color: #707070; /* Color gris suave */
    }
	
    .califica-text {
        font-size: 0.875rem;
        color: #707070; /* Texto en gris */
    }  
    
    .califica-btn {
		background-color: #0A4985; 
		color: #FFFFFF;		
		border-radius: 10px; /* Botón redondeado */		
		font-size: 0.8rem;					
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
		transition: background-color 0.3s ease;
	}

	.califica-btn:hover {
		background-color: #083b6e; /* Cambio de color en hover */
		font-weight: bold;
	}	
    
    .btn-danger{
        border-radius: 10px; /* Botón redondeado */		
		font-size: 0.8rem;					
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
		transition: background-color 0.3s ease;
    }
    .enviar-btn {
		background-color: #0A4985; 
		color: #FFFFFF;		
		border-radius: 10px; /* Botón redondeado */		
		font-size: 0.8rem;					
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
		transition: background-color 0.3s ease;
	}

	.enviar-btn:hover {
		background-color: #081863;
		font-weight: bold;
	}

    :global(.filepond--credits){
        display: none;
    }

    :global(.filepond--label) {
        color: #5A70D9 !important;    
    }

    :global(.filepond--drop-label) {
        background: #D2D8F8 !important; 
        background-color: #D2D8F8 !important;
    }
    :global(.filepond--drop-label:hover) {
        background-color: #A4AFEC !important;
    }

</style>
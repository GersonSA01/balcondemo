<script>
	import { createEventDispatcher, onMount } from 'svelte';	  
    import { addToast } from "$lib/store/toastStore";
    import { apiPOSTFormData, apiPOST, browserGet, apiGET} from "$lib/utils/requestUtils";
    import FilePond, { registerPlugin, supported } from 'svelte-filepond';  
    import { loading } from '$lib/store/loadingStore';
    import { addNotification } from '$lib/store/notificationStore';
  import { goto } from '$app/navigation';
    let item = 0;
    let actionItem = '';
	export let eService;
    export let eRequirements;
    export let eListaSolicitudes;
	let nameDocumento = 'fileDocumento';
    let eRequestServiceObservation = "";
    let pondDocumento;

	onMount(async () => {		
	});

    // console.log('eService form');
    // console.log(eService);
    // console.log('eRequirements');
    // console.log(eRequirements);

	const dispatch = createEventDispatcher();

    const actionLoad = (action, link) => {		
        item = link;
        actionItem = action       
		dispatch('actionRun', { action: actionItem, data: { item: item } });    
	};

    const saveRequestServicess = async () => {
        const $frmRequestService = document.querySelector('#frmRequestService');
        const formData = new FormData($frmRequestService);

        formData.append('action', 'addRequestService');
        formData.append('service_id', eService.id);
        formData.append('tipo', '2');

        if (!eRequestServiceObservation) {
            addNotification({
                msg: 'Favor complete el campo de descripción',
                type: 'error',
                target: 'newNotificationToast'
            });
            loading.setLoading(false, 'Cargando, espere por favor...');
            return;
        } else {
            formData.append('descripcion', eRequestServiceObservation);
        }
        if(eService.proceso.subesolicitud){
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
        }

        let fileDocumentRequired = null;
        let eFileDocumentoRequired = undefined;
        for (const key in eRequirements) {
            fileDocumentRequired = eRequirements[key].pond.getFile();
            // console.log('Archivo', fileDocumentRequired);
            // console.log('requer', eRequirements);
            let file = '';
            if(fileDocumentRequired == null && eRequirements[key].required){
                // console.log('Ingreso en requerido');
                addNotification({
                    msg: `El archivo del campo ${eRequirements[key].display} es obligatorio.`,
                    type: 'error',
                    target: 'newNotificationToast'
                });
                return;
            }
            if(fileDocumentRequired != null){
                // console.log('Con Archivo');
                loading.setLoading(false, 'Cargando, espere por favor...');
                //return;
                if (fileDocumentRequired.length == 0 ) {
                    // console.log('Con Archivo igual a cero', fileDocumentRequired);
                    addNotification({
                        msg: 'Debe subir un archivo',
                        type: 'error',
                        target: 'newNotificationToast'
                    });
                    loading.setLoading(false, 'Cargando, espere por favor...');
                    return;
                }

                if (fileDocumentRequired.length > 1 && eRequirements[key].required) {
                    // console.log('Con Archivo mayor a cero', fileDocumentRequired);
                    addNotification({
                        msg: 'Archivo de documento debe ser único',
                        type: 'error',
                        target: 'newNotificationToast'
                    });
                    loading.setLoading(false, 'Cargando, espere por favor...');
                    return;
                }
                // console.log(eRequirements[key].pond && fileDocumentRequired.length > 0)
                if (eRequirements[key].pond && fileDocumentRequired.length > 0) {
                    fileDocumentRequired = pondDocumento.getFiles()[0];
                }
                // console.log(fileDocumentRequired)
                file = fileDocumentRequired.file;
                // console.log(file)
            }
            formData.append(`file_requirement_${eRequirements[key].id}`, file);
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
                                            
                //loadInitial()
                actionLoad('cleanFormularioService', eService.id);
                // alert(res.data.urlservice);
                if (res.data.urlservice != null && res.data.urlservice != ''){
                    window.open(res.data.urlservice, '_blank');
                }
                loading.setLoading(false, 'Cargando, espere por favor...');
                goto('/alu_solicitudbalcon/missolicitudes_new');
                // location.reload();
            }
        }
        //addNotification({ msg: 'entro', type: 'error', target: 'newNotificationToast' });
    };

</script>

<div class="formulario-solicitud mt-5">
    {#if eService}    
    <div class="headtitle mb-lg-0 m-0">
        <h3 class="mx-2 m-0 p-0">{eService.servicio.nombre_minus}</h3>        
    </div>
    <form id="frmRequestService" on:submit|preventDefault={saveRequestServicess}>
        <div class="my-2">
            <div class="col-md-12">
                <label for="eRequestServiceObservation" class="form-label fw-bold mx-3 mt-2">                
                    Descripción*:
                </label>
                <textarea
                    rows="5"
                    cols="100"                   
                    class="form-control"
                    id="eRequestServiceObservation"
                    bind:value={eRequestServiceObservation}
                />
            </div>

            {#if eService.proceso.subesolicitud}
                <div class="col-md-12">
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
                    <p class="fst-italic mx-3 mt-2">Recuerda que el archivo debe ser formato PDF y un peso max. 4 Mb</p>
                </div>
            {/if}
            {#if eService.requisitos.length > 0 }
                <hr>
                <label for="ePersonaFileDocumentoRequisitos" class="form-label fw-bold mx-3">                        
                    Requisitos:
                </label>
                <div class="col-md-12 mb-3">                    
                    {#each eService.requisitos as eDetRequisito}                                
                        <div class="col-md-12 mb-3">
                            <label for="eRequestServiceDocument{eDetRequisito.id}" class="form-label fw-bold mx-3 mt-2">
                                {eDetRequisito.requisito.descripcion_minus}
                                {#if eDetRequisito.obligatorio}
                                    *
                                {/if}:
                            </label>
                            <FilePond
                                    class="pb-0 mb-0"
                                    id="eRequestServiceDocument{eDetRequisito.id}"
                                    bind:this={eRequirements[`requirement_${eDetRequisito.id}`].pond}
                                    {nameDocumento}
                                    name="{eRequirements[`requirement_${eDetRequisito.id}`].name}"
                                    labelIdle={['<span class="filepond--label"><i class="bi bi-file-earmark-arrow-up" style="font-size: 150%;"></i> Arrastre y suelte el archivo o haga clic aquí.</span>']}
                                    allowMultiple={true}
                                    oninit={eRequirements[`requirement_${eDetRequisito.id}`].handleInit}
                                    onaddfile={eRequirements[`requirement_${eDetRequisito.id}`].handleAddFile}
                                    credits=""
                                    acceptedFileTypes={['application/pdf']}
                                    labelInvalidField="El campo contiene archivos no válidos"
                                    maxFiles="1"
                                    maxParallelUploads="1"
                            />  
                            <p class="fst-italic mx-3 mt-2">Recuerda que el archivo debe ser formato PDF y un peso max. 4 Mb</p>                                  
                        </div>
                    {/each}                    
                </div>
            {/if}

            <div class="text-muted mb-6">
                <br>
                <div class="d-grid gap-2 d-md-flex justify-content-md-center">                    
                    <a class="btn btn-danger px-5" on:click={() => actionLoad('closeFormularioService', eService.id)}> Cerrar</a>
                    <button type="submit" class="btn enviar-btn px-5">Enviar</button>
                </div>
            </div>
        </div>
    </form>
    {/if}
</div>
<!-- Estilos -->
<style>
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
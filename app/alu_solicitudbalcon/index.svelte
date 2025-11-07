<script context="module" lang="ts">
    import type { Load } from '@sveltejs/kit';
    export const load: Load = async ({ fetch }) => {
        let eCategorias = [];
        let eSolicitudes = [];
        let eListaSolicitudes = [];
        let banPresi = false;
        let cantSolicitudesSinResponderEncuesta: 0;
        let mensajeResponderEncuesta: "";
        const ds = browserGet('dataSession');
        //console.log(ds);
        if (ds != null || ds != undefined) {
            loading.setLoading(true, 'Cargando, espere por favor...');
            const [res, errors] = await apiGET(fetch, 'alumno/balcon_servicios', {});
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
                    eCategorias = res.data['eCategorias'];
                    banPresi = res.data['ban']
                    eSolicitudes = res.data['eBalconyRequests'];
                    eListaSolicitudes = res.data['eListaSolicitudes'];
                    cantSolicitudesSinResponderEncuesta = res.data['cantSolicitudesSinResponderEncuesta'];
                    mensajeResponderEncuesta = res.data['mensajeResponderEncuesta'];
                }
            }
        }

        return {
            props: {
                eCategorias,
                banPresi,
                eSolicitudes,
                eListaSolicitudes,
                cantSolicitudesSinResponderEncuesta,
                mensajeResponderEncuesta
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
    import { createEventDispatcher, onDestroy } from 'svelte';
    import CarruselInfo from './_carruselinfo.svelte';
    import Menu from './_menu.svelte';
    import Solicitud from './_solicitudesinfo.svelte';
    import FomularioSolicitud from './_formulario.svelte';
    const dispatch = createEventDispatcher();
    import { goto } from '$app/navigation';
    import { navigating } from '$app/stores';
    import { addNotification } from '$lib/store/notificationStore';
    import { Modal, ModalBody, ModalHeader } from 'sveltestrap';
    import {FilePondFile} from "filepond";

    let mOpenModalGenerico = false;
    let mOpenConfirmarImportarNotasIngles = false;
    let modalTitle = '';
    const mToggleModalGenerico = () => (mOpenModalGenerico = !mOpenModalGenerico);
    (mOpenConfirmarImportarNotasIngles = !mOpenConfirmarImportarNotasIngles);

    let mSizeRequestService = 'lg';
    let mOpenRequestService = false;
    let service_id = '';
    let eRequestServiceObservation = '';
    let textService = '';
    let eService = {};
    let eRequirements = {};
    const mToggleRequestService = () => (mOpenRequestService = !mOpenRequestService );

    let itemsBreadCrumb = [{ text: 'Balcón de servicios', active: true, href: undefined }];
    let backBreadCrumb = { href: '/', text: 'Atrás' };
    $: loading.setNavigate(!!$navigating);
    $: loading.setLoading(!!$navigating, 'Cargando, espere por favor...');
    let pondDocumento;
    let nameDocumento = 'fileDocumento';
    let pondUprequest;
    let nameUprequest = 'fileUprequest';
    export let cantSolicitudesSinResponderEncuesta;
    export let mensajeResponderEncuesta;
    onMount(async () => {
        registerPlugin(FilePondPluginFileValidateType);
        if (cantSolicitudesSinResponderEncuesta > 0) {
            addNotification({
                msg: `${mensajeResponderEncuesta}`,
                type: 'warning',
                target: 'newNotificationToast',
                duration: 15000,
                pausable: true,
                intro: { y: 192 }
            });
        }
    });
    const loadAjax = async (data, url, method = undefined) =>
        new Promise(async (resolve, reject) => {
            if (method === undefined) {
                const [res, errors] = await apiPOST(fetch, url, data);
                //console.log(errorsCertificates);
                if (errors.length > 0) {
                    reject({
                        error: true,
                        message: errors[0].error
                    });
                } else {
                    resolve({
                        error: false,
                        value: res
                    });
                }
            } else {
                const [res, errors] = await apiGET(fetch, url, data);
                //console.log(errorsCertificates);
                if (errors.length > 0) {
                    reject({
                        error: true,
                        message: errors[0].error
                    });
                } else {
                    resolve({
                        error: false,
                        value: res
                    });
                }
            }
        });
    export let eCategorias;
    export let banPresi;
    export let eSolicitudes;
    export let eListaSolicitudes;

   
    let eInformationsServices  = [];
    
    const actionRun = async (event) => {		
        const detail = event.detail;
		const action = detail.action;
		const data = detail.data;
        console.log(action);
		if (action == 'selectItem') {            
            loading.setLoading(true, 'Cargando, espere por favor...');                           
            LoadProcessInformationsServices(data.item);
            //    
        }
        // if(action =='selectCarrusel'){
        //     console.log('Evento capturado en el padre:', data);
        // }
        if(action =='openRequestService'){
            loading.setLoading(true, 'Cargando, espere por favor...');  
            OpenRequestService(data.item);
        }
        if(action =='closeFormularioService'){
            CloseRequestService();            
            loading.setLoading(true, 'Cargando, espere por favor...');            
        }
        if(action =='cleanFormularioService'){
            limpiarcampos();    
            showFormularioSolicitud = false;        
            loading.setLoading(true, 'Cargando, espere por favor...');            
        }
        loading.setLoading(false, 'Cargando, espere por favor...');
    };

            

    const LoadProcessInformationsServices = async (id) => {
        loading.setLoading(true, 'Cargando, espere por favor...');
        const [res, errors] = await apiPOST(fetch, 'alumno/balcon_servicios', {
            action: 'getInformationsServices',
            id: id
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
                //console.log(res.data);
                eInformationsServices = res.data.eInformationsServices
                console.log(eInformationsServices);
                CloseRequestService();
            }
        }
    };
    
    
    
    let showFormularioSolicitud = false;    

    
    const OpenRequestService = (eServicetemp) =>{
        loading.setLoading(false, 'Cargando, espere por favor...');
        limpiarcampos();
        showFormularioSolicitud = true;
        
        
        
        // mSizeRequestService = 'lg';
        // mOpenRequestService = true;
        textService = eServicetemp.display;
        LoadServicesRequirements(eServicetemp);
    }
    const LoadServicesRequirements = (eServiceCurrent) => {
        eService = eServiceCurrent;
        console.log(eService);
        service_id = eServiceCurrent.id;
        if (Object.keys(eServiceCurrent).length !== 0){
            for (const requ of eServiceCurrent.requisitos ) {
                eRequirements[`requirement_${requ.id}`]={
                    id:requ.id,
                    name:`fileDocumento${requ.id}`,
                    display:requ.requisito.descripcion,
                    pond:null,
                    required:requ.obligatorio,
                    handleInit : () => {
                        console.log(`FilePond has initialised${requ.id}`);
                    },
                    handleAddFile : (err, fileItem) => {
                        //console.log(this.pond.getFiles());
                        console.log(this, `A file has been added${requ.id}`, fileItem);
                    }
                }
            }
        }
    }

    const CloseRequestService = () =>{
        showFormularioSolicitud = false;
        mOpenRequestService = false;
    }
    const handleInit = () => {
        console.log('FilePond has initialised');
    };

    const handleAddFile = (err, fileItem) => {
        //console.log(pondDocumento.getFiles());
        //console.log('A file has been added', fileItem);
    };
    const limpiarcampos = () => {
        service_id = '';
        eRequestServiceObservation = '';
        eService = {};
        eRequirements = {};
    };
    // const saveRequestService = async () => {
    //     const $frmRequestService = document.querySelector('#frmRequestService');
    //     const formData = new FormData($frmRequestService);

    //     formData.append('action', 'addRequestService');
    //     formData.append('service_id', service_id);
    //     formData.append('tipo', '2');

    //     if (!eRequestServiceObservation) {
    //         addNotification({
    //             msg: 'Favor complete el campo de descripción',
    //             type: 'error',
    //             target: 'newNotificationToast'
    //         });
    //         loading.setLoading(false, 'Cargando, espere por favor...');
    //         return;
    //     } else {
    //         formData.append('descripcion', eRequestServiceObservation);
    //     }
    //     if(eService.proceso.subesolicitud){
    //         let fileDocumento = pondDocumento.getFiles();
    //         if (fileDocumento.length == 0) {
    //             addNotification({
    //                 msg: 'Debe subir un archivo',
    //                 type: 'error',
    //                 target: 'newNotificationToast'
    //             });
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             return;
    //         }
    //         if (fileDocumento.length > 1) {
    //             addNotification({
    //                 msg: 'Archivo de documento debe ser único',
    //                 type: 'error',
    //                 target: 'newNotificationToast'
    //             });
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             return;
    //         }
    //         let eFileDocumento = undefined;
    //         if (pondDocumento && pondDocumento.getFiles().length > 0) {
    //             eFileDocumento = pondDocumento.getFiles()[0];
    //         }
    //         formData.append('file_uprequest', eFileDocumento.file);
    //     }

    //     let fileDocumentRequired = null;
    //     let eFileDocumentoRequired = undefined;
    //     for (const key in eRequirements) {
    //         fileDocumentRequired = eRequirements[key].pond.getFile();
    //         console.log('Archivo', fileDocumentRequired);
    //         console.log('requer', eRequirements);
    //         let file = '';
    //         if(fileDocumentRequired == null && eRequirements[key].required){
    //             console.log('Ingreso en requerido');
    //             addNotification({
    //                 msg: `El archivo del campo ${eRequirements[key].display} es obligatorio.`,
    //                 type: 'error',
    //                 target: 'newNotificationToast'
    //             });
    //             return;
    //         }
    //         if(fileDocumentRequired != null){
    //             console.log('Con Archivo');
    //             loading.setLoading(false, 'Cargando, espere por favor...');
    //             //return;
    //             if (fileDocumentRequired.length == 0 ) {
    //                 console.log('Con Archivo igual a cero', fileDocumentRequired);
    //                 addNotification({
    //                     msg: 'Debe subir un archivo',
    //                     type: 'error',
    //                     target: 'newNotificationToast'
    //                 });
    //                 loading.setLoading(false, 'Cargando, espere por favor...');
    //                 return;
    //             }

    //             if (fileDocumentRequired.length > 1 && eRequirements[key].required) {
    //                 console.log('Con Archivo mayor a cero', fileDocumentRequired);
    //                 addNotification({
    //                     msg: 'Archivo de documento debe ser único',
    //                     type: 'error',
    //                     target: 'newNotificationToast'
    //                 });
    //                 loading.setLoading(false, 'Cargando, espere por favor...');
    //                 return;
    //             }
    //             console.log(eRequirements[key].pond && fileDocumentRequired.length > 0)
    //             if (eRequirements[key].pond && fileDocumentRequired.length > 0) {
    //                 fileDocumentRequired = pondDocumento.getFiles()[0];
    //             }
    //             console.log(fileDocumentRequired)
    //             file = fileDocumentRequired.file;
    //             console.log(file)
    //         }
    //         formData.append(`file_requirement_${eRequirements[key].id}`, file);
    //     }

    //     console.log(eRequirements)
    //     console.log(eService)
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
    //             //loadInitial()
    //             limpiarcampos()
    //             // alert(res.data.urlservice);
    //             if (res.data.urlservice != null && res.data.urlservice != ''){
    //                 window.open(res.data.urlservice, '_blank');
    //             }
    //         }
    //     }
    //     //addNotification({ msg: 'entro', type: 'error', target: 'newNotificationToast' });
    // };


</script>
<!--<div class="col-lg-12 col-md-12 col-12">-->
<!--    <div class="pb-2 mb-4 d-lg-flex justify-content-between align-items-center">-->
<!--        <div class="mb-3 mb-lg-0">-->
<!--            <h4 class="mb-0" style="color: #012E46;margin-left: 5px;">¡<b>Hola Angel Torres</b>, bienvenido al Sistema de Gestión Académica!</h4>-->
<!--        </div>-->
<!--        <div class="d-flex">-->
<!--            <div class="input-group me-3">-->
<!--                <input class="form-control" id="idbuscador" type="text" placeholder=" Buscar..." style="font-family:Arial, FontAwesome">-->
<!--            </div>-->
<!--        </div>-->
<!--    </div>-->
<!--</div>-->
<svelte:head>
	<title>Balcón de servicios </title>
</svelte:head>
<BreadCrumb title="Balcón de servicios" subtitle="Para agilizar tu solicitud, selecciona la categoría y subcategoría correspondientes." items={itemsBreadCrumb} back={backBreadCrumb} />
<div class="container-fluid">
    <div class="row">
        <div class="col-lg-3 col-md-3 col-12 ">
            <Menu on:actionRun={actionRun} {eCategorias} />
        </div>
        <div class="col-lg-6 col-md-6 col-12 mx-0">
            {#if showFormularioSolicitud}
                <FomularioSolicitud on:actionRun={actionRun} {eService} {eRequirements} {eListaSolicitudes}/>
            {:else}
                <CarruselInfo on:actionRun={actionRun} {eInformationsServices} />                           
            {/if}
        </div>
        <div class="col-lg-3 col-md-3 col-12 ">
            <Solicitud {eSolicitudes} />                        
        </div>
    </div>
</div>








<!-- <a href="/alu_solicitudbalcon/missolicitudes" class="btn btn-primary mb-4"> MIS SOLICITUDES</a>
<div class="row">
    <div class="col-4 col-md-4 col-sm-12">
        <div class="bg-white">
            <table class="table table-bordered mt-5 p-0 m-0">
                <tbody>
                {#each eCategorias as eCategoria }
                    <tr>
                        <td style="width: 30px; text-align: center;">
                            <a class="btn-default"
                                    data-bs-toggle="collapse" aria-expanded="false" aria-controls="collapseExample"
                                    href="#balcon-item{eCategoria.id}">
                                <img src="{variables.BASE_API_STATIC}/images/iconos/add-folder.png" alt="" width="15px" height="15px" id="img_1">
                            </a>
                        </td>
                        <td style="vertical-align: middle;"  class="respon">
                            {eCategoria.display}
                        </td>
                    </tr>
                    <tr>
                        <td colspan="2" style="padding-top: 0; padding-bottom: 0; !important;padding-left:60px;  padding-right: 0px;">
                            <div class="collapse" id="balcon-item{eCategoria.id}" style="color:#08c;"s>
                                <ul class="list-group">
                                    {#each eCategoria.procesos as eProceso }
                                        {#if eProceso.descripcion != 'PRESIDENTE DE CURSO'}
                                            <li class="list-group-item" style="font-size: 11px;">
                                                
                                                    <i class="fe fe-tag"></i>
                                                        <a href="javascript:;" on:click={() => LoadProcessInformationsServices(eProceso.id)}>{eProceso.descripcion}
                                                    </a>
                                                
                                            </li>
                                        {:else if banPresi}
                                            <li class="list-group-item" style="font-size: 11px;">
                                                    
                                                <i class="fe fe-tag"></i>
                                                    <a href="javascript:;" on:click={() => LoadProcessInformationsServices(eProceso.id)}>{eProceso.descripcion}
                                                </a>
                                            
                                            </li>
                                        {/if}
                                    {/each}
                                </ul>
                            </div>
                        </td>
                    </tr>
                {/each}
                </tbody>
            </table>
        </div>
    </div>
    <div class="col-8 col-md-8 col-sm-12">
        <div class="bg-white">
            {#if eInformationsServices.length > 0}
                <ul class="result-list">
                    {#each eInformationsServices as eInformationService,index}
                        <li class="list-group-item">
                            <div class="result-info">
                                <div style="float: right">
                                    <a data-fancybox="image"
								class="btn tl"
								title="Ver imagen"
								href="{eInformationService.archivomostrar}">
								<img style="margin-top: 2px; width: 25px" src="{variables.BASE_API_STATIC}/images/image.png" width="30" height="30"/></a>
                                    {#if eInformationService.archivomostrar }
                                        {#if eInformationService.typefilemostrar != '.pdf' }
                                            <a data-fancybox="image"
                                               class="btn tl"
                                               title="VER ARCHIVO PARA MOSTRAR"
                                               href="{eInformationService.archivomostrar}">
                                                <img style="margin-top: 2px; width: 25px" src="{variables.BASE_API_STATIC}/images/image.png" width="30" height="30"/></a>
                                        {:else}
                                            <a data-fancybox data-type="iframe"
                                               class="btn tl"
                                               title="VER ARCHIVO PARA MOSTRAR"
                                               href="{eInformationService.archivomostrar}">
                                                <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/pdf.png" width="30" height="30"/></a>
                                        {/if}
                                    {/if}
                                    {#if eInformationService.archivodescargar }
                                        {#if eInformationService.typefiledescargar != '.pdf' }
                                            <a data-fancybox="image"
                                               class="btn tl"
                                               title="VER ARCHIVO PARA DESCARGAR"
                                               href="{eInformationService.archivodescargar}">
                                                <img style="margin-top: 2px; width: 25px" src="{variables.BASE_API_STATIC}/images/image.png" width="30" height="30"/></a>
                                        {:else}
                                            <a data-fancybox data-type="iframe"
                                               class="btn tl"
                                               title="VER ARCHIVO PARA DESCARGAR"
                                               href="{eInformationService.archivodescargar}">
                                                <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/pdf.png" width="30" height="30"/></a>
                                        {/if}
                                    {/if}
                                    {#if eInformationService.servicio.opcsistema}
                                        <a class="btn btn-primary tl "
                                           href="{eInformationService.servicio.opcsistema.modulo.api?'':variables.BASE_API}/{ eInformationService.servicio.opcsistema.modulo.url }"
                                           style="padding-top: 5px; padding-bottom: 5px"
                                           title="Ir {eInformationService.servicio.display}">
                                            <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/solicitar_balcon4.png" width="30"
                                                 height="30"/>
                                            Solicitar
                                        </a>
                                    {:else}
                                        <a class="btn btn-primary tl " on:click={() => OpenRequestService(eInformationService.servicio)}
                                           href="javascript:void(0);" style="padding-top: 5px; padding-bottom: 5px"
                                           data-original-title="SOLICITAR PROYECTOS DE INVESTIGACIÓN">
                                            <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/solicitar_balcon4.png" width="30" height="30">
                                            Solicitar
                                        </a>
                                    {/if}
                                </div>
                                <h4 class="title">
                                    <a href="javascript:;">{index+1}. {eInformationService.servicio.display} </a>
                                </h4>
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-clock" viewBox="0 0 16 16">
                                    <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/>
                                    <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/>
                                </svg> Tiempo de atención de <b>{eInformationService.servicio.tiempominimo }</b> a
                                <b>{eInformationService.servicio.tiempomaximo}</b> días.
                                <br>
                                {eInformationService.descripcion}<br>
                                {#if eInformationService.informacion}
                                <button class="btn btn-link" type="button"
                                        data-bs-toggle="collapse" style="text-align: right"
                                        data-bs-target="#collapseOne{eInformationService.id}" aria-expanded="true"
                                        aria-controls="collapseOne{eInformationService.id}"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-plus-circle-fill" viewBox="0 0 16 16">
                                    <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM8.5 4.5a.5.5 0 0 0-1 0v3h-3a.5.5 0 0 0 0 1h3v3a.5.5 0 0 0 1 0v-3h3a.5.5 0 0 0 0-1h-3v-3z"/>
                                </svg> Ver más
                                </button>
                                {/if}
                                <hr>
                                <div id="collapseOne{eInformationService.id}" class="collapse">
                                    {@html eInformationService.informacion}
                                </div>

                            </div>
                        </li>
                    {/each}
                </ul>
            {:else}
                <div class="card" style="vertical-align: center">
                    <div class="card-body" style="vertical-align: center">
                        <p class="card-text alert alert-info" style="width: 100%;font-size: 14px;display: compact;">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" class="bi bi-shield-fill-exclamation" viewBox="0 0 16 16">
                                <path fill-rule="evenodd" d="M8 0c-.69 0-1.843.265-2.928.56-1.11.3-2.229.655-2.887.87a1.54 1.54 0 0 0-1.044 1.262c-.596 4.477.787 7.795 2.465 9.99a11.777 11.777 0 0 0 2.517 2.453c.386.273.744.482 1.048.625.28.132.581.24.829.24s.548-.108.829-.24a7.159 7.159 0 0 0 1.048-.625 11.775 11.775 0 0 0 2.517-2.453c1.678-2.195 3.061-5.513 2.465-9.99a1.541 1.541 0 0 0-1.044-1.263 62.467 62.467 0 0 0-2.887-.87C9.843.266 8.69 0 8 0zm-.55 8.502L7.1 4.995a.905.905 0 1 1 1.8 0l-.35 3.507a.552.552 0 0 1-1.1 0zM8.002 12a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"></path>
                            </svg>
                            <b>AVISO IMPORTANTE:</b>
                            Recuerda que posterior al registro y trámite de tu solicitud, podrás calificar la atención recibida
                            por parte del personal encargado en la opción mis solicitudes
                        </p>
                    </div>
                    <img class="card-img-top" src="{variables.BASE_API_STATIC}/images/undraw/Encuesta-UNEMI.jpg"  style="width:60%; margin-left: 20%;">
                </div>
            {/if}
        </div>
    </div>
</div> -->


<!--<div class="row-fluid mt-4" style="background: white">-->
<!--    <div class="col-lg-12 col-md-12 col-12">-->
<!--        <div class="containerMenu">-->
<!--            <div class="menuPanelCard">-->
<!--                {#each eCategorias as eCategoria }-->
<!--                    <div class="dropdown_main">-->
<!--                        <div data-nombre="aprobar capacitaciones" url="adm_aprobarcapdocente" class="carbon-example flex-wrapper action-menu-entry">-->
<!--                            <div class="row">-->
<!--                                <div class="col-auto">-->
<!--                                    <div class="avatar avatar-md avatar-indicators" style="padding: 2px">-->
<!--                                        <img alt="avatar"  src="{variables.BASE_API_STATIC}/images/iconssga/icon_aprobacion_capacitacion.svg">-->
<!--                                    </div>-->
<!--                                </div>-->
<!--                                <div class="col"  style="padding-right: 2px;display: flex; align-items: center;">-->
<!--                                    <h4 class="mb-0 h5">{eCategoria.display}</h4>-->
<!--                                </div>-->
<!--                                <div class="col-auto" style="padding:0px;text-align:center; background: #1C3247; border-bottom-right-radius: 6px;border-top-right-radius: 6px;width: 2.5rem;">-->
<!--                                    <a class="btn-icon btn btn-ghost btn-sm rounded-none" href="#collapseExample{eCategoria.id}" role="button"-->
<!--                                       data-bs-toggle="collapse" aria-expanded="false" aria-controls="collapseExample"-->
<!--                                       id="courseDropdown7">-->
<!--                                        <i class="bi bi-caret-down-fill" style="font-size: 20px; color: #FE9900 !important;" ></i>-->
<!--                                    </a>-->
<!--                                </div>-->
<!--                            </div>-->
<!--                        </div>-->
<!--                        <div class="collapse" id="collapseExample{eCategoria.id}"  style="background: #1D4983; border-radius:12px; text-align: center;">-->
<!--                            <ul class="list-group" style="display: flex;background: #F1F6FB;">-->
<!--                                {#each eCategoria.procesos as eProceso }-->
<!--                                    <li class="list-group-item" style="background: #F1F6FB;">-->
<!--                                        <a href="javascript:;" on:click={() => LoadProcessInformationsServices(eProceso.id)} style="color:#1C3247;">{eProceso.descripcion}</a>-->
<!--                                    </li>-->
<!--                                {/each}-->
<!--                            </ul>-->
<!--                        </div>-->
<!--                    </div>-->
<!--                {/each}-->
<!--&lt;!&ndash;                <div class="dropdown_main">&ndash;&gt;-->
<!--&lt;!&ndash;                    <div data-nombre="aprobar capacitaciones" url="adm_aprobarcapdocente" class="carbon-example flex-wrapper action-menu-entry">&ndash;&gt;-->
<!--&lt;!&ndash;                        <div class="row">&ndash;&gt;-->
<!--&lt;!&ndash;                            <div class="col-auto">&ndash;&gt;-->
<!--&lt;!&ndash;                                <div class="avatar avatar-md avatar-indicators" style="padding: 2px">&ndash;&gt;-->
<!--&lt;!&ndash;                                    <img alt="avatar"  src="{variables.BASE_API_STATIC}/images/iconssga/icon_aprobacion_capacitacion.svg">&ndash;&gt;-->
<!--&lt;!&ndash;                                </div>&ndash;&gt;-->
<!--&lt;!&ndash;                            </div>&ndash;&gt;-->
<!--&lt;!&ndash;                            <div class="col"  style="padding-right: 2px;display: flex; align-items: center;">&ndash;&gt;-->
<!--&lt;!&ndash;                                <h4 class="mb-0 h5">INVESTIGACIÓN</h4>&ndash;&gt;-->
<!--&lt;!&ndash;                            </div>&ndash;&gt;-->
<!--&lt;!&ndash;                            <div class="col-auto" style="padding:0px;text-align:center; background: #1C3247; border-bottom-right-radius: 6px;border-top-right-radius: 6px;width: 2.5rem;">&ndash;&gt;-->
<!--&lt;!&ndash;                                <a class="d-block link-dark text-decoration-none dropdown-toggle" href="#"&ndash;&gt;-->
<!--&lt;!&ndash;                                   id="id_button_example"&ndash;&gt;-->
<!--&lt;!&ndash;                                   data-bs-toggle="dropdown"&ndash;&gt;-->
<!--&lt;!&ndash;                                   data-bs-customClass="beautifier"&ndash;&gt;-->
<!--&lt;!&ndash;                                   aria-expanded="false">&ndash;&gt;-->
<!--&lt;!&ndash;                                    <i class="bi bi-caret-down-fill" style="font-size: 20px; color: #FE9900 !important;" ></i>&ndash;&gt;-->
<!--&lt;!&ndash;                                </a>&ndash;&gt;-->
<!--&lt;!&ndash;                                <ul class="dropdown-menu text-small" style="inset: 0rem auto auto -15.9rem !important; background: #F1F6FB;">&ndash;&gt;-->
<!--&lt;!&ndash;                                    <li><a class="dropdown-item" href="#">New project...</a></li>&ndash;&gt;-->
<!--&lt;!&ndash;                                    <li><a class="dropdown-item" href="#">Settings</a></li>&ndash;&gt;-->
<!--&lt;!&ndash;                                    <li><a class="dropdown-item" href="#">Profile</a></li>&ndash;&gt;-->
<!--&lt;!&ndash;                                    <li><hr class="dropdown-divider"></li>&ndash;&gt;-->
<!--&lt;!&ndash;                                    <li><a class="dropdown-item" href="#">Sign out</a></li>&ndash;&gt;-->
<!--&lt;!&ndash;                                </ul>&ndash;&gt;-->
<!--&lt;!&ndash;                            </div>&ndash;&gt;-->
<!--&lt;!&ndash;                        </div>&ndash;&gt;-->
<!--&lt;!&ndash;                    </div>&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                    <div class="d-flex align-items-center">&ndash;&gt;&ndash;&gt;-->

<!--&lt;!&ndash;&lt;!&ndash;                        <div class="flex-shrink-0 dropdown">&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                            <a href="#" class="d-block link-dark text-decoration-none dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <img src="https://github.com/mdo.png" alt="mdo" width="32" height="32" class="rounded-circle">&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                            </a>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                            <ul class="dropdown-menu text-small shadow" style="">&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <li><a class="dropdown-item" href="#">New project...</a></li>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <li><a class="dropdown-item" href="#">Settings</a></li>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <li><a class="dropdown-item" href="#">Profile</a></li>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <li><hr class="dropdown-divider"></li>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                                <li><a class="dropdown-item" href="#">Sign out</a></li>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                            </ul>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                        </div>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;&lt;!&ndash;                    </div>&ndash;&gt;&ndash;&gt;-->
<!--&lt;!&ndash;                </div>&ndash;&gt;-->
<!--            </div>-->
<!--        </div>-->
<!--    </div>-->
<!--    <div class="row-fluid p-3">-->
<!--        <div class="col-lg-12 col-md-12 col-12" style="min-height: 500px;">-->
<!--            <ul class="result-list">-->
<!--                {#each eInformationsServices as eInformationService,index}-->
<!--                    <li class="list-group-item">-->
<!--                        <div class="result-info">-->
<!--                            <div style="float: right">-->
<!--                                {#if eInformationService.archivomostrar }-->
<!--                                    {#if eInformationService.typefilemostrar != '.pdf' }-->
<!--                                        <a data-fancybox="image"-->
<!--                                           class="btn tl"-->
<!--                                           title="VER ARCHIVO PARA MOSTRAR"-->
<!--                                           href="{eInformationService.archivomostrar}">-->
<!--                                            <img style="margin-top: 2px; width: 25px" src="{variables.BASE_API_STATIC}/images/image.png" width="30" height="30"/></a>-->
<!--                                    {:else}-->
<!--                                        <a data-fancybox data-type="iframe"-->
<!--                                           class="btn tl"-->
<!--                                           title="VER ARCHIVO PARA MOSTRAR"-->
<!--                                           href="{eInformationService.archivomostrar}">-->
<!--                                            <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/pdf.png" width="30" height="30"/></a>-->
<!--                                    {/if}-->
<!--                                {/if}-->
<!--                                {#if eInformationService.archivodescargar }-->
<!--                                    {#if eInformationService.typefiledescargar != '.pdf' }-->
<!--                                        <a data-fancybox="image"-->
<!--                                           class="btn tl"-->
<!--                                           title="VER ARCHIVO PARA DESCARGAR"-->
<!--                                           href="{eInformationService.archivodescargar}">-->
<!--                                            <img style="margin-top: 2px; width: 25px" src="{variables.BASE_API_STATIC}/images/image.png" width="30" height="30"/></a>-->
<!--                                    {:else}-->
<!--                                        <a data-fancybox data-type="iframe"-->
<!--                                           class="btn tl"-->
<!--                                           title="VER ARCHIVO PARA DESCARGAR"-->
<!--                                           href="{eInformationService.archivodescargar}">-->
<!--                                            <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/pdf.png" width="30" height="30"/></a>-->
<!--                                    {/if}-->
<!--                                {/if}-->
<!--                                {#if eInformationService.servicio.opcsistema}-->
<!--                                    <a class="btn btn-primary tl "-->
<!--                                       href="{variables.BASE_API}/{ eInformationService.servicio.opcsistema.modulo.url }"-->
<!--                                       style="padding-top: 5px; padding-bottom: 5px"-->
<!--                                       title="Ir {eInformationService.servicio.display}">-->
<!--                                        <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/solicitar_balcon4.png" width="30"-->
<!--                                             height="30"/>-->
<!--                                        Solicitar-->
<!--                                    </a>-->
<!--                                {:else}-->
<!--                                    <a class="btn btn-primary tl " on:click={() => OpenRequestService(eInformationService.servicio)}-->
<!--                                       href="javascript:void(0);" style="padding-top: 5px; padding-bottom: 5px"-->
<!--                                       data-original-title="SOLICITAR PROYECTOS DE INVESTIGACIÓN">-->
<!--                                        <img style="margin-top: 2px;" src="{variables.BASE_API_STATIC}/images/iconos/solicitar_balcon4.png" width="30" height="30">-->
<!--                                        Solicitar-->
<!--                                    </a>-->
<!--                                {/if}-->
<!--                            </div>-->
<!--                            <h4 class="title">-->
<!--                                <a href="javascript:;">{index+1}. {eInformationService.servicio.display} </a>-->
<!--                            </h4>-->
<!--                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-clock" viewBox="0 0 16 16">-->
<!--                                <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/>-->
<!--                                <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/>-->
<!--                            </svg> Tiempo de atención de <b>{eInformationService.servicio.tiempominimo }</b> a-->
<!--                            <b>{eInformationService.servicio.tiempomaximo}</b> días.-->
<!--                            <br>-->
<!--                            {eInformationService.descripcion}<br>-->
<!--                            <button class="btn btn-link" type="button"-->
<!--                                    data-bs-toggle="collapse" style="text-align: right"-->
<!--                                    data-bs-target="#collapseOne{eInformationService.id}" aria-expanded="true"-->
<!--                                    aria-controls="collapseOne{eInformationService.id}"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-plus-circle-fill" viewBox="0 0 16 16">-->
<!--                                <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM8.5 4.5a.5.5 0 0 0-1 0v3h-3a.5.5 0 0 0 0 1h3v3a.5.5 0 0 0 1 0v-3h3a.5.5 0 0 0 0-1h-3v-3z"/>-->
<!--                            </svg> Ver más-->
<!--                            </button>-->
<!--                            <hr>-->
<!--                            <div id="collapseOne{eInformationService.id}" class="collapse">-->
<!--                                {@html eInformationService.informacion}-->
<!--                            </div>-->

<!--                        </div>-->
<!--                    </li>-->
<!--                {/each}-->
<!--            </ul>-->
<!--        </div>-->
<!--    </div>-->
<!--</div>-->

    <Modal isOpen={mOpenRequestService}
           toggle={mToggleRequestService}
           size={mSizeRequestService}
           class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-fullscreen-md-down"
           backdrop="static"
           fade={false}>

        <ModalHeader toggle={mToggleRequestService}>
            <h4><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-list-ul" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M5 11.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm0-4a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5zm-3 1a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0 4a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0 4a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/>
                </svg> SOLICITAR {textService}</h4>
        </ModalHeader>
        <ModalBody>
            {#if Object.keys(eService).length !== 0  }
            <form id="frmRequestService" on:submit|preventDefault={saveRequestService}>
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
                                id="eRequestServiceObservation"
                                bind:value={eRequestServiceObservation}/>
                    </div>
                    {#if eService.proceso.subesolicitud}
                        <div class="col-md-12">
                            <label for="ePersonaFileDocumento" class="form-label fw-bold"
                            ><i title="Campo obligatorio" class="bi bi-exclamation-circle-fill" style="color: red"></i> Archivo Solicitud:</label
                            >
                            <!--https://pqina.nl/filepond/docs/api/instance/properties/-->
                            <FilePond
                                    class="pb-0 mb-0"
                                    id="ePersonaFileDocumento"
                                    bind:this={pondDocumento}
                                    {nameDocumento}
                                    name="fileDocumento"
                                    labelIdle={['<span class="filepond--label-action">Subir archivo</span>']}
                                    allowMultiple={false}
                                    oninit={handleInit}
                                    onaddfile={handleAddFile}
                                    credits=""
                                    accepted-file-types={['application/pdf']}
                                    labelInvalidField="El campo contiene archivos no válidos"
                                    maxFiles="1"
                                    maxParallelUploads="1"
                                    accept=".pdf"
                            />
                            <small class="text-warning">Tamaño máximo permitido 15Mb, en formato pdf</small>
                        </div>
                    {/if}
                    {#if eService.requisitos}
                        <div class="col-md-12 mt-3">
                            <table class="table table-bordered">
<!--                                <thead>-->
<!--                                    <tr>-->
<!--                                        <th> Requisito</th>-->
<!--                                        <th> Archivos</th>-->
<!--                                    </tr>-->
<!--                                </thead>-->
                                <tbody>
                                    {#each eService.requisitos as eDetRequisito}
                                        <tr>
                                            <td style="width: 100%;">
                                                <label for="eRequestServiceDocument{eDetRequisito.id}" class="form-label fw-bold">
                                                    {#if eDetRequisito.obligatorio}
                                                        <i title="Campo obligatorio" class="bi bi-exclamation-circle-fill" style="color: red"></i>
                                                    {/if}    {eDetRequisito.requisito.descripcion}:
                                                </label>
                                                <FilePond
                                                        class="pb-0 mb-0"
                                                        id="eRequestServiceDocument{eDetRequisito.id}"
                                                        bind:this={eRequirements[`requirement_${eDetRequisito.id}`].pond}
                                                        {nameDocumento}
                                                        name="{eRequirements[`requirement_${eDetRequisito.id}`].name}"
                                                        labelIdle={['<span class="filepond--label-action">Subir archivo</span>']}
                                                        allowMultiple={true}
                                                        oninit={eRequirements[`requirement_${eDetRequisito.id}`].handleInit}
                                                        onaddfile={eRequirements[`requirement_${eDetRequisito.id}`].handleAddFile}
                                                        credits=""
                                                        acceptedFileTypes={['application/pdf']}
                                                        labelInvalidField="El campo contiene archivos no válidos"
                                                        maxFiles="1"
                                                        maxParallelUploads="1"
                                                />
                                            </td>
                                        </tr>
                                {/each}
                                </tbody>
                            </table>
                        </div>
                    {/if}
                    <div class="card-footer text-muted">
                        <div class="d-grid gap-2 d-md-flex justify-content-md-end">
                            <!--<button class="btn btn-primary me-md-2" type="button">Button</button>-->
                            <button type="submit" class="btn btn-info">Guardar</button>
                            <a color="danger" class="btn btn-danger" on:click={() => CloseRequestService()}>Cerrar</a>

                        </div>
                    </div>
                </div>
            </form>
            {/if}
        </ModalBody>
    </Modal>

<style>
    .dropdown_menu{
        border: 1px  solid #c1d7e3;
        width: 20rem;
    }
    .dropdown_menu.show{
        display: block;
    }

    div.collapse >a{
        display: block;
    }
    .dropdown_button{
        background: #0a53be;
    }

    .containerMenu > * {
        grid-column: col-start / span 12;
    }
    .menuPanelCard .dropdown_main{
        padding-left: 10px !important;
        padding-right: 10px !important;
    }
    .menuPanelCard {
        list-style: none;
        margin: 0em !important;
        padding: 0px !important;
        /*padding-left: 10px !important;*/
        padding-right: 10px !important;
        display: grid;
        grid-gap: 6px;
        grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
        /* grid-template-columns: 1fr 1fr 1fr 1fr 1fr; */
        font-size: 12px;
    }
    .menuPanelCard .carbon-example {
        border: 1px solid #e3e3e3;
    }
    .carbon-example {
        /*padding: 8px;*/
        background-color: #fff;
        /* width: 295px; */
        /* width: 215px; */
        /*height: 90px;*/
        box-sizing: border-box;
        border-radius: 6px;
        -webkit-box-align: start;
        -ms-flex-align: start;
        -webkit-align-items: flex-start;
        -moz-align-items: flex-start;
        align-items: flex-start;
        position: relative;
        z-index: 5;
        /* box-shadow: 0 2px 20px 0 rgb(0 0 0 / 10%); */
        margin-top: 6px;
        border: 1px solid #e3e3e3;
    }
    .carbon-example img {
        margin-right: 9px;
        border-right: 1.5px solid #e3e3e3;
        max-width: 125px;
        /*padding-right: 8px;*/
        /*width: 40px;*/
    }
    .carbon-example .inner-wrapper {
        text-align: left;
    }
    .avatar-md {
        height: 2.5rem;
        width: 2.5rem /*height: 28px;*/ /*width: 29px;*/;
    }

    .result-list {
        list-style-type: none;
        margin: 0;
        padding: 0;
        width: 100%
    }

    .result-list:after, .result-list:before {
        content: '';
        display: table;
        clear: both
    }

    .result-list > li {
        border: 1px solid #ddd;
        background: #fff;
        overflow: hidden;
        position: relative;
        display: -webkit-box;
        display: -ms-flexbox;
        display: flex;
        -webkit-flex-wrap: wrap;
        -ms-flex-wrap: wrap;
        flex-wrap: wrap;
    }

    .result-list > li:after, .result-list > li:before {
        content: '';
        display: table;
        clear: both
    }

    .result-list > li + li {
        margin-top: 10px
    }

    .result-list > li .result-image {
        width: 240px;
        padding: 0;
        overflow: hidden;
        background: #2d353c;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat
    }


    .result-list > li .result-image a {
        display: block
    }

    .result-list > li .result-image img {
        width: 100%
    }

    .result-list > li .result-image:focus, .result-list > li .result-image:hover {
        opacity: .8
    }

    .result-list > li .result-info {
        padding: 20px;
        position: relative;
        -webkit-box-flex: 1;
        -ms-flex: 1;
        flex: 1
    }

    .result-list > li .result-info .title {
        margin: 0 0 5px;
        font-size: 18px;
        line-height: 22px
    }


    .result-list > li .result-info .title a {
        color: #2d353c
    }

    .result-list > li .result-info .location {
        color: #6f8293;
    }

    .result-list > li .result-info .decs {
        margin-bottom: 20px;
        max-height: 32px;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: 16px
    }

    .result-list > li .result-info .btn-row {
        display: -webkit-box;
        display: -ms-flexbox;
        display: flex;
        -webkit-flex-wrap: wrap;
        -ms-flex-wrap: wrap;
        flex-wrap: wrap
    }

    .result-list > li .result-info .btn-row:after, .result-list > li .result-info .btn-row:before {
        content: '';
        display: table;
        clear: both
    }

    .result-list > li .result-info .btn-row a {
        color: #2d353c;
        background: #f2f3f4;
        font-size: 14px;
        line-height: 18px;
        padding: 8px 10px;
        -webkit-border-radius: 4px;
        border-radius: 4px
    }

    .result-list > li .result-info .btn-row a + a {
        margin-left: 5px
    }

    .result-list > li .result-info .btn-row a:focus, .result-list > li .result-info .btn-row a:hover {
        background: #d5dbe0
    }

    .result-list > li .result-price {
        width: 240px;
        font-size: 28px;
        text-align: center;
        background: #f2f3f4;
        color: #2d353c;
        padding: 20px;
        position: relative;
        display: -webkit-box;
        display: -ms-flexbox;
        display: flex;
        -webkit-box-orient: vertical;
        -webkit-box-direction: normal;
        -ms-flex-direction: column;
        flex-direction: column;
        -webkit-box-pack: center;
        -ms-flex-pack: center;
        justify-content: center;
        -ms-flex-align: center;
        align-items: center
    }


    .result-list > li .result-price small {
        display: block;
        font-size: 11px;
        font-weight: 600;
        color: #6f8293
    }

    .result-list > li .result-price .btn {
        margin-top: 30px
    }

    .row > [class^=col-].ui-sortable {
        min-height: 50px
    }

    @-webkit-keyframes rotation {
        from {
            -webkit-transform: rotate(0);
            -moz-transform: rotate(0);
            -ms-transform: rotate(0);
            -o-transform: rotate(0);
            transform: rotate(0)
        }
        to {
            -webkit-transform: rotate(359deg);
            -moz-transform: rotate(359deg);
            -ms-transform: rotate(359deg);
            -o-transform: rotate(359deg);
            transform: rotate(359deg)
        }
    }

    @-moz-keyframes rotation {
        from {
            -webkit-transform: rotate(0);
            -moz-transform: rotate(0);
            -ms-transform: rotate(0);
            -o-transform: rotate(0);
            transform: rotate(0)
        }
        to {
            -webkit-transform: rotate(359deg);
            -moz-transform: rotate(359deg);
            -ms-transform: rotate(359deg);
            -o-transform: rotate(359deg);
            transform: rotate(359deg)
        }
    }

    @-o-keyframes rotation {
        from {
            -webkit-transform: rotate(0);
            -moz-transform: rotate(0);
            -ms-transform: rotate(0);
            -o-transform: rotate(0);
            transform: rotate(0)
        }
        to {
            -webkit-transform: rotate(359deg);
            -moz-transform: rotate(359deg);
            -ms-transform: rotate(359deg);
            -o-transform: rotate(359deg);
            transform: rotate(359deg)
        }
    }

    @keyframes rotation {
        from {
            -webkit-transform: rotate(0);
            -moz-transform: rotate(0);
            -ms-transform: rotate(0);
            -o-transform: rotate(0);
            transform: rotate(0)
        }
        to {
            -webkit-transform: rotate(359deg);
            -moz-transform: rotate(359deg);
            -ms-transform: rotate(359deg);
            -o-transform: rotate(359deg);
            transform: rotate(359deg)
        }
    }

    .single_faq {
        margin-bottom: 15px;
        padding: 15px;
    }

    .faq_question::before {
        font-size: 20px;
        line-height: 35px;
    }

    .faq_question {
        padding: 8px 10px 8px 26px;
    }

    .faq_answer {
        margin-top: 0;
    }
</style>
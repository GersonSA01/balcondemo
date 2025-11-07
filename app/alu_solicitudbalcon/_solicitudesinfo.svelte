<script>
    import { Carousel, CarouselItem } from 'sveltestrap';

    // Inicializa los índices activos para cada carrusel
    let activeItemTramite = 0;
    let activeItemPendiente = 0;
    let activeItemAprobado = 0;
    let activeItemCorregir = 0;
    let activeItemRechazado = 0;
    let solicitudTitle = 'Estado de mis solicitudes';
    // La data que recibes, que incluye 'en_trámite' y 'pendiente'
    export let eSolicitudes;
    let existsSolicitudes = false;

    // Función para cambiar el ítem activo del carrusel
    const changeItem = (tipo, index) => {
        if (tipo === 'T') {
            activeItemTramite = index;
        }
        if (tipo === 'P') {
            activeItemPendiente = index;
        }
        if (tipo === 'A') {
            activeItemAprobado = index;
        }
        if (tipo === 'C') {
            activeItemCorregir = index;
        }
        if (tipo === 'R') {
            activeItemRechazado = index;
        }
    };

    if(Object.keys(eSolicitudes).length > 0){
        solicitudTitle = 'Solicitudes';
        existsSolicitudes = true;
    }                
</script>

<div>
    <h5 class="solicitud-title">{solicitudTitle}</h5>
    <div class="solicitudes-container {existsSolicitudes? '' : 'container-empty'}">
        {#if existsSolicitudes}        
                                    
            {#if eSolicitudes.en_tramite}             
                <h4>Solicitudes en Trámite</h4>
                <Carousel activeIndex={activeItemTramite} dark>
                    <ol class="carousel-indicators">
                        {#each eSolicitudes.en_tramite as solicitud, i}
                            <li class="{activeItemTramite === i ? 'active' : ''}"  on:click={() => changeItem('T', i)}></li>
                        {/each}
                    </ol>

                    <div class="carousel-inner">
                        {#each eSolicitudes.en_tramite as solicitud, i}
                            <CarouselItem>
                                <div class="card card-hover mb-lg-4 m-2 {activeItemTramite === i ? 'd-block' : 'd-none'}">
                                    <h6 class="solicitud-titulo">{solicitud.nombre_servicio_minus}</h6><hr>
                                    <p>Esta solicitud fue ingresada el <strong>{solicitud.fecha_creacion_v2}</strong> 
                                    a las <strong>{solicitud.hora_creacion_v2}</strong> y actualmente se encuentra 
                                    en <strong>proceso de revisión interno</strong>.</p>
                                </div>
                            </CarouselItem>
                        {/each}
                    </div>
                </Carousel>                                               
            {:else if eSolicitudes.pendiente}                        
                <h4>Solicitudes Pendientes</h4>
                <Carousel activeIndex={activeItemPendiente} dark>
                    <ol class="carousel-indicators">
                        {#each eSolicitudes.pendiente as solicitud, i}
                            <li class="{activeItemPendiente === i ? 'active' : ''}" on:click={() => changeItem('P', i)}></li>
                        {/each}
                    </ol>

                    <div class="carousel-inner">
                        {#each eSolicitudes.pendiente as solicitud, i}
                            <CarouselItem>
                                <div class="card card-hover mb-lg-4 m-2 {activeItemPendiente === i ? 'd-block' : 'd-none'}">
                                    <h6 class="solicitud-titulo">{solicitud.nombre_servicio_minus}</h6><hr>                                
                                    <p>Esta solicitud fue ingresada el <strong>{solicitud.fecha_creacion_v2}</strong> 
                                    a las <strong>{solicitud.hora_creacion_v2}</strong> y actualmente se encuentra 
                                    en <strong>proceso de revisión interno.</strong>.</p>
                                </div>
                            </CarouselItem>
                        {/each}
                    </div>
                </Carousel> 
            {/if}
            
            {#if eSolicitudes.aprobado}                         
                <h4>Solicitudes Aprobadas</h4>
                <Carousel activeIndex={activeItemAprobado} dark>
                    <ol class="carousel-indicators">
                        {#each eSolicitudes.aprobado as solicitud, i}
                            <li class="{activeItemAprobado === i ? 'active' : ''}" on:click={() => changeItem('A', i)}></li>
                        {/each}
                    </ol>

                    <div class="carousel-inner">
                        {#each eSolicitudes.aprobado as solicitud, i}
                            <CarouselItem>
                                <div class="card card-hover mb-lg-4 m-2 {activeItemAprobado === i ? 'd-block' : 'd-none'}">
                                    <h6 class="solicitud-titulo">{solicitud.nombre_servicio_minus}</h6><hr>
                                    <p>Esta solicitud fue ingresada el <strong>{solicitud.fecha_creacion_v2}</strong> 
                                    a las <strong>{solicitud.hora_creacion_v2}</strong> y actualmente se encuentra 
                                    en <strong>estado aprobado</strong>.</p>
                                </div>
                            </CarouselItem>
                        {/each}
                    </div>
                </Carousel>
            
            {:else if eSolicitudes.corregir}                        
                <h4>Solicitudes Corregir</h4>
                <Carousel activeIndex={activeItemCorregir} dark>
                    <ol class="carousel-indicators">
                        {#each eSolicitudes.corregir as solicitud, i}
                            <li class="{activeItemCorregir === i ? 'active' : ''}" on:click={() => changeItem('C', i)}></li>
                        {/each}
                    </ol>

                    <div class="carousel-inner">
                        {#each eSolicitudes.corregir as solicitud, i}
                            <CarouselItem>
                                <div class="card card-hover mb-lg-4 m-2 {activeItemCorregir === i ? 'd-block' : 'd-none'}">
                                    <h6 class="solicitud-titulo">{solicitud.nombre_servicio_minus}</h6><hr>                                
                                    <p>Esta solicitud fue ingresada el <strong>{solicitud.fecha_creacion_v2}</strong> 
                                    a las <strong>{solicitud.hora_creacion_v2}</strong> y actualmente se encuentra 
                                    en <strong>proceso de revisión correción.</strong>.</p>
                                </div>
                            </CarouselItem>
                        {/each}
                    </div>
                </Carousel> 
            
            {:else if eSolicitudes.rechazado}                        
                <h4>Solicitudes Rechazado</h4>
                <Carousel activeIndex={activeItemRechazado} dark>
                    <ol class="carousel-indicators">
                        {#each eSolicitudes.rechazado as solicitud, i}
                            <li class="{activeItemRechazado === i ? 'active' : ''}" on:click={() => changeItem('R', i)}></li>
                        {/each}
                    </ol>

                    <div class="carousel-inner">
                        {#each eSolicitudes.rechazado as solicitud, i}
                            <CarouselItem>
                                <div class="card card-hover mb-lg-4 m-2 {activeItemRechazado === i ? 'd-block' : 'd-none'}">
                                    <h6 class="solicitud-titulo">{solicitud.nombre_servicio_minus}</h6><hr>                                
                                    <p>Esta solicitud fue ingresada el <strong>{solicitud.fecha_creacion_v2}</strong> 
                                    a las <strong>{solicitud.hora_creacion_v2}</strong> y actualmente se encuentra 
                                    en <strong>proceso de revisión correción.</strong>.</p>
                                </div>
                            </CarouselItem>
                        {/each}
                    </div>
                </Carousel> 
            {/if}
        {:else}                             
            <p class="solicitudes-empty-text text-center">Usted no posee actualmente ninguna solicitud</p>          
        {/if}
    </div>
    {#if existsSolicitudes}    
        <div>
            <a href="/alu_solicitudbalcon/missolicitudes_new" class="btn btn-missolicitudes btn-primary mt-2"> Ver mis solicitudes</a>
        </div>
    {/if}
</div>
<style>

    .btn-missolicitudes {
        border-radius: 16px;
        opacity: 1;
        background-color: #12216A; 
        width: 100%;
        
        
    }
    .btn-missolicitudes:hover {        
        background-color: #0A4985;    
        font-weight: bold;
        border-color: #0A4985;
        transition: box-shadow 10s ease;
    }

    .solicitud-title {
        font-size: 1.25rem;
        font-weight: bold;
        color: #12216A;         
        text-align: center;
    }

    .solicitudes-container {
        background-color: #E8EFFB; /* Color de fondo del contenedor principal */
        padding: 0.5rem; /* Espaciado interior */
        border-radius: 15px; /* Bordes redondeados */
        margin-bottom: 0px;        
    }
    
    .solicitudes-container.container-empty{
        background-color: #FFFFFF;
        border: 2px dotted #707070;
        padding: 55% 15%;
        margin: 5px; /* Margen opcional */
        border-radius: 5px; /* Borde redondeado opcional */
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

    h4 {        
        font-weight: bold;
        margin-top: 1rem;
        color: #253CA6; 
        font-size: 1rem;
        text-align: center;
    }

    .card-hover {
        background-color: #ffffff; /* Fondo blanco para las tarjetas */
        border-radius: 12px; /* Bordes redondeados para las tarjetas */
        padding: 1.5rem; /* Espaciado interior de las tarjetas */
        box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1); /* Sombra sutil */
        margin-bottom: 1rem; /* Separación entre tarjetas */
        transition: box-shadow 0.3s ease; /* Transición suave al hacer hover */
    }

    .card-hover:hover {
        box-shadow: 0px 6px 12px rgba(0, 0, 0, 0.15); /* Sombra al hacer hover */
    }

    .solicitud-titulo {
        font-size: 1rem;
        font-weight: 600;
        color: #12216A;
        margin-bottom: 0.1rem;
    }

    p {
        font-size: 0.875rem;
        color: #717174; /* Gris suave */
        margin-bottom: 0rem;
    }    

    .carousel-indicators {
        position: absolute;
        bottom: -15px; /* Ajusta la posición del indicador de puntos */
        left: 35%;
        transform: translateX(-50%);
        display: flex;
        justify-content: center;
        list-style: none;
        
    }

    .carousel-indicators li {
        background-color: #D3DBE3;
        border-radius: 50%;
        width: 8px;
        height: 8px;
        margin: 0 5px;
        cursor: pointer;        
    }

    .carousel-indicators .active {
        background-color: #0A4985; /* Azul oscuro para el punto activo */
    }

    .solicitudes-title {
        font-size: 1.2rem;
        color: #12216A;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1.5rem;
    }

    .solicitudes-box {
        background-color: #F5F8FB;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        color: #707070;
    }

    .solicitudes-empty-text {
        font-size: 0.875rem;
        color: #707070;
    }
    
</style>
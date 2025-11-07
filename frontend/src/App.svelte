<script>
  import BalconServicios from "./lib/balcon/BalconServicios.svelte";
  import ToastContainer from "./lib/components/ToastContainer.svelte";
  import LoadingOverlay from "./lib/components/LoadingOverlay.svelte";
  import NotificationContainer from "./lib/components/NotificationContainer.svelte";
</script>

<!-- Vista única del Balcón de Servicios -->
<BalconServicios />

<!-- Componentes globales -->
<ToastContainer />
<LoadingOverlay />
<NotificationContainer />

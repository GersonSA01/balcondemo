<script>
    import { loading } from '$lib/store/loadingStore';
	import { Button, Modal, ModalBody, ModalFooter, ModalHeader, Spinner } from 'sveltestrap';
	import { addToast } from '$lib/store/toastStore';
	import { apiPOSTFormData } from '$lib/utils/requestUtils';
	import { createEventDispatcher, onMount } from 'svelte';
	import { goto } from '$app/navigation';

	export let aData;
	export let mToggle;
	export let mOpenModal;
	export let mTitle;
	export let mSize = 'lg';
	let mClass =
		'modal-dialog modal-dialog-centered modal-dialog-scrollable modal-fullscreen-lg-down';


	let pdfUrl;
	let action = '';

    onMount(() => {
		if (aData.pdfUrl) {
			pdfUrl = aData.pdfUrl;
		}

	});

</script>



<Modal isOpen={true} toggle={mToggle} size={mSize} class={mClass} backdrop="static">
	<ModalHeader toggle={mToggle} class="bg-primary text-white">
		<span class="text-white">{mTitle}</span>
	</ModalHeader>
	<ModalBody>
		<div class="container">
            <iframe
					src={pdfUrl}
					width="100%"
					height="500px"
					style="border: none;"
				></iframe>

		</div>
	</ModalBody>
	<ModalFooter>
		<Button color="secondary" class="rounded-5 btn-sm " on:click={mToggle}
			><i class="fe fe-x" /> Cerrar </Button
		>
	</ModalFooter>
</Modal>
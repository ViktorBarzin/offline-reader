<script lang="ts">
	/**
	 * App gate. Registers the app-shell service worker (so the installed PWA opens
	 * offline) and renders the current route. There is no auth/onboarding step — the
	 * app is served same-origin behind SSO; the Library and Reader read from
	 * IndexedDB and work with the network cut.
	 */
	import { onMount, type Snippet } from 'svelte';
	import { pwaInfo } from 'virtual:pwa-info';

	import '../app.css';
	import { scheduleSwUpdates } from '$lib/pwa';

	let { children }: { children: Snippet } = $props();

	const webManifestLink = pwaInfo ? pwaInfo.webManifest.linkTag : '';

	onMount(async () => {
		if ('serviceWorker' in navigator) {
			const { registerSW } = await import('virtual:pwa-register');
			registerSW({
				immediate: true,
				onRegisteredSW(_swUrl, registration) {
					if (registration) scheduleSwUpdates(registration);
				}
			});
		}
	});
</script>

<svelte:head>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- plugin-generated tag -->
	{@html webManifestLink}
</svelte:head>

<div class="app-shell">
	{@render children()}
</div>

<script lang="ts">
	/**
	 * App gate. Registers the app-shell service worker (so the installed PWA opens
	 * offline) and renders the current route. There is no auth/onboarding step — the
	 * app is served same-origin behind SSO; the Library and Reader read from
	 * IndexedDB and work with the network cut.
	 *
	 * On the production host it also loads the Rybbit script and names the
	 * signed-in Person from `GET /api/me` (ADR-0007). Offline, both fail quietly.
	 */
	import { onMount, type Snippet } from 'svelte';
	import { pwaInfo } from 'virtual:pwa-info';

	import '../app.css';
	import { clearPerson, identifyPerson, loadAnalytics } from '$lib/analytics';
	import { api, AuthWallError } from '$lib/api';
	import { scheduleSwUpdates } from '$lib/pwa';

	let { children }: { children: Snippet } = $props();

	const webManifestLink = pwaInfo ? pwaInfo.webManifest.linkTag : '';

	async function namePerson(): Promise<void> {
		try {
			const me = await api.me();
			if (me.person_id) identifyPerson(me.person_id, window);
			else clearPerson(window);
		} catch (err) {
			// The SSO session has gone; offline or any other failure changes nothing.
			if (err instanceof AuthWallError) clearPerson(window);
		}
	}

	onMount(async () => {
		if (loadAnalytics(document, location.hostname, window)) void namePerson();
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

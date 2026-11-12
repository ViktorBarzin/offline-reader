<script lang="ts">
	/**
	 * App gate. Registers the app-shell service worker (so the installed PWA opens
	 * offline) and renders the current route. There is no auth/onboarding step — the
	 * app is served same-origin behind SSO; the Library and Reader read from
	 * IndexedDB and work with the network cut.
	 *
	 * It also starts telemetry from what `GET /api/me` answers, which names the
	 * signed-in Person (ADR-0007). Off the production host that loads nothing.
	 */
	import { onMount, type Snippet } from 'svelte';
	import { pwaInfo } from 'virtual:pwa-info';

	import '../app.css';
	import { isProductionHost } from '@viktorbarzin/telemetry';

	import { PRODUCTION_HOSTS, startTelemetry } from '$lib/analytics';
	import { api, AuthWallError } from '$lib/api';
	import { scheduleSwUpdates } from '$lib/pwa';

	let { children }: { children: Snippet } = $props();

	const webManifestLink = pwaInfo ? pwaInfo.webManifest.linkTag : '';

	async function startAnalytics(): Promise<void> {
		try {
			startTelemetry({ me: await api.me() });
		} catch (err) {
			// The SSO session has gone, or there is no network: start from what was remembered.
			startTelemetry(err instanceof AuthWallError ? { signedOut: true } : { offline: true });
		}
	}

	onMount(async () => {
		if (isProductionHost(location.hostname, PRODUCTION_HOSTS)) void startAnalytics();
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

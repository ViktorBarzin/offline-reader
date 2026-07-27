/// <reference lib="webworker" />
/**
 * Offline Reader service worker (Workbox via `@vite-pwa/sveltekit` injectManifest).
 *
 * THE founding requirement (ADR-0006): the installed PWA must cold-start OFFLINE,
 * including on a never-visited deep link (`/read/<cid>/<pid>`). So we precache the
 * app shell + every content-hashed build asset and serve the shell for any in-scope
 * navigation. The app then renders entirely from IndexedDB — there is deliberately
 * NO runtime `/api` cache: captured pages live in IndexedDB (downloaded explicitly),
 * never in an HTTP cache, so nothing here can serve stale or partial capture data.
 *
 * Minimal app-shell handler copied from the tasks/tripit pattern
 * (tasks/frontend/src/service-worker.ts).
 */
import { clientsClaim } from 'workbox-core';
import { cleanupOutdatedCaches, matchPrecache, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { CacheFirst } from 'workbox-strategies';

declare let self: ServiceWorkerGlobalScope & {
	__WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

const ASSET_CACHE = 'offline-reader-assets-v1';

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);

/**
 * SPA navigation fallback: serve the precached app shell (index.html) for any
 * client-side route so a never-visited deep link boots offline. Precache-key
 * agnostic — try the precached shell, then the runtime cache, then the network.
 */
async function appShell(): Promise<Response> {
	const precached = (await matchPrecache('/index.html')) ?? (await matchPrecache('index.html'));
	if (precached) return precached;
	const cached = await caches.match('/index.html', { ignoreSearch: true });
	if (cached) return cached;
	return fetch('/index.html');
}

// `/api`, health and metrics must always reach the network; every other
// navigation falls back to the app shell.
registerRoute(
	new NavigationRoute(appShell, {
		denylist: [/^\/api\//, /^\/healthz$/, /^\/metrics$/]
	})
);

self.skipWaiting();
clientsClaim();

// Content-hashed build assets under /_app (immutable) — plus SvelteKit's generated
// version.json. Cache-first so the SPA boots offline on a cold navigation; a new
// deploy changes the hash, so a stale entry is never served.
registerRoute(
	({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/_app/'),
	new CacheFirst({ cacheName: ASSET_CACHE }),
	'GET'
);

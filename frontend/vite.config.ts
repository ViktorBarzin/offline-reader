import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [
		sveltekit(),
		// vite-plugin-pwa (SvelteKit integration), autoUpdate + injectManifest: a
		// hand-written app-shell service worker (src/service-worker.ts) that swaps
		// itself in on a new deploy. The installed PWA opens with no network and
		// reads captures from IndexedDB.
		SvelteKitPWA({
			registerType: 'autoUpdate',
			strategies: 'injectManifest',
			srcDir: 'src',
			filename: 'service-worker.ts',
			// Registration is done manually in +layout.svelte (virtual:pwa-register).
			injectRegister: null,
			manifest: {
				name: 'Offline Reader',
				short_name: 'Reader',
				description: 'Read whole websites offline — captured pages stored on your device.',
				start_url: '/',
				display: 'standalone',
				background_color: '#0b0b0f',
				theme_color: '#0b0b0f',
				icons: [
					{ src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
					{ src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
					{
						src: '/pwa-512x512.png',
						sizes: '512x512',
						type: 'image/png',
						purpose: 'maskable'
					}
				]
			},
			// spa + adapterFallback ⇒ the fallback index.html is added to the precache
			// manifest (self.__WB_MANIFEST) that the SW serves as the shell.
			kit: {
				spa: true,
				adapterFallback: 'index.html'
			},
			injectManifest: {
				globPatterns: ['client/**/*.{js,css,html,svg,png,ico,webp,woff,woff2,webmanifest}']
			},
			devOptions: {
				enabled: false
			}
		})
	],
	test: {
		include: ['src/**/*.{test,spec}.{js,ts}'],
		environment: 'node'
	}
});

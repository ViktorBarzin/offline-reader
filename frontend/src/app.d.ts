/// <reference types="vite-plugin-pwa/client" />
/// <reference types="vite-plugin-pwa/info" />
/// <reference types="vite-plugin-pwa/svelte" />

// See https://svelte.dev/docs/kit/types#app.d.ts
declare global {
	interface Window {
		/** Rybbit's script, once loaded (src/lib/analytics.ts). */
		rybbit?: import('$lib/analytics').Rybbit;
	}
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};

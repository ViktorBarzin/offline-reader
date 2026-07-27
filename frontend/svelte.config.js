import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		// SPA build: everything renders client-side from IndexedDB; the backend
		// serves build/ with an index.html fallback so deep links (/read/<cid>/<pid>)
		// boot the shell (tasks/tripit pattern).
		adapter: adapter({
			fallback: 'index.html',
			precompress: false
		}),
		// Absolute asset/SW paths — relative paths break service-worker registration
		// on deep links (learned in tripit; see tasks/frontend/svelte.config.js).
		paths: {
			relative: false
		},
		alias: {
			$lib: 'src/lib'
		}
	}
};

export default config;

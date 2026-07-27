/**
 * Online/offline as a Svelte store. Seeds from `navigator.onLine` and tracks the
 * window `online`/`offline` events. In a non-browser context it stays `true`.
 */
import { readable } from 'svelte/store';

export const online = readable(true, (set) => {
	if (typeof navigator === 'undefined' || typeof window === 'undefined') return;
	set(navigator.onLine);
	const goOnline = (): void => set(true);
	const goOffline = (): void => set(false);
	window.addEventListener('online', goOnline);
	window.addEventListener('offline', goOffline);
	return () => {
		window.removeEventListener('online', goOnline);
		window.removeEventListener('offline', goOffline);
	};
});

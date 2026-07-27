/**
 * Download a Capture onto the device for offline reading.
 *
 * iOS has NO Background Fetch, so this runs in the FOREGROUND (keep the app open).
 * It is chunked page-by-page and RESUMABLE: pages already in IndexedDB are skipped,
 * so a failed/interrupted download continues where it left off on the next tap.
 * Before a (potentially large) download we ask for persistent storage once
 * (feature-checked) to reduce the chance of eviction.
 *
 * Flow: fetch the manifest → for each not-yet-stored page fetch its HTML bytes and
 * put them in `pages` → finally store the capture meta + manifest in `captures`.
 * The capture is only marked stored once its pages are in place.
 */
import { api } from './api';
import * as db from './db';
import type { Capture, StoredCapture } from './types';

export interface DownloadProgress {
	/** Pages persisted so far (including ones skipped as already-stored). */
	done: number;
	/** Total pages in the manifest. */
	total: number;
	/** Bytes fetched during THIS run (already-stored pages add nothing). */
	bytes: number;
	/** The page currently being fetched, if any. */
	current?: string;
}

export interface DownloadOptions {
	onProgress?: (p: DownloadProgress) => void;
	signal?: AbortSignal;
	/** Skip the `navigator.storage.persist()` request (used by tests). */
	skipPersist?: boolean;
}

/** Ask the browser to keep our storage (best-effort; mitigates iOS eviction). */
export async function requestPersistentStorage(): Promise<boolean> {
	if (typeof navigator === 'undefined' || !navigator.storage?.persist) return false;
	try {
		return await navigator.storage.persist();
	} catch {
		return false;
	}
}

/**
 * Download a capture's pages + manifest into IndexedDB. `capture` is the meta from
 * the Library (used to build the stored record). Resolves with the StoredCapture
 * that was persisted. Throws (leaving already-stored pages in place, so a retry
 * resumes) if a page fetch fails or is aborted.
 */
export async function downloadCapture(
	capture: Capture,
	opts: DownloadOptions = {}
): Promise<StoredCapture> {
	const { onProgress, signal, skipPersist } = opts;

	if (!skipPersist) await requestPersistentStorage();

	const manifest = await api.manifest(capture.id);
	const pages = manifest.pages;
	const total = pages.length;

	let done = 0;
	let bytes = 0;
	onProgress?.({ done, total, bytes });

	for (const page of pages) {
		if (signal?.aborted) throw new DOMException('Download aborted', 'AbortError');

		if (await db.hasPage(capture.id, page.id)) {
			// Resume: already stored, count it and move on without re-fetching.
			done += 1;
			onProgress?.({ done, total, bytes });
			continue;
		}

		onProgress?.({ done, total, bytes, current: page.id });
		const buf = await api.pageBytes(capture.id, page.id, signal);
		await db.putPage(capture.id, page.id, buf, 'text/html');
		done += 1;
		bytes += buf.byteLength;
		onProgress?.({ done, total, bytes });
	}

	// All pages in place → record the capture meta + manifest. Prefer the manifest's
	// title/root_url (freshest) but keep the Library meta (status, size, created_at).
	const stored: StoredCapture = {
		...capture,
		title: manifest.title || capture.title,
		root_url: manifest.root_url || capture.root_url,
		page_count: total,
		pages,
		downloadedAt: Date.now()
	};
	await db.putCapture(stored);
	return stored;
}

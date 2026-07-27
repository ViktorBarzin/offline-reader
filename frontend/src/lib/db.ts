/**
 * The offline store (IndexedDB via `idb`). This is where Downloaded captures live
 * so the Reader works with the network cut; the backend is the source of truth and
 * this store is disposable (a Capture is always re-downloadable — ADR-0006).
 *
 * DB `offline-reader`:
 *  - `captures` keyPath `id`          — StoredCapture (capture meta + manifest pages)
 *  - `pages`    keyPath `[cid, pid]`  — StoredPage (page HTML as an ArrayBuffer,
 *                                       tripit `documentBlobs` style)
 *
 * This module is pure storage: no Svelte, no network.
 */
import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

import type { StoredCapture, StoredPage } from './types';

const DB_NAME = 'offline-reader';
const DB_VERSION = 1;

interface OfflineReaderDB extends DBSchema {
	captures: {
		key: string;
		value: StoredCapture;
	};
	pages: {
		key: [string, string];
		value: StoredPage;
		indexes: { 'by-cid': string };
	};
}

let dbPromise: Promise<IDBPDatabase<OfflineReaderDB>> | null = null;

function hasIndexedDb(): boolean {
	return typeof indexedDB !== 'undefined';
}

function db(): Promise<IDBPDatabase<OfflineReaderDB>> {
	if (!dbPromise) {
		dbPromise = openDB<OfflineReaderDB>(DB_NAME, DB_VERSION, {
			upgrade(database, oldVersion) {
				// Version-aware so a future migration adds stores in place rather than
				// re-creating (and throwing on) ones that already exist.
				if (oldVersion < 1) {
					database.createObjectStore('captures', { keyPath: 'id' });
					const pages = database.createObjectStore('pages', { keyPath: ['cid', 'pid'] });
					// Secondary index so a capture's pages can be counted/evicted without
					// scanning the whole store.
					pages.createIndex('by-cid', 'cid');
				}
			}
		});
	}
	return dbPromise;
}

/** Test-only: drop the memoized connection so the next call reopens against a
 * freshly-swapped `globalThis.indexedDB`. */
export function _resetForTests(): void {
	dbPromise = null;
}

/**
 * Strip Svelte 5 `$state` proxies (not structured-cloneable) to a plain JSON value
 * before an IndexedDB write. Capture meta is pure JSON, so a round-trip is always
 * safe. NEVER applied to page bytes — a JSON round-trip would destroy the
 * ArrayBuffer; those are structured-cloneable and stored as-is.
 */
function plain<T>(value: T): T {
	return JSON.parse(JSON.stringify(value)) as T;
}

// --- Captures (meta + manifest) --------------------------------------------

/** Upsert a downloaded capture's meta + manifest. */
export async function putCapture(capture: StoredCapture): Promise<void> {
	if (!hasIndexedDb()) return;
	await (await db()).put('captures', plain(capture));
}

export async function getCapture(id: string): Promise<StoredCapture | undefined> {
	if (!hasIndexedDb()) return undefined;
	return (await db()).get('captures', id);
}

export async function getAllCaptures(): Promise<StoredCapture[]> {
	if (!hasIndexedDb()) return [];
	return (await db()).getAll('captures');
}

export async function hasCapture(id: string): Promise<boolean> {
	if (!hasIndexedDb()) return false;
	return (await (await db()).getKey('captures', id)) !== undefined;
}

/** Delete a capture and cascade to every page it holds. */
export async function deleteCapture(id: string): Promise<void> {
	if (!hasIndexedDb()) return;
	const database = await db();
	await database.delete('captures', id);
	await deletePagesForCapture(id);
}

// --- Pages (HTML bytes) -----------------------------------------------------

/** Store one page's HTML bytes (keyed by [cid, pid]). Bytes arrive as an
 * ArrayBuffer; the mime travels with them so a correctly-typed Blob/string can be
 * built on read. */
export async function putPage(
	cid: string,
	pid: string,
	bytes: ArrayBuffer,
	mime = 'text/html'
): Promise<void> {
	if (!hasIndexedDb()) return;
	await (await db()).put('pages', { cid, pid, bytes, mime });
}

export async function getPage(cid: string, pid: string): Promise<StoredPage | undefined> {
	if (!hasIndexedDb()) return undefined;
	return (await db()).get('pages', [cid, pid]);
}

/** The raw HTML bytes for a page, or undefined if not downloaded. */
export async function getPageBytes(cid: string, pid: string): Promise<ArrayBuffer | undefined> {
	return (await getPage(cid, pid))?.bytes;
}

/** Whether a page is already stored — used to skip it on a resumed download. */
export async function hasPage(cid: string, pid: string): Promise<boolean> {
	if (!hasIndexedDb()) return false;
	return (await (await db()).getKey('pages', [cid, pid])) !== undefined;
}

/** How many of a capture's pages are stored (for partial-download UI). */
export async function pageCountFor(cid: string): Promise<number> {
	if (!hasIndexedDb()) return 0;
	return (await db()).countFromIndex('pages', 'by-cid', cid);
}

/** Drop every page belonging to a capture (cursor delete via the by-cid index). */
export async function deletePagesForCapture(cid: string): Promise<void> {
	if (!hasIndexedDb()) return;
	const tx = (await db()).transaction('pages', 'readwrite');
	let cursor = await tx.store.index('by-cid').openCursor(cid);
	while (cursor) {
		await cursor.delete();
		cursor = await cursor.continue();
	}
	await tx.done;
}

// --- Storage usage ----------------------------------------------------------

/** Total bytes of all stored page HTML (for the storage-usage display). Computed
 * from the actual buffers so it reflects what is really on the device. */
export async function storedBytes(): Promise<number> {
	if (!hasIndexedDb()) return 0;
	const rows = await (await db()).getAll('pages');
	return rows.reduce((sum, r) => sum + r.bytes.byteLength, 0);
}

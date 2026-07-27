import 'fake-indexeddb/auto';

import { IDBFactory } from 'fake-indexeddb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as db from './db';
import { downloadCapture, type DownloadProgress } from './download';
import type { Capture } from './types';

const CAPTURE: Capture = {
	id: 'c1',
	root_url: 'https://docs.test/',
	title: 'Docs',
	status: 'done',
	page_count: 3,
	size_bytes: 30,
	created_at: '2026-07-27T00:00:00Z'
};

const MANIFEST = {
	cid: 'c1',
	root_url: 'https://docs.test/',
	title: 'Docs',
	pages: [
		{ id: 'p1', url: 'https://docs.test/a', title: 'A', file: 'p1.html' },
		{ id: 'p2', url: 'https://docs.test/b', title: 'B', file: 'p2.html' },
		{ id: 'p3', url: 'https://docs.test/c', title: 'C', file: 'p3.html' }
	]
};

let fetchMock: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status: 200,
		headers: { 'content-type': 'application/json' }
	});
}

function htmlResponse(body: string): Response {
	return new Response(body, { status: 200, headers: { 'content-type': 'text/html' } });
}

/** Route the mock: manifest → MANIFEST, page → its id as HTML. */
function routeOk(url: string): Response {
	if (url.endsWith('/manifest')) return jsonResponse(MANIFEST);
	const m = url.match(/\/pages\/(\w+)$/);
	if (m) return htmlResponse(`<!doctype html><title>${m[1]}</title>`);
	throw new Error(`unexpected url ${url}`);
}

beforeEach(() => {
	globalThis.indexedDB = new IDBFactory();
	db._resetForTests();
	fetchMock = vi.fn();
	vi.stubGlobal('fetch', fetchMock);
	// No navigator.storage in node; downloadCapture feature-checks, but pass
	// skipPersist to be explicit and deterministic.
});

afterEach(() => vi.unstubAllGlobals());

describe('downloadCapture', () => {
	it('fetches the manifest + every page into IndexedDB and stores the capture meta', async () => {
		fetchMock.mockImplementation((url: string) => Promise.resolve(routeOk(url)));

		const progress: DownloadProgress[] = [];
		const stored = await downloadCapture(CAPTURE, {
			skipPersist: true,
			onProgress: (p) => progress.push({ ...p })
		});

		// All three pages persisted, decodable.
		expect(await db.pageCountFor('c1')).toBe(3);
		expect(new TextDecoder().decode(new Uint8Array((await db.getPageBytes('c1', 'p2'))!))).toContain('p2');

		// Capture meta + manifest stored.
		expect(stored.pages.map((p) => p.id)).toEqual(['p1', 'p2', 'p3']);
		expect(stored.downloadedAt).toBeGreaterThan(0);
		expect(await db.hasCapture('c1')).toBe(true);

		// Progress ended at done === total.
		const last = progress.at(-1)!;
		expect(last.done).toBe(3);
		expect(last.total).toBe(3);
		expect(last.bytes).toBeGreaterThan(0);
	});

	it('resumes: skips pages already in IndexedDB and only fetches the missing ones', async () => {
		// Pre-store p1 and p2 as if a prior run got that far.
		await db.putPage('c1', 'p1', new TextEncoder().encode('old1').buffer as ArrayBuffer);
		await db.putPage('c1', 'p2', new TextEncoder().encode('old2').buffer as ArrayBuffer);

		fetchMock.mockImplementation((url: string) => Promise.resolve(routeOk(url)));
		await downloadCapture(CAPTURE, { skipPersist: true });

		// Only the manifest + the single missing page (p3) were fetched.
		const pageFetches = fetchMock.mock.calls.filter(([u]) => /\/pages\//.test(u as string));
		expect(pageFetches.map(([u]) => u)).toEqual(['/api/captures/c1/pages/p3']);
		// Pre-existing bytes were NOT overwritten.
		expect(new TextDecoder().decode(new Uint8Array((await db.getPageBytes('c1', 'p1'))!))).toBe('old1');
		expect(await db.pageCountFor('c1')).toBe(3);
	});

	it('throws on a page fetch failure but leaves already-fetched pages for a resume', async () => {
		fetchMock.mockImplementation((url: string) => {
			if (url.endsWith('/manifest')) return Promise.resolve(jsonResponse(MANIFEST));
			if (url.endsWith('/pages/p1')) return Promise.resolve(htmlResponse('<p>p1</p>'));
			// p2 fails
			return Promise.resolve(new Response('boom', { status: 500 }));
		});

		await expect(downloadCapture(CAPTURE, { skipPersist: true })).rejects.toBeTruthy();

		// p1 persisted; capture meta NOT written (download incomplete) → a retry resumes.
		expect(await db.hasPage('c1', 'p1')).toBe(true);
		expect(await db.hasPage('c1', 'p2')).toBe(false);
		expect(await db.hasCapture('c1')).toBe(false);
	});

	it('aborts promptly when the signal is already aborted', async () => {
		fetchMock.mockImplementation((url: string) => Promise.resolve(routeOk(url)));
		const ctrl = new AbortController();
		ctrl.abort();
		await expect(
			downloadCapture(CAPTURE, { skipPersist: true, signal: ctrl.signal })
		).rejects.toMatchObject({ name: 'AbortError' });
		expect(await db.pageCountFor('c1')).toBe(0);
	});
});

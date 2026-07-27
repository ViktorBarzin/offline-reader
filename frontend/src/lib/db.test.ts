import 'fake-indexeddb/auto';

import { IDBFactory } from 'fake-indexeddb';
import { beforeEach, describe, expect, it } from 'vitest';

import * as db from './db';
import type { Capture, ManifestPage, StoredCapture } from './types';

function bytesOf(text: string): ArrayBuffer {
	return new TextEncoder().encode(text).buffer as ArrayBuffer;
}

function textOf(buf: ArrayBuffer): string {
	return new TextDecoder().decode(new Uint8Array(buf));
}

function capture(id: string, extra: Partial<Capture> = {}): Capture {
	return {
		id,
		root_url: `https://site.test/${id}`,
		title: `Capture ${id}`,
		status: 'done',
		page_count: 3,
		size_bytes: 1000,
		created_at: '2026-07-27T00:00:00Z',
		...extra
	};
}

function page(id: string, url: string): ManifestPage {
	return { id, url, title: `Page ${id}`, file: `${id}.html` };
}

function stored(id: string, pages: ManifestPage[]): StoredCapture {
	return { ...capture(id, { page_count: pages.length }), pages, downloadedAt: 123 };
}

beforeEach(() => {
	// Fresh in-memory IndexedDB per test, and a fresh memoized connection.
	globalThis.indexedDB = new IDBFactory();
	db._resetForTests();
});

describe('pages store', () => {
	it('round-trips page HTML through an ArrayBuffer (bytes preserved)', async () => {
		const html = '<!doctype html><title>hi</title><p>café — 世界</p>';
		await db.putPage('c1', 'p1', bytesOf(html));

		const row = await db.getPage('c1', 'p1');
		expect(row).toBeDefined();
		expect(row?.mime).toBe('text/html');
		expect(row?.bytes).toBeInstanceOf(ArrayBuffer);
		expect(textOf(row!.bytes)).toBe(html);

		const buf = await db.getPageBytes('c1', 'p1');
		expect(buf).toBeInstanceOf(ArrayBuffer);
		expect(textOf(buf!)).toBe(html);
	});

	it('keys pages by [cid, pid] — same pid under different captures is distinct', async () => {
		await db.putPage('c1', 'shared', bytesOf('one'));
		await db.putPage('c2', 'shared', bytesOf('two'));
		expect(textOf((await db.getPageBytes('c1', 'shared'))!)).toBe('one');
		expect(textOf((await db.getPageBytes('c2', 'shared'))!)).toBe('two');
	});

	it('hasPage reflects stored state (drives resume)', async () => {
		expect(await db.hasPage('c1', 'p1')).toBe(false);
		await db.putPage('c1', 'p1', bytesOf('x'));
		expect(await db.hasPage('c1', 'p1')).toBe(true);
	});

	it('counts a capture’s stored pages via the by-cid index', async () => {
		await db.putPage('c1', 'p1', bytesOf('a'));
		await db.putPage('c1', 'p2', bytesOf('b'));
		await db.putPage('c2', 'p1', bytesOf('c'));
		expect(await db.pageCountFor('c1')).toBe(2);
		expect(await db.pageCountFor('c2')).toBe(1);
	});

	it('missing page reads as undefined', async () => {
		expect(await db.getPage('nope', 'nope')).toBeUndefined();
		expect(await db.getPageBytes('nope', 'nope')).toBeUndefined();
	});
});

describe('captures store', () => {
	it('stores and reads a capture meta + manifest', async () => {
		const sc = stored('c1', [page('p1', 'https://site.test/a'), page('p2', 'https://site.test/b')]);
		await db.putCapture(sc);

		const got = await db.getCapture('c1');
		expect(got?.title).toBe('Capture c1');
		expect(got?.pages.map((p) => p.id)).toEqual(['p1', 'p2']);
		expect(await db.hasCapture('c1')).toBe(true);
		expect((await db.getAllCaptures()).map((c) => c.id)).toEqual(['c1']);
	});
});

describe('deletion cascade', () => {
	it('deleteCapture removes the capture and all its pages, leaving others', async () => {
		await db.putCapture(stored('c1', [page('p1', 'u1'), page('p2', 'u2')]));
		await db.putPage('c1', 'p1', bytesOf('a'));
		await db.putPage('c1', 'p2', bytesOf('b'));
		await db.putCapture(stored('c2', [page('p1', 'u3')]));
		await db.putPage('c2', 'p1', bytesOf('c'));

		await db.deleteCapture('c1');

		expect(await db.hasCapture('c1')).toBe(false);
		expect(await db.pageCountFor('c1')).toBe(0);
		expect(await db.getPageBytes('c1', 'p1')).toBeUndefined();
		// c2 untouched
		expect(await db.hasCapture('c2')).toBe(true);
		expect(await db.pageCountFor('c2')).toBe(1);
	});
});

describe('storage usage', () => {
	it('sums the byte length of stored pages', async () => {
		await db.putPage('c1', 'p1', bytesOf('12345')); // 5 bytes
		await db.putPage('c1', 'p2', bytesOf('123')); // 3 bytes
		expect(await db.storedBytes()).toBe(8);
	});
});

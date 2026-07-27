import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError, AuthWallError } from './api';

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
	fetchMock = vi.fn();
	vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

function jsonResponse(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

/** A fetch Response as it appears with redirect:'manual' after a cross-origin 3xx. */
function opaqueRedirect(): Response {
	return {
		type: 'opaqueredirect',
		ok: false,
		status: 0,
		headers: new Headers(),
		json: async () => ({}),
		arrayBuffer: async () => new ArrayBuffer(0)
	} as unknown as Response;
}

describe('api requests', () => {
	it('lists captures from GET /api/captures', async () => {
		fetchMock.mockResolvedValue(jsonResponse([{ id: 'c1' }, { id: 'c2' }]));
		const list = await api.listCaptures();
		expect(list.map((c) => c.id)).toEqual(['c1', 'c2']);
		expect(fetchMock).toHaveBeenCalledWith('/api/captures', expect.objectContaining({ redirect: 'manual' }));
	});

	it('POSTs a create body with a JSON content-type', async () => {
		fetchMock.mockResolvedValue(jsonResponse({ id: 'new', status: 'queued' }));
		await api.createCapture({ url: 'https://x.test', scope_type: 'prefix' });
		const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body as string)).toEqual({ url: 'https://x.test', scope_type: 'prefix' });
		expect((init.headers as Record<string, string>)['content-type']).toBe('application/json');
	});

	it('encodes ids in the manifest path', async () => {
		fetchMock.mockResolvedValue(jsonResponse({ cid: 'a/b', root_url: '', title: '', pages: [] }));
		await api.manifest('a/b');
		expect(fetchMock).toHaveBeenCalledWith('/api/captures/a%2Fb/manifest', expect.anything());
	});

	it('accepts a 204 (no content) — delete success', async () => {
		fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
		await expect(api.deleteCapture('c1')).resolves.toBeUndefined();
	});

	it('throws ApiError on a non-ok status', async () => {
		fetchMock.mockResolvedValue(new Response('boom', { status: 500 }));
		const err = await api.listCaptures().catch((e: unknown) => e);
		expect(err).toBeInstanceOf(ApiError);
		expect((err as ApiError).status).toBe(500);
	});

	it('throws AuthWallError on an opaque redirect (SSO bounce)', async () => {
		fetchMock.mockResolvedValue(opaqueRedirect());
		await expect(api.listCaptures()).rejects.toBeInstanceOf(AuthWallError);
	});

	it('throws AuthWallError on an ok but non-JSON body (login HTML)', async () => {
		fetchMock.mockResolvedValue(
			new Response('<!doctype html><title>Sign in</title>', {
				status: 200,
				headers: { 'content-type': 'text/html' }
			})
		);
		await expect(api.listCaptures()).rejects.toBeInstanceOf(AuthWallError);
	});
});

describe('pageBytes', () => {
	it('returns raw ArrayBuffer bytes for an html page', async () => {
		const html = '<!doctype html><p>hi</p>';
		fetchMock.mockResolvedValue(
			new Response(html, { status: 200, headers: { 'content-type': 'text/html; charset=utf-8' } })
		);
		const buf = await api.pageBytes('c1', 'p1');
		expect(buf).toBeInstanceOf(ArrayBuffer);
		expect(new TextDecoder().decode(new Uint8Array(buf))).toBe(html);
		expect(fetchMock).toHaveBeenCalledWith('/api/captures/c1/pages/p1', expect.objectContaining({ redirect: 'manual' }));
	});

	it('treats an SSO bounce during a page fetch as the auth wall', async () => {
		fetchMock.mockResolvedValue(opaqueRedirect());
		await expect(api.pageBytes('c1', 'p1')).rejects.toBeInstanceOf(AuthWallError);
	});

	it('throws ApiError when a page returns JSON (error envelope, not HTML)', async () => {
		fetchMock.mockResolvedValue(jsonResponse({ error: 'gone' }, 404));
		await expect(api.pageBytes('c1', 'p1')).rejects.toBeInstanceOf(ApiError);
	});
});

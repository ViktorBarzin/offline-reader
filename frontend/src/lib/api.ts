/**
 * Thin same-origin client for the Offline Reader API (all under `/api`). The PWA
 * is served same-origin behind SSO; the client sends no auth of its own — the
 * session cookie (or the backend's DEV_USER fallback) carries identity.
 *
 * As in tasks/tripit we use `redirect: 'manual'` so an Authentik forward-auth
 * bounce (a cross-origin 3xx to the SSO login) surfaces as an opaque redirect we
 * can distinguish from real data, rather than being followed into login HTML that
 * masquerades as a corrupt API reply.
 */
import { API_BASE } from './config';
import type { Capture, CreateCaptureBody, Manifest } from './types';

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** The SSO wall (session expired): a request was bounced to the login page.
 * Distinct from being offline — remediation is a full navigation to '/'. */
export class AuthWallError extends Error {
	constructor() {
		super('auth-wall');
		this.name = 'AuthWallError';
	}
}

function url(path: string): string {
	return `${API_BASE}${path}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(url(path), {
		credentials: 'same-origin',
		redirect: 'manual',
		...init,
		headers: {
			accept: 'application/json',
			...(init?.body ? { 'content-type': 'application/json' } : {}),
			...init?.headers
		}
	});
	if (res.type === 'opaqueredirect') throw new AuthWallError();
	if (!res.ok) throw new ApiError(res.status, `${init?.method ?? 'GET'} ${path} → ${res.status}`);
	if (res.status === 204) return undefined as T;
	const contentType = res.headers.get('content-type') ?? '';
	// An OK response that isn't JSON is the SSO login HTML served in place of the
	// API (a same-origin wall that doesn't redirect) — the auth wall, not data.
	if (!contentType.includes('application/json')) throw new AuthWallError();
	return (await res.json()) as T;
}

export const api = {
	/** GET /api/captures — the Library list. */
	listCaptures(): Promise<Capture[]> {
		return request<Capture[]>('/captures');
	},

	/** GET /api/captures/{id} — poll while status is queued/crawling. */
	getCapture(id: string): Promise<Capture> {
		return request<Capture>(`/captures/${encodeURIComponent(id)}`);
	},

	/** POST /api/captures — submit a URL to capture. */
	createCapture(body: CreateCaptureBody): Promise<Capture> {
		return request<Capture>('/captures', {
			method: 'POST',
			body: JSON.stringify(body)
		});
	},

	/** DELETE /api/captures/{id}. */
	deleteCapture(id: string): Promise<void> {
		return request<void>(`/captures/${encodeURIComponent(id)}`, { method: 'DELETE' });
	},

	/** POST /api/captures/{id}/refresh — re-crawl and replace. */
	refreshCapture(id: string): Promise<Capture> {
		return request<Capture>(`/captures/${encodeURIComponent(id)}/refresh`, { method: 'POST' });
	},

	/** GET /api/captures/{id}/manifest — the ordered reader TOC. */
	manifest(id: string): Promise<Manifest> {
		return request<Manifest>(`/captures/${encodeURIComponent(id)}/manifest`);
	},

	/** URL of a single page's self-contained HTML. */
	pageUrl(cid: string, pid: string): string {
		return url(`/captures/${encodeURIComponent(cid)}/pages/${encodeURIComponent(pid)}`);
	},

	/**
	 * GET /api/captures/{id}/pages/{page_id} as raw bytes (text/html). Not JSON, so
	 * it bypasses `request` — but still honours the auth-wall signals so a bounced
	 * download doesn't silently store login HTML as a page.
	 */
	async pageBytes(cid: string, pid: string, signal?: AbortSignal): Promise<ArrayBuffer> {
		const res = await fetch(this.pageUrl(cid, pid), {
			credentials: 'same-origin',
			redirect: 'manual',
			signal
		});
		if (res.type === 'opaqueredirect') throw new AuthWallError();
		if (!res.ok) throw new ApiError(res.status, `GET page ${cid}/${pid} → ${res.status}`);
		const contentType = res.headers.get('content-type') ?? '';
		if (contentType.includes('application/json')) {
			// The pages endpoint returns HTML; a JSON body here is an error envelope.
			throw new ApiError(res.status, `GET page ${cid}/${pid} → unexpected JSON`);
		}
		return res.arrayBuffer();
	}
};

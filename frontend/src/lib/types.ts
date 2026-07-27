/**
 * THE API + IndexedDB contract types. Kept in one place so the api client, the
 * offline store, and the UI agree on shapes.
 */

/** Capture lifecycle, as reported by the backend. */
export type CaptureStatus = 'queued' | 'crawling' | 'done' | 'failed';

/** Crawl scope, widest to narrowest is domain > host > prefix > page. */
export type ScopeType = 'page' | 'prefix' | 'host' | 'domain';

/** A Capture as returned by `GET /api/captures` and `GET /api/captures/{id}`. */
export interface Capture {
	id: string;
	root_url: string;
	title: string;
	status: CaptureStatus;
	page_count: number;
	size_bytes: number;
	created_at: string;
}

/** One page entry in a capture's manifest (the ordered reader TOC). */
export interface ManifestPage {
	id: string;
	url: string;
	title: string;
	file: string;
}

/** `GET /api/captures/{id}/manifest`. */
export interface Manifest {
	cid: string;
	root_url: string;
	title: string;
	pages: ManifestPage[];
}

/** Body for `POST /api/captures`. */
export interface CreateCaptureBody {
	url: string;
	scope_type?: ScopeType;
	max_pages?: number;
	include?: string;
	exclude?: string;
}

/**
 * A capture stored offline in IndexedDB (`captures` store, keyPath `id`): the
 * capture meta merged with its manifest pages plus the download timestamp.
 */
export interface StoredCapture extends Capture {
	pages: ManifestPage[];
	downloadedAt: number;
}

/**
 * A page's HTML stored offline in IndexedDB (`pages` store, keyPath `[cid, pid]`).
 * Bytes are held as an ArrayBuffer (portably structured-cloneable — the tripit
 * `documentBlobs` shape); a Blob/string is reconstructed on read.
 */
export interface StoredPage {
	cid: string;
	pid: string;
	bytes: ArrayBuffer;
	mime: string;
}

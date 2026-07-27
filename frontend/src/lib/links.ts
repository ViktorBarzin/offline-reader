/**
 * Inter-page link rewriting for the Reader.
 *
 * THE PROBLEM. Captured pages are static, self-contained HTML with the site's
 * ORIGINAL absolute URLs still in their `<a href>`s. We render each page in a
 * sandboxed `<iframe srcdoc>` WITHOUT `allow-scripts` (scripts are stripped
 * server-side; keeping the frame script-less is the security boundary — ADR-0006)
 * and WITHOUT `allow-same-origin`. That means:
 *   - we cannot run a click handler INSIDE the iframe (no scripts), and
 *   - we cannot read the iframe DOM from the parent (opaque origin),
 * so the ONLY navigation signal the parent can act on is a real top-level
 * navigation the link itself performs.
 *
 * THE APPROACH (robust, best-effort). Before setting `srcdoc`, parse the HTML and
 * rewrite every `<a href>`:
 *   - A link whose (resolved, normalized) target is another CAPTURED page →
 *     rewrite its href to this app's reader route `${appOrigin}/read/{cid}/{pid}`
 *     and set `target="_top"`. Clicking navigates the TOP window to that route
 *     (the iframe is granted `allow-top-navigation-by-user-activation`). This is a
 *     full navigation, so the app boots and renders the target page from
 *     IndexedDB — it works OFFLINE. `appOrigin` MUST be absolute at render time
 *     (we pass `location.origin`) so the URL resolves against our origin, not the
 *     iframe's opaque `about:srcdoc` base.
 *   - Any other http(s) link → resolve to an absolute URL and set
 *     `target="_blank" rel="noopener noreferrer"`. It opens in a new tab when the
 *     iframe is granted `allow-popups`; with no network the browser simply fails to
 *     load it (graceful). These links are marked `data-external`.
 *   - `javascript:` links are neutralized (href removed).
 *   - `mailto:`/`tel:` and pure in-page `#fragment` links are left untouched.
 *
 * The TOC (built from the manifest) is the PRIMARY navigation and does fast
 * client-side routing; link rewriting is the best-effort in-page path.
 *
 * Pure and DOM-based (`DOMParser`) so it is deterministic and unit-testable.
 */

export interface RewritePage {
	id: string;
	url: string;
}

export interface RewriteOptions {
	/** The capture id — used to build reader routes. */
	cid: string;
	/** The capture's manifest pages (id + original url). */
	pages: RewritePage[];
	/** The original URL of the page being rendered — the base for relative hrefs. */
	pageUrl: string;
	/** Absolute origin of THIS app (e.g. `https://reader.example`). Required for
	 * internal links to resolve correctly inside the opaque srcdoc iframe. Empty
	 * string yields root-relative routes (fine in unit tests). */
	appOrigin?: string;
}

/**
 * Canonical key for comparing a link target to a captured page URL. Ignores the
 * scheme (http/https treated alike — sites mix them internally), lowercases the
 * host, drops a single trailing slash and the fragment, and keeps the query.
 * Returns null for non-http(s) URLs (mailto:, tel:, javascript:, data:, …).
 */
export function normalizeUrl(raw: string, base?: string): string | null {
	let u: URL;
	try {
		u = base ? new URL(raw, base) : new URL(raw);
	} catch {
		return null;
	}
	if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
	let path = u.pathname || '/';
	if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
	return `${u.host.toLowerCase()}${path}${u.search}`;
}

/**
 * Rewrite the `<a href>`s in a captured page's HTML for offline in-app reading.
 * Returns a complete HTML document string ready for `iframe.srcdoc`.
 */
export function rewriteLinks(html: string, opts: RewriteOptions): string {
	const { cid, pages, pageUrl, appOrigin = '' } = opts;

	// url-key → captured page id
	const byKey = new Map<string, string>();
	for (const p of pages) {
		const key = normalizeUrl(p.url);
		if (key) byKey.set(key, p.id);
	}

	const doc = new DOMParser().parseFromString(html, 'text/html');

	for (const a of Array.from(doc.querySelectorAll('a[href]'))) {
		const raw = (a.getAttribute('href') ?? '').trim();
		if (raw === '' || raw.startsWith('#')) continue; // in-page anchor / empty — leave

		const scheme = raw.slice(0, raw.indexOf(':') + 1).toLowerCase();
		if (scheme === 'javascript:') {
			a.removeAttribute('href');
			a.setAttribute('data-stripped', 'js');
			continue;
		}
		if (scheme === 'mailto:' || scheme === 'tel:') continue; // leave as-is

		const key = normalizeUrl(raw, pageUrl);
		if (key && byKey.has(key)) {
			// Captured page → in-app reader route, navigate the top window.
			const pid = byKey.get(key) as string;
			a.setAttribute('href', `${appOrigin}/read/${encodeURIComponent(cid)}/${encodeURIComponent(pid)}`);
			a.setAttribute('target', '_top');
			a.setAttribute('data-internal', 'true');
			a.removeAttribute('download');
		} else {
			// Un-captured http(s) (or unresolvable) → open online in a new tab.
			let abs = raw;
			try {
				abs = new URL(raw, pageUrl).href;
			} catch {
				/* keep raw */
			}
			a.setAttribute('href', abs);
			a.setAttribute('target', '_blank');
			a.setAttribute('rel', 'noopener noreferrer');
			a.setAttribute('data-external', 'true');
		}
	}

	return `<!doctype html>${doc.documentElement.outerHTML}`;
}

/**
 * Product analytics in the PWA (ADR-0007, infra ADR-0041).
 *
 * Rybbit's script, served from the Ingest path `/_t/r/`, records pageviews and
 * session replay on the production host only, with password fields masked and
 * other inputs left visible. `app.html` carries
 * `<meta name="analytics" content="sdk">`, which tells the edge injection
 * plugin that this app loads the script itself. Offline, the script simply
 * does not load.
 *
 * Once `GET /api/me` names the signed-in Person (their Authentik `uid`),
 * `identifyPerson` hands it to Rybbit, so the anonymous visits before join the
 * same Person; `clearPerson` undoes it when the SSO session has gone. Browser
 * custom events wait for the shared `@viktorbarzin/telemetry` package.
 */

/** Hosts whose visits count. Anything else (localhost, a preview) loads nothing. */
export const PRODUCTION_HOSTS: readonly string[] = Object.freeze([
	'offline-reader.viktorbarzin.me'
]);

/** The Analytics site first-party apps are recorded under (`apps`). */
export const SITE_ID = '1';

export const SCRIPT_SRC = '/_t/r/script.js';

export interface Rybbit {
	identify: (id: string) => void;
	clearUserId: () => void;
}

export interface AnalyticsWindow {
	rybbit?: Rybbit;
}

export interface ScriptElement {
	src?: string;
	defer?: boolean;
	setAttribute: (name: string, value: string) => void;
	addEventListener: (event: string, listener: () => void) => void;
}

/** The part of `document` this module uses; `S` is its script element. */
export interface AnalyticsDocument<S extends ScriptElement = ScriptElement> {
	createElement: (tag: 'script') => S;
	head: { appendChild: (el: S) => unknown };
}

let loaded = false;
/** The Person id Rybbit was last told, or waits to be told. */
let named: string | null = null;
/** An identify waiting for the script to load. */
let pending: string | null = null;

export function isProductionHost(hostname: string): boolean {
	return PRODUCTION_HOSTS.includes(hostname);
}

/** Add the Rybbit script to the page on the production host. True when added. */
export function loadAnalytics<S extends ScriptElement>(
	doc: AnalyticsDocument<S>,
	hostname: string,
	win: AnalyticsWindow
): boolean {
	if (loaded || !isProductionHost(hostname)) return false;
	loaded = true;
	const script = doc.createElement('script');
	script.src = SCRIPT_SRC;
	script.defer = true;
	script.setAttribute('data-site-id', SITE_ID);
	script.setAttribute('data-replay-mask-all-inputs', 'false');
	script.setAttribute('data-replay-mask-input-options', '{"password":true}');
	script.addEventListener('load', () => {
		if (pending && win.rybbit) {
			win.rybbit.identify(pending);
			pending = null;
		}
	});
	doc.head.appendChild(script);
	return true;
}

/** Name the signed-in Person, now or once the script has loaded. */
export function identifyPerson(personId: string | null, win: AnalyticsWindow): void {
	if (!personId || personId === named) return;
	named = personId;
	if (win.rybbit) {
		win.rybbit.identify(personId);
	} else {
		pending = personId;
	}
}

/** Forget the Person, so the next visitor on this browser is anonymous. */
export function clearPerson(win: AnalyticsWindow): void {
	pending = null;
	if (named === null) return;
	named = null;
	win.rybbit?.clearUserId();
}

/** Forget what this module has done. For tests. */
export function resetAnalytics(): void {
	loaded = false;
	named = null;
	pending = null;
}

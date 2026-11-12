/**
 * Product analytics in the PWA (ADR-0007, infra ADR-0041), through
 * `@viktorbarzin/telemetry/browser`.
 *
 * On the production host the package adds Rybbit's script from the Ingest
 * path `/_t/r/` (pageviews and session replay, password fields masked) and a
 * Segment client that sends this app's own events to `/_t/e/`. Anywhere else
 * (localhost, a preview) it loads and sends nothing. `app.html` carries
 * `<meta name="analytics" content="sdk">`, which tells the edge injection
 * plugin that this app loads the script itself.
 *
 * The layout calls `startTelemetry` on every app start with what `GET /api/me`
 * answered: the Write key and release while the server has events on, and the
 * signed-in Person (their Authentik `uid`), whom the package identifies on
 * every start. The settings are remembered, so a start the API does not answer
 * (offline, or the SSO wall in front of the installed PWA) still records, and
 * the SSO wall resets the Person. `visitorHeaders` puts the script's visitor id
 * on every API call, so the backend's events join the same Rybbit user.
 *
 * Browser events are for what only the device sees. The server already sends
 * `capture.*` and `download.started`; nothing here repeats them.
 */
import { initTelemetry, reset, track, visitorHeaders } from '@viktorbarzin/telemetry/browser';

import type { BrowserTelemetry, Me } from './types';

export { visitorHeaders };

/** Hosts whose visits count. Anything else (localhost, a preview) loads nothing. */
export const PRODUCTION_HOSTS: readonly string[] = Object.freeze([
	'offline-reader.viktorbarzin.me'
]);

/** The Analytics site first-party apps are recorded under (`apps`). */
export const SITE_ID = 1;

/** localStorage key holding the settings from the last answer that carried them. */
export const SETTINGS_KEY = 'offline-reader:telemetry';

/** How `GET /api/me` went at this start. */
export type MeAnswer = { me: Me } | { signedOut: true } | { offline: true };

type SettingsStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function remembered(storage: SettingsStorage | undefined): BrowserTelemetry | null {
	try {
		const raw = storage?.getItem(SETTINGS_KEY);
		if (!raw) return null;
		const value: unknown = JSON.parse(raw);
		if (typeof value !== 'object' || value === null) return null;
		const { write_key, release } = value as Record<string, unknown>;
		return typeof write_key === 'string' && typeof release === 'string'
			? { write_key, release }
			: null;
	} catch {
		return null;
	}
}

function remember(storage: SettingsStorage | undefined, settings: BrowserTelemetry | null): void {
	try {
		if (settings) storage?.setItem(SETTINGS_KEY, JSON.stringify(settings));
		else storage?.removeItem(SETTINGS_KEY);
	} catch {
		// Storage blocked: this start still records, the next unanswered one cannot.
	}
}

/**
 * Start telemetry for this page from `GET /api/me`'s answer. True when started.
 * A live answer is the truth: no settings in it means the server has events off.
 */
export function startTelemetry(
	answer: MeAnswer,
	storage: SettingsStorage | undefined = globalThis.localStorage
): boolean {
	const me = 'me' in answer ? answer.me : null;
	if (me) remember(storage, me.telemetry);
	const settings = me ? me.telemetry : remembered(storage);
	if (!settings) return false;
	initTelemetry({
		writeKey: settings.write_key,
		siteId: SITE_ID,
		release: settings.release,
		productionHosts: PRODUCTION_HOSTS,
		personId: me?.person_id ?? undefined
	});
	if ('signedOut' in answer || (me && !me.person_id)) reset();
	return true;
}

export const DOWNLOAD_COMPLETED = 'download.completed';
export const DOWNLOAD_INTERRUPTED = 'download.interrupted';
export const PAGE_READ = 'page.read';

/** Every event the PWA sends, for the ADR and the tests. */
export const EVENTS: readonly string[] = [DOWNLOAD_COMPLETED, DOWNLOAD_INTERRUPTED, PAGE_READ];

/** Every Page of a Capture is on the device. */
export function downloadCompleted(properties: {
	page_count: number;
	/** Bytes fetched by this run; pages already stored add nothing. */
	bytes_fetched: number;
	/** Some Pages were already on the device from an earlier, interrupted run. */
	resumed: boolean;
	duration_ms: number;
}): void {
	track(DOWNLOAD_COMPLETED, properties);
}

/** A Download stopped before every Page was stored; the next tap resumes it. */
export function downloadInterrupted(properties: {
	pages_done: number;
	page_count: number;
	reason: 'auth' | 'network';
}): void {
	track(DOWNLOAD_INTERRUPTED, properties);
}

/** The Reader showed a Page from the device, with or without a network. */
export function pageRead(properties: { online: boolean }): void {
	track(PAGE_READ, properties);
}

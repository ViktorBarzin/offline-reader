import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
	PRODUCTION_HOSTS,
	clearPerson,
	identifyPerson,
	isProductionHost,
	loadAnalytics,
	resetAnalytics,
	type AnalyticsDocument,
	type AnalyticsWindow,
	type ScriptElement
} from './analytics';

interface FakeScript extends ScriptElement {
	attributes: Record<string, string>;
	listeners: Record<string, () => void>;
}

/** A document stand-in that records the script elements appended to head. */
function fakeDocument(): AnalyticsDocument<FakeScript> & { appended: FakeScript[] } {
	const appended: FakeScript[] = [];
	return {
		appended,
		head: { appendChild: (el: FakeScript) => appended.push(el) },
		createElement: () => {
			const el: FakeScript = {
				attributes: {},
				listeners: {},
				setAttribute(name, value) {
					el.attributes[name] = value;
				},
				addEventListener(event, listener) {
					el.listeners[event] = listener;
				}
			};
			return el;
		}
	};
}

/** The one script the page was given. */
function onlyScript(doc: { appended: FakeScript[] }): FakeScript {
	expect(doc.appended).toHaveLength(1);
	const [script] = doc.appended;
	if (!script) throw new Error('no script added');
	return script;
}

/** The script finished loading. */
function fireLoad(doc: { appended: FakeScript[] }): void {
	const listener = onlyScript(doc).listeners.load;
	if (!listener) throw new Error('no load listener');
	listener();
}

function fakeRybbit() {
	return { identify: vi.fn(), clearUserId: vi.fn() };
}

const HOST = 'offline-reader.viktorbarzin.me';

beforeEach(() => resetAnalytics());

describe('isProductionHost', () => {
	it('is the offline-reader host only', () => {
		expect(PRODUCTION_HOSTS).toEqual([HOST]);
		expect(isProductionHost(HOST)).toBe(true);
		expect(isProductionHost('localhost')).toBe(false);
		expect(isProductionHost(`${HOST}.evil.test`)).toBe(false);
	});
});

describe('loadAnalytics', () => {
	it('adds the Rybbit script on the production host', () => {
		const doc = fakeDocument();
		expect(loadAnalytics(doc, HOST, {})).toBe(true);
		const script = onlyScript(doc);
		expect(script.src).toBe('/_t/r/script.js');
		expect(script.defer).toBe(true);
		expect(script.attributes).toEqual({
			'data-site-id': '1',
			'data-replay-mask-all-inputs': 'false',
			'data-replay-mask-input-options': '{"password":true}'
		});
	});

	it('adds nothing anywhere else', () => {
		const doc = fakeDocument();
		expect(loadAnalytics(doc, 'localhost', {})).toBe(false);
		expect(doc.appended).toEqual([]);
	});

	it('adds it once per page', () => {
		const doc = fakeDocument();
		loadAnalytics(doc, HOST, {});
		loadAnalytics(doc, HOST, {});
		expect(doc.appended).toHaveLength(1);
	});
});

describe('identifyPerson', () => {
	it('names the Person once the script is there', () => {
		const rybbit = fakeRybbit();
		identifyPerson('uid-1', { rybbit });
		expect(rybbit.identify).toHaveBeenCalledWith('uid-1');
	});

	it('waits for the script when it has not loaded yet', () => {
		const doc = fakeDocument();
		const win: AnalyticsWindow = {};
		loadAnalytics(doc, HOST, win);
		identifyPerson('uid-1', win);
		const rybbit = fakeRybbit();
		win.rybbit = rybbit;
		fireLoad(doc);
		expect(rybbit.identify).toHaveBeenCalledWith('uid-1');
	});

	it('does nothing without an id', () => {
		const rybbit = fakeRybbit();
		identifyPerson(null, { rybbit });
		expect(rybbit.identify).not.toHaveBeenCalled();
	});

	it('does not name the same Person twice', () => {
		const rybbit = fakeRybbit();
		identifyPerson('uid-1', { rybbit });
		identifyPerson('uid-1', { rybbit });
		expect(rybbit.identify).toHaveBeenCalledTimes(1);
	});
});

describe('clearPerson', () => {
	it('forgets a Person who was named', () => {
		const rybbit = fakeRybbit();
		identifyPerson('uid-1', { rybbit });
		clearPerson({ rybbit });
		expect(rybbit.clearUserId).toHaveBeenCalledTimes(1);
	});

	it('leaves an anonymous visitor alone', () => {
		const rybbit = fakeRybbit();
		clearPerson({ rybbit });
		expect(rybbit.clearUserId).not.toHaveBeenCalled();
	});

	it('cancels a pending identify', () => {
		const doc = fakeDocument();
		const win: AnalyticsWindow = {};
		loadAnalytics(doc, HOST, win);
		identifyPerson('uid-1', win);
		clearPerson(win);
		const rybbit = fakeRybbit();
		win.rybbit = rybbit;
		fireLoad(doc);
		expect(rybbit.identify).not.toHaveBeenCalled();
	});
});

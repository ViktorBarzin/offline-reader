import { beforeEach, describe, expect, it, vi } from 'vitest';

const telemetry = vi.hoisted(() => ({
	initTelemetry: vi.fn(),
	reset: vi.fn(),
	track: vi.fn(),
	visitorHeaders: vi.fn(() => ({}))
}));
vi.mock('@viktorbarzin/telemetry/browser', () => telemetry);

import { checkEvent } from '@viktorbarzin/telemetry';

import {
	EVENTS,
	PRODUCTION_HOSTS,
	SETTINGS_KEY,
	SITE_ID,
	downloadCompleted,
	downloadInterrupted,
	pageRead,
	startTelemetry
} from './analytics';
import type { Me } from './types';

const SETTINGS = { write_key: 'wk-1', release: '0.1.0' };
const PERSON = 'uid-1';

function memoryStorage(initial: Record<string, string> = {}) {
	const items = new Map(Object.entries(initial));
	return {
		getItem: (key: string) => items.get(key) ?? null,
		setItem: (key: string, value: string) => void items.set(key, value),
		removeItem: (key: string) => void items.delete(key),
		items
	};
}

function me(overrides: Partial<Me> = {}): Me {
	return { username: 'viktor', person_id: PERSON, telemetry: SETTINGS, ...overrides };
}

beforeEach(() => vi.clearAllMocks());

describe('startTelemetry', () => {
	it('starts the package with the signed-in Person from /api/me', () => {
		expect(startTelemetry({ me: me() }, memoryStorage())).toBe(true);
		expect(telemetry.initTelemetry).toHaveBeenCalledWith({
			writeKey: 'wk-1',
			siteId: SITE_ID,
			release: '0.1.0',
			productionHosts: PRODUCTION_HOSTS,
			personId: PERSON
		});
		expect(telemetry.reset).not.toHaveBeenCalled();
	});

	it('counts the offline-reader host only', () => {
		expect(PRODUCTION_HOSTS).toEqual(['offline-reader.viktorbarzin.me']);
		expect(SITE_ID).toBe(1);
	});

	it('remembers the settings for a start without an answer', () => {
		const storage = memoryStorage();
		startTelemetry({ me: me() }, storage);
		vi.clearAllMocks();

		expect(startTelemetry({ offline: true }, storage)).toBe(true);
		expect(telemetry.initTelemetry).toHaveBeenCalledWith(
			expect.objectContaining({ writeKey: 'wk-1', personId: undefined })
		);
		expect(telemetry.reset).not.toHaveBeenCalled();
	});

	it('forgets the Person when the SSO session has gone', () => {
		const storage = memoryStorage({ [SETTINGS_KEY]: JSON.stringify(SETTINGS) });
		expect(startTelemetry({ signedOut: true }, storage)).toBe(true);
		expect(telemetry.reset).toHaveBeenCalledTimes(1);
	});

	it('forgets the Person when /api/me names nobody', () => {
		startTelemetry({ me: me({ person_id: null }) }, memoryStorage());
		expect(telemetry.reset).toHaveBeenCalledTimes(1);
	});

	it('starts nothing, and forgets the settings, while the server has events off', () => {
		const storage = memoryStorage({ [SETTINGS_KEY]: JSON.stringify(SETTINGS) });
		expect(startTelemetry({ me: me({ telemetry: null }) }, storage)).toBe(false);
		expect(telemetry.initTelemetry).not.toHaveBeenCalled();
		expect(storage.items.has(SETTINGS_KEY)).toBe(false);
	});

	it('starts nothing before any answer has carried settings', () => {
		expect(startTelemetry({ offline: true }, memoryStorage())).toBe(false);
		expect(startTelemetry({ signedOut: true }, memoryStorage())).toBe(false);
		expect(telemetry.initTelemetry).not.toHaveBeenCalled();
	});

	it('ignores remembered settings it cannot read', () => {
		const storage = memoryStorage({ [SETTINGS_KEY]: '{"write_key": 4}' });
		expect(startTelemetry({ offline: true }, storage)).toBe(false);
	});

	it('still starts where storage is blocked', () => {
		const blocked = {
			getItem: (): string | null => {
				throw new Error('SecurityError');
			},
			setItem: (): void => {
				throw new Error('SecurityError');
			},
			removeItem: (): void => {
				throw new Error('SecurityError');
			}
		};
		expect(startTelemetry({ me: me() }, blocked)).toBe(true);
		expect(startTelemetry({ offline: true }, blocked)).toBe(false);
	});
});

describe('browser events', () => {
	it('meet the naming standard and never repeat a server event', () => {
		const server = [
			'capture.requested',
			'capture.completed',
			'capture.failed',
			'capture.refreshed',
			'capture.deleted',
			'download.started'
		];
		for (const name of EVENTS) {
			expect(checkEvent(name).problems).toEqual([]);
			expect(server).not.toContain(name);
		}
	});

	it('send what the device saw', () => {
		downloadCompleted({ page_count: 12, bytes_fetched: 3400, resumed: true, duration_ms: 900 });
		downloadInterrupted({ pages_done: 3, page_count: 12, reason: 'network' });
		pageRead({ online: false });
		expect(telemetry.track.mock.calls).toEqual([
			[
				'download.completed',
				{ page_count: 12, bytes_fetched: 3400, resumed: true, duration_ms: 900 }
			],
			['download.interrupted', { pages_done: 3, page_count: 12, reason: 'network' }],
			['page.read', { online: false }]
		]);
	});
});

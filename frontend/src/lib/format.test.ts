import { describe, expect, it } from 'vitest';

import { formatBytes } from './format';

describe('formatBytes', () => {
	it('handles zero and non-finite as 0 B', () => {
		expect(formatBytes(0)).toBe('0 B');
		expect(formatBytes(-5)).toBe('0 B');
		expect(formatBytes(NaN)).toBe('0 B');
	});

	it('formats plain bytes with no decimals', () => {
		expect(formatBytes(512)).toBe('512 B');
	});

	it('scales into KB / MB / GB with one decimal', () => {
		expect(formatBytes(1536)).toBe('1.5 KB');
		expect(formatBytes(5 * 1024 * 1024)).toBe('5 MB');
		expect(formatBytes(2.5 * 1024 * 1024 * 1024)).toBe('2.5 GB');
	});
});

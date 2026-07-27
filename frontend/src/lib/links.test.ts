// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';

import { normalizeUrl, rewriteLinks, type RewritePage } from './links';

const PAGES: RewritePage[] = [
	{ id: 'p1', url: 'https://docs.test/guide/intro' },
	{ id: 'p2', url: 'https://docs.test/guide/setup/' }, // trailing slash
	{ id: 'p3', url: 'https://docs.test/guide/api?v=2' } // query
];

const OPTS = {
	cid: 'c1',
	pages: PAGES,
	pageUrl: 'https://docs.test/guide/intro',
	appOrigin: 'https://reader.example'
};

/** Parse rewritten HTML back to a document so we can assert on attributes. */
function parse(html: string): Document {
	return new DOMParser().parseFromString(html, 'text/html');
}

describe('normalizeUrl', () => {
	it('ignores scheme, lowercases host, drops trailing slash + fragment, keeps query', () => {
		expect(normalizeUrl('https://Docs.Test/guide/setup/')).toBe('docs.test/guide/setup');
		expect(normalizeUrl('http://docs.test/guide/setup')).toBe('docs.test/guide/setup');
		expect(normalizeUrl('https://docs.test/guide/api?v=2#top')).toBe('docs.test/guide/api?v=2');
	});

	it('resolves relative against a base', () => {
		// From /guide/intro (dir /guide/): "./api?v=2" → /guide/api, "../x" → /x.
		expect(normalizeUrl('./api?v=2', 'https://docs.test/guide/intro')).toBe('docs.test/guide/api?v=2');
		expect(normalizeUrl('../top', 'https://docs.test/guide/intro')).toBe('docs.test/top');
	});

	it('returns null for non-http(s) schemes', () => {
		expect(normalizeUrl('mailto:a@b.test')).toBeNull();
		expect(normalizeUrl('javascript:void(0)')).toBeNull();
		expect(normalizeUrl('data:text/plain,hi')).toBeNull();
		expect(normalizeUrl('not a url')).toBeNull();
	});
});

describe('rewriteLinks — captured (internal) links', () => {
	it('rewrites an absolute link to a captured page into an app reader route with target=_top', () => {
		const html = '<a href="https://docs.test/guide/api?v=2">API</a>';
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('https://reader.example/read/c1/p3');
		expect(a.getAttribute('target')).toBe('_top');
		expect(a.getAttribute('data-internal')).toBe('true');
	});

	it('resolves a RELATIVE link against the page URL before matching', () => {
		const html = '<a href="setup/">Setup</a>'; // relative to /guide/intro → /guide/setup/
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('https://reader.example/read/c1/p2');
		expect(a.getAttribute('target')).toBe('_top');
	});

	it('matches regardless of trailing slash / scheme differences', () => {
		const html = '<a href="http://docs.test/guide/setup">Setup</a>'; // http, no slash
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('https://reader.example/read/c1/p2');
	});

	it('with an empty appOrigin yields a root-relative route (test/default)', () => {
		const html = '<a href="https://docs.test/guide/intro">Home</a>';
		const a = parse(rewriteLinks(html, { ...OPTS, appOrigin: '' })).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('/read/c1/p1');
	});
});

describe('rewriteLinks — external / other links', () => {
	it('sends an un-captured http link to a new tab, absolutized', () => {
		const html = '<a href="/other/page">Other</a>'; // same host, NOT in manifest
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('https://docs.test/other/page');
		expect(a.getAttribute('target')).toBe('_blank');
		expect(a.getAttribute('rel')).toBe('noopener noreferrer');
		expect(a.getAttribute('data-external')).toBe('true');
	});

	it('absolutizes an off-site link and opens it in a new tab', () => {
		const html = '<a href="https://elsewhere.test/x">Away</a>';
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.getAttribute('href')).toBe('https://elsewhere.test/x');
		expect(a.getAttribute('data-external')).toBe('true');
	});

	it('neutralizes javascript: links', () => {
		const html = '<a href="javascript:alert(1)">x</a>';
		const a = parse(rewriteLinks(html, OPTS)).querySelector('a')!;
		expect(a.hasAttribute('href')).toBe(false);
		expect(a.getAttribute('data-stripped')).toBe('js');
	});

	it('leaves mailto:, tel: and pure #fragment links untouched', () => {
		const doc = parse(
			rewriteLinks(
				'<a id="m" href="mailto:a@b.test">mail</a><a id="t" href="tel:+123">call</a><a id="f" href="#section">jump</a>',
				OPTS
			)
		);
		expect(doc.querySelector('#m')!.getAttribute('href')).toBe('mailto:a@b.test');
		expect(doc.querySelector('#m')!.hasAttribute('target')).toBe(false);
		expect(doc.querySelector('#t')!.getAttribute('href')).toBe('tel:+123');
		expect(doc.querySelector('#f')!.getAttribute('href')).toBe('#section');
	});

	it('returns a full HTML document, preserving non-anchor markup', () => {
		const html = '<h1>Title</h1><img src="data:image/png;base64,AAAA"><a href="https://docs.test/guide/api?v=2">x</a>';
		const out = rewriteLinks(html, OPTS);
		expect(out.startsWith('<!doctype html>')).toBe(true);
		const doc = parse(out);
		expect(doc.querySelector('h1')!.textContent).toBe('Title');
		expect(doc.querySelector('img')!.getAttribute('src')).toBe('data:image/png;base64,AAAA');
	});
});

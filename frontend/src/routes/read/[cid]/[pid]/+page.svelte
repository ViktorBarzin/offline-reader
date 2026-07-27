<script lang="ts">
	/**
	 * The Reader (`/read/{cid}/{pid}`). Reads ONLY from IndexedDB, so it works with
	 * the network cut. A TOC (built from the capture's manifest) is the primary
	 * navigation and does fast client-side routing; the current page is rendered in
	 * a sandboxed `<iframe srcdoc>` WITHOUT `allow-scripts` (scripts are stripped
	 * server-side; a script-less frame is the security boundary — ADR-0006).
	 *
	 * The iframe is granted only `allow-top-navigation-by-user-activation` (so a
	 * rewritten inter-page link can navigate the top window to another reader route)
	 * and `allow-popups`/`allow-popups-to-escape-sandbox` (so an un-captured link can
	 * open online in a real new tab). See `$lib/links` for the rewriting rationale.
	 */
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import * as db from '$lib/db';
	import { rewriteLinks } from '$lib/links';
	import type { StoredCapture } from '$lib/types';

	// Non-scripting sandbox: no allow-scripts, no allow-same-origin.
	const SANDBOX = 'allow-top-navigation-by-user-activation allow-popups allow-popups-to-escape-sandbox';

	let capture = $state<StoredCapture | null | undefined>(undefined); // undefined=loading, null=missing
	let srcdoc = $state('');
	let renderError = $state('');
	let tocOpen = $state(false);

	const cid = $derived($page.params.cid ?? '');
	const pid = $derived($page.params.pid ?? '');

	const currentIndex = $derived(capture ? capture.pages.findIndex((p) => p.id === pid) : -1);
	const currentPage = $derived(currentIndex >= 0 ? capture!.pages[currentIndex] : undefined);
	const prevPage = $derived(currentIndex > 0 ? capture!.pages[currentIndex - 1] : undefined);
	const nextPage = $derived(
		capture && currentIndex >= 0 && currentIndex < capture.pages.length - 1
			? capture.pages[currentIndex + 1]
			: undefined
	);

	// Load the capture whenever the cid changes.
	$effect(() => {
		const id = cid;
		let cancelled = false;
		db.getCapture(id).then((c) => {
			if (!cancelled) capture = c ?? null;
		});
		return () => {
			cancelled = true;
		};
	});

	// Render the current page whenever the capture or pid changes.
	$effect(() => {
		const c = capture;
		const id = cid;
		const p = pid;
		if (c === undefined) return; // still loading the capture
		if (c === null) {
			srcdoc = '';
			return;
		}
		const pg = c.pages.find((x) => x.id === p);
		if (!pg) {
			srcdoc = '';
			renderError = 'This page isn’t part of the capture.';
			return;
		}
		let cancelled = false;
		db.getPageBytes(id, p).then((buf) => {
			if (cancelled) return;
			if (!buf) {
				renderError = 'This page isn’t downloaded on this device.';
				srcdoc = '';
				return;
			}
			renderError = '';
			const html = new TextDecoder().decode(new Uint8Array(buf));
			const appOrigin = browser ? location.origin : '';
			srcdoc = rewriteLinks(html, { cid: id, pages: c.pages, pageUrl: pg.url, appOrigin });
		});
		return () => {
			cancelled = true;
		};
	});

	async function navigate(targetPid: string): Promise<void> {
		tocOpen = false;
		await goto(`/read/${encodeURIComponent(cid)}/${encodeURIComponent(targetPid)}`);
	}
</script>

<div class="reader">
	<header class="reader-bar">
		<a class="bar-btn" href="/" aria-label="Back to Library">‹</a>
		<div class="bar-title">
			<p class="cap-title">{capture?.title ?? 'Reader'}</p>
			{#if currentPage}<p class="pg-title muted">{currentPage.title || currentPage.url}</p>{/if}
		</div>
		<button class="bar-btn" onclick={() => (tocOpen = !tocOpen)} aria-label="Table of contents">☰</button>
	</header>

	<div class="reader-body">
		<!-- TOC: sidebar on wide screens, drawer on mobile -->
		<nav class="toc" class:open={tocOpen} aria-label="Table of contents">
			<p class="eyebrow toc-head">
				Contents{#if capture}<span class="muted"> · {capture.pages.length}</span>{/if}
			</p>
			<ol class="toc-list">
				{#if capture}
					{#each capture.pages as p, i (p.id)}
						<li>
							<button class="toc-item" class:current={p.id === pid} onclick={() => navigate(p.id)}>
								<span class="toc-num">{i + 1}</span>
								<span class="toc-label">{p.title || p.url}</span>
							</button>
						</li>
					{/each}
				{/if}
			</ol>
		</nav>

		<!-- Scrim behind the mobile drawer -->
		{#if tocOpen}
			<button class="scrim" aria-label="Close contents" onclick={() => (tocOpen = false)}></button>
		{/if}

		<main class="page-area">
			{#if capture === undefined}
				<p class="empty"><span class="spinner"></span></p>
			{:else if capture === null}
				<div class="notice">
					<p>This capture isn’t on this device.</p>
					<a class="btn btn-accent" href="/">Go to Library</a>
				</div>
			{:else if renderError}
				<div class="notice"><p>{renderError}</p></div>
			{:else if srcdoc}
				<!-- Sandboxed, script-less: captured pages are self-contained (data: URIs)
				     so no allow-same-origin is needed; scripts are stripped + blocked. -->
				<iframe class="page-frame" title={currentPage?.title || 'Captured page'} sandbox={SANDBOX} srcdoc={srcdoc}
				></iframe>
			{/if}
		</main>
	</div>

	{#if capture}
		<footer class="reader-nav">
			<button class="nav-btn" disabled={!prevPage} onclick={() => prevPage && navigate(prevPage.id)}>
				‹ Prev
			</button>
			<span class="nav-pos muted">
				{currentIndex >= 0 ? currentIndex + 1 : '–'} / {capture.pages.length}
			</span>
			<button class="nav-btn" disabled={!nextPage} onclick={() => nextPage && navigate(nextPage.id)}>
				Next ›
			</button>
		</footer>
	{/if}
</div>

<style>
	.reader {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
	}

	.reader-bar {
		flex: none;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: calc(env(safe-area-inset-top) + 8px) 12px 8px;
		border-bottom: 0.5px solid var(--hairline);
		background: var(--card);
	}

	.bar-btn {
		flex: none;
		width: 40px;
		height: 40px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 22px;
		color: var(--accent);
		border-radius: 10px;
	}

	.bar-title {
		flex: 1;
		min-width: 0;
		text-align: center;
	}

	.cap-title {
		margin: 0;
		font-size: 15px;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.pg-title {
		margin: 0;
		font-size: 12px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.reader-body {
		flex: 1;
		min-height: 0;
		display: flex;
		position: relative;
	}

	.toc {
		flex: none;
		width: 280px;
		overflow-y: auto;
		border-right: 0.5px solid var(--hairline);
		background: var(--card);
		padding: 12px 8px 24px;
	}

	.toc-head {
		margin: 4px 0 8px 8px;
	}

	.toc-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.toc-item {
		display: flex;
		gap: 10px;
		width: 100%;
		text-align: left;
		padding: 9px 8px;
		border-radius: 8px;
		font-size: 14px;
		line-height: 1.3;
		color: var(--fg);
	}

	.toc-item.current {
		background: color-mix(in srgb, var(--accent) 14%, transparent);
		color: var(--accent);
		font-weight: 600;
	}

	.toc-num {
		flex: none;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
		min-width: 20px;
		text-align: right;
	}

	.toc-item.current .toc-num {
		color: var(--accent);
	}

	.toc-label {
		overflow-wrap: anywhere;
	}

	.page-area {
		flex: 1;
		min-width: 0;
		display: flex;
		background: #fff;
	}

	.page-frame {
		flex: 1;
		width: 100%;
		height: 100%;
		border: none;
		background: #fff;
	}

	.notice {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 14px;
		padding: 24px;
		text-align: center;
		color: var(--muted);
	}

	.scrim {
		display: none;
	}

	.reader-nav {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 8px 16px calc(env(safe-area-inset-bottom) + 8px);
		border-top: 0.5px solid var(--hairline);
		background: var(--card);
	}

	.nav-btn {
		padding: 8px 16px;
		border-radius: 10px;
		background: var(--field);
		font-size: 15px;
		font-weight: 600;
	}

	.nav-pos {
		font-size: 14px;
		font-variant-numeric: tabular-nums;
	}

	/* Mobile: the TOC becomes a slide-in drawer. */
	@media (max-width: 720px) {
		.toc {
			position: absolute;
			inset: 0 auto 0 0;
			z-index: 20;
			width: min(80vw, 320px);
			transform: translateX(-100%);
			transition: transform 0.22s ease;
			box-shadow: 2px 0 24px rgba(0, 0, 0, 0.25);
		}

		.toc.open {
			transform: translateX(0);
		}

		.scrim {
			display: block;
			position: absolute;
			inset: 0;
			z-index: 10;
			background: var(--sheet-scrim);
			border-radius: 0;
		}
	}
</style>

<script lang="ts">
	/**
	 * Library — the home screen. Lists Captures (merging the server list with any
	 * already-Downloaded captures from IndexedDB, so it still shows something
	 * offline), submits new capture jobs, polls in-flight ones, and offers
	 * Download / Read / Refresh / Delete per row.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';

	import { api, AuthWallError } from '$lib/api';
	import * as db from '$lib/db';
	import { downloadCapture, type DownloadProgress } from '$lib/download';
	import { formatBytes } from '$lib/format';
	import { online } from '$lib/net';
	import type { Capture, CreateCaptureBody, ScopeType, StoredCapture } from '$lib/types';

	// --- Submit form ---
	let url = $state('');
	let scope = $state<ScopeType>('prefix');
	let maxPages = $state('');
	let showAdvanced = $state(false);
	let include = $state('');
	let exclude = $state('');
	let submitting = $state(false);
	let submitError = $state('');

	// --- Data ---
	let serverCaptures = $state<Capture[]>([]);
	let stored = $state<StoredCapture[]>([]);
	let storedCounts = $state<Record<string, number>>({});
	let usageBytes = $state(0);
	let loading = $state(true);
	let loadError = $state<'' | 'offline' | 'auth'>('');

	// --- Per-row download state ---
	let downloads = $state<Record<string, DownloadProgress>>({});
	let downloadErrors = $state<Record<string, string>>({});

	interface Row extends Capture {
		downloaded: boolean;
		storedPages: number;
	}

	const scopes: { value: ScopeType; label: string }[] = [
		{ value: 'page', label: 'This page only' },
		{ value: 'prefix', label: 'Path prefix (book / docs)' },
		{ value: 'host', label: 'Whole host' },
		{ value: 'domain', label: 'Whole domain' }
	];

	const rows = $derived.by<Row[]>(() => {
		const byId = new Map<string, Capture>();
		for (const c of serverCaptures) byId.set(c.id, c);
		// Downloaded captures the server didn't return (offline, or server-pruned)
		// still belong in the list so they stay readable.
		for (const s of stored) if (!byId.has(s.id)) byId.set(s.id, s);
		const storedSet = new Set(stored.map((s) => s.id));
		return [...byId.values()]
			.map((c) => ({ ...c, downloaded: storedSet.has(c.id), storedPages: storedCounts[c.id] ?? 0 }))
			.sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
	});

	const hasPending = $derived(rows.some((r) => r.status === 'queued' || r.status === 'crawling'));

	async function refreshStored(): Promise<void> {
		stored = await db.getAllCaptures();
		const counts: Record<string, number> = {};
		for (const s of stored) counts[s.id] = await db.pageCountFor(s.id);
		storedCounts = counts;
		usageBytes = await db.storedBytes();
	}

	async function refreshServer(): Promise<void> {
		try {
			serverCaptures = await api.listCaptures();
			loadError = '';
		} catch (e) {
			loadError = e instanceof AuthWallError ? 'auth' : 'offline';
		}
	}

	let poll: ReturnType<typeof setInterval> | undefined;

	onMount(async () => {
		await refreshStored();
		await refreshServer();
		loading = false;
		poll = setInterval(async () => {
			if (typeof navigator !== 'undefined' && !navigator.onLine) return;
			const ids = rows.filter((r) => r.status === 'queued' || r.status === 'crawling').map((r) => r.id);
			for (const id of ids) {
				try {
					const c = await api.getCapture(id);
					serverCaptures = serverCaptures.map((x) => (x.id === id ? c : x));
				} catch {
					/* transient; try again next tick */
				}
			}
		}, 4000);
	});

	onDestroy(() => clearInterval(poll));

	async function submit(event: SubmitEvent): Promise<void> {
		event.preventDefault();
		const u = url.trim();
		if (!u || submitting) return;
		submitting = true;
		submitError = '';
		try {
			const body: CreateCaptureBody = { url: u, scope_type: scope };
			const mp = Number.parseInt(maxPages, 10);
			if (Number.isFinite(mp) && mp > 0) body.max_pages = mp;
			if (showAdvanced) {
				if (include.trim()) body.include = include.trim();
				if (exclude.trim()) body.exclude = exclude.trim();
			}
			const created = await api.createCapture(body);
			serverCaptures = [created, ...serverCaptures.filter((c) => c.id !== created.id)];
			url = '';
			maxPages = '';
			include = '';
			exclude = '';
		} catch (e) {
			submitError =
				e instanceof AuthWallError
					? 'Session expired — reload the app to sign in.'
					: 'Could not submit — are you online?';
		} finally {
			submitting = false;
		}
	}

	async function download(c: Row): Promise<void> {
		downloadErrors = { ...downloadErrors, [c.id]: '' };
		downloads = { ...downloads, [c.id]: { done: 0, total: c.page_count || 0, bytes: 0 } };
		try {
			await downloadCapture(c, {
				onProgress: (p) => {
					downloads = { ...downloads, [c.id]: p };
				}
			});
		} catch (e) {
			downloadErrors = {
				...downloadErrors,
				[c.id]:
					e instanceof AuthWallError ? 'Session expired' : 'Download interrupted — tap to resume'
			};
		} finally {
			const next = { ...downloads };
			delete next[c.id];
			downloads = next;
			await refreshStored();
		}
	}

	async function read(c: Row): Promise<void> {
		await goto(`/read/${encodeURIComponent(c.id)}`);
	}

	async function remove(c: Row): Promise<void> {
		if (
			typeof window !== 'undefined' &&
			!window.confirm(`Delete "${c.title || c.root_url}"? Removes it from the server and this device.`)
		)
			return;
		await db.deleteCapture(c.id);
		if (typeof navigator === 'undefined' || navigator.onLine) {
			try {
				await api.deleteCapture(c.id);
				serverCaptures = serverCaptures.filter((x) => x.id !== c.id);
			} catch {
				/* offline / already gone — local copy is removed regardless */
			}
		}
		await refreshStored();
	}

	async function refresh(c: Row): Promise<void> {
		try {
			// The contract doesn't pin the /refresh response shape: it may return the
			// updated Capture, or 204. Use it if it has an id; otherwise re-fetch so
			// the row reflects the new (queued/crawling) status either way.
			const updated = await api.refreshCapture(c.id);
			const fresh = updated && updated.id ? updated : await api.getCapture(c.id);
			serverCaptures = serverCaptures.map((x) => (x.id === c.id ? fresh : x));
		} catch {
			/* ignore; polling / next load reconciles */
		}
	}

	function statusLabel(r: Row): string {
		if (r.status === 'queued') return 'Queued';
		if (r.status === 'crawling') return 'Crawling…';
		if (r.status === 'failed') return 'Failed';
		return 'Ready';
	}
</script>

<div class="screen">
	<div class="screen-inner">
		<div class="navbar">
			<h1 class="title">Offline Reader</h1>
			{#if usageBytes > 0}
				<span class="usage muted">{formatBytes(usageBytes)} on device</span>
			{/if}
		</div>

		{#if !$online}
			<div class="inline-banner">Offline — showing captures already on this device.</div>
		{:else if loadError === 'auth'}
			<div class="inline-banner">Session expired — reload the app to sign in.</div>
		{:else if loadError === 'offline'}
			<div class="inline-banner">Can’t reach the server — showing downloaded captures only.</div>
		{/if}

		<!-- Submit a new capture -->
		<form class="card capture-form" onsubmit={submit}>
			<input
				class="field"
				type="url"
				inputmode="url"
				placeholder="https://example.com/docs/"
				bind:value={url}
				autocomplete="off"
				autocapitalize="none"
				spellcheck="false"
			/>
			<div class="form-row">
				<select class="field" bind:value={scope} aria-label="Capture scope">
					{#each scopes as s (s.value)}
						<option value={s.value}>{s.label}</option>
					{/each}
				</select>
				<input
					class="field max-pages"
					type="number"
					min="1"
					placeholder="max pages"
					bind:value={maxPages}
					aria-label="Maximum pages"
				/>
			</div>

			<button type="button" class="advanced-toggle" onclick={() => (showAdvanced = !showAdvanced)}>
				{showAdvanced ? '▾' : '▸'} Advanced (include / exclude)
			</button>
			{#if showAdvanced}
				<input class="field" placeholder="include regex (optional)" bind:value={include} />
				<input class="field" placeholder="exclude regex (optional)" bind:value={exclude} />
			{/if}

			{#if submitError}<p class="form-error">{submitError}</p>{/if}
			<button class="btn btn-accent submit" type="submit" disabled={submitting || !url.trim()}>
				{#if submitting}<span class="spinner"></span> Submitting…{:else}Capture site{/if}
			</button>
		</form>

		<!-- Library list -->
		{#if loading}
			<p class="empty"><span class="spinner"></span></p>
		{:else if rows.length === 0}
			<p class="empty">No captures yet. Paste a URL above to save a site for offline reading.</p>
		{:else}
			<p class="eyebrow list-head">Library</p>
			<div class="card hairline-rows">
				{#each rows as r (r.id)}
					{@const prog = downloads[r.id]}
					<div class="row">
						<div class="row-main">
							<p class="row-title">{r.title || r.root_url}</p>
							<p class="row-sub muted">
								<span class="badge badge-{r.status}">{statusLabel(r)}</span>
								{#if r.status === 'queued' || r.status === 'crawling'}
									<span class="spinner"></span>
								{/if}
								{#if r.page_count > 0}· {r.page_count} pages{/if}
								{#if r.size_bytes > 0}· {formatBytes(r.size_bytes)}{/if}
								{#if r.downloaded}· <span class="ondevice">on device</span>{/if}
							</p>
							{#if prog}
								<div class="progress" role="progressbar" aria-valuenow={prog.done} aria-valuemax={prog.total}>
									<div class="progress-bar" style:width="{prog.total ? (prog.done / prog.total) * 100 : 0}%"></div>
								</div>
								<p class="row-sub muted">Downloading {prog.done}/{prog.total} · {formatBytes(prog.bytes)}</p>
							{:else if downloadErrors[r.id]}
								<p class="row-sub err">{downloadErrors[r.id]}</p>
							{/if}
						</div>
						<div class="row-actions">
							{#if r.downloaded}
								<button class="link-accent" onclick={() => read(r)}>Read</button>
							{/if}
							{#if $online && r.status === 'done' && !prog}
								<button class="link-accent" onclick={() => download(r)}>
									{r.downloaded ? 'Update' : 'Download'}
								</button>
							{/if}
							{#if $online && r.status === 'done'}
								<button class="link-plain muted" onclick={() => refresh(r)}>Refresh</button>
							{/if}
							<button class="link-danger" onclick={() => remove(r)}>Delete</button>
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.usage {
		font-size: 13px;
	}

	.inline-banner {
		background: color-mix(in srgb, var(--orange) 16%, var(--card));
		color: var(--orange);
		border-radius: 12px;
		padding: 10px 14px;
		font-size: 14px;
		margin-bottom: 16px;
	}

	.capture-form {
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin-bottom: 24px;
	}

	.form-row {
		display: flex;
		gap: 10px;
	}

	.form-row .field {
		flex: 1;
	}

	.max-pages {
		max-width: 130px;
	}

	.advanced-toggle {
		align-self: flex-start;
		color: var(--muted);
		font-size: 14px;
	}

	.submit {
		margin-top: 2px;
	}

	.form-error {
		color: var(--danger);
		font-size: 14px;
		margin: 0;
	}

	.list-head {
		margin: 0 0 8px 4px;
	}

	.row {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 14px;
	}

	.row-main {
		flex: 1;
		min-width: 0;
	}

	.row-title {
		margin: 0 0 4px;
		font-size: 16px;
		font-weight: 600;
		overflow-wrap: anywhere;
	}

	.row-sub {
		margin: 0;
		font-size: 13px;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
	}

	.row-sub.err {
		color: var(--danger);
	}

	.ondevice {
		color: var(--green);
		font-weight: 600;
	}

	.badge {
		font-weight: 600;
	}
	.badge-done {
		color: var(--green);
	}
	.badge-queued,
	.badge-crawling {
		color: var(--orange);
	}
	.badge-failed {
		color: var(--danger);
	}

	.row-actions {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 10px;
		flex: none;
	}

	.row-actions button {
		font-size: 15px;
		font-weight: 600;
	}

	.link-plain {
		font-weight: 500;
	}

	.progress {
		height: 5px;
		border-radius: 3px;
		background: var(--field);
		overflow: hidden;
		margin: 8px 0 4px;
	}

	.progress-bar {
		height: 100%;
		background: var(--accent);
		transition: width 0.2s ease;
	}
</style>

<script lang="ts">
	/**
	 * `/read/{cid}` — entry point for a capture. Loads the capture from IndexedDB
	 * and redirects to its first page (`/read/{cid}/{firstPid}`), where the real
	 * Reader lives. If the capture isn't downloaded, points the user back to the
	 * Library.
	 */
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import * as db from '$lib/db';

	let state = $state<'loading' | 'missing'>('loading');

	onMount(async () => {
		const cid = $page.params.cid ?? '';
		const capture = await db.getCapture(cid);
		const first = capture?.pages[0];
		if (capture && first) {
			await goto(`/read/${encodeURIComponent(cid)}/${encodeURIComponent(first.id)}`, {
				replaceState: true
			});
		} else {
			state = 'missing';
		}
	});
</script>

<div class="screen">
	<div class="screen-inner">
		{#if state === 'loading'}
			<p class="empty"><span class="spinner"></span></p>
		{:else}
			<div class="navbar">
				<a class="link-accent" href="/">‹ Library</a>
			</div>
			<p class="empty">This capture isn’t downloaded on this device. Download it from the Library first.</p>
		{/if}
	</div>
</div>

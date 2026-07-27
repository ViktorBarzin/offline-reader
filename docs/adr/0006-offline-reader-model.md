# 0006 — Offline reader model: self-contained HTML in IndexedDB, sandboxed iframe

Status: accepted

Each Page is captured as a single self-contained HTML file — all CSS, images, and fonts
inlined as `data:` URIs, **scripts stripped** (single-file-cli default). The PWA Downloads a
Capture by fetching its manifest + all Page blobs (same-origin, SSO cookie carried) into
**IndexedDB**, then renders a Page in a **sandboxed `<iframe srcdoc>` without
`allow-scripts`**.

Stripping scripts is both a fidelity trade and a **security boundary**: captured pages are
untrusted third-party content, and a script-less sandboxed iframe cannot run their JS on our
origin. Layout, styling, and images are preserved; interactivity is not.

Whole-site reading is reconstructed by us: a **table of contents** built from the Crawl
manifest (discovered Pages + titles, ordered by URL / discovery), and **inter-page link
rewriting** — a link whose target is another captured Page loads it from IndexedDB; links to
un-captured URLs open online only when there is a network.

## iOS storage handling

- Prompt to **install to the home screen** and call `navigator.storage.persist()` (feature-
  checked) — together these exempt the origin from the 7-day ITP wipe and grant ~60%-of-disk
  quota, but Apple gives no absolute guarantee.
- The Download runs in the **foreground** (iOS has no Background Fetch), chunked and
  resumable; the UI shows per-Capture size + total used and marks an evicted Capture for
  re-download.
- The PWA **app shell** is precached with an injectManifest service worker (the tripit/tasks
  pattern) so the app opens with no network.

## Consequences

- The reader has no WASM decoder or replay engine — simple and fast.
- We own a link-rewriting + navigation layer and (later) a client-side search index.
- Storage durability on iOS is strong-but-not-guaranteed; the UX treats a Capture as
  re-downloadable, not sacred.

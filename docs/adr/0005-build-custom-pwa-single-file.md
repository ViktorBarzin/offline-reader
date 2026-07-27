# 0005 — Build a custom PWA with single-file-cli capture (supersedes ADR-0001)

Status: accepted

The user requires a Reader that **stores captures natively on the phone with no manual file
handling** — tap a Capture, it downloads into the app and is available offline. The adopted
Kiwix client (ADR-0001) cannot do this on iOS: `kiwix-js-pwa`'s auto-download-to-OPFS relies
on `FileSystemFileHandle.createWritable()`, absent on iOS 17/18 (it shipped only in Safari
26), and it cannot be pointed at our SSO'd server; the native Kiwix app needs the manual
Safari→Files→import flow the user rejected. So we **build a custom PWA** and drop the
adopt-Kiwix approach.

Within "build a PWA", the capture format was the fork:

- **single-file-cli** → one self-contained HTML per Page (assets inlined, scripts stripped)
  → stored in IndexedDB → rendered in a sandboxed iframe. No decoder, no replay engine.
- **zimit ZIM in the browser** → whole-site fidelity + full-text search for free, but a ZIM
  must be read with a vendored kiwix-js WASM reader **plus** the wabac.js replay engine that
  zimit ZIMs embed — the heaviest, most fragile build.

We chose **single-file-cli**: it matches the target content (books / docs / articles), fits
the existing SvelteKit + FastAPI + `idb` stack, and keeps the reader simple. A PWA (unlike
the native Kiwix app) runs in the browser, so a same-origin download carries the SSO cookie
automatically — in-app auto-download works behind the existing SSO wall (see ADR-0003).

## Consequences

- We build and maintain a PWA and own **iOS offline-storage correctness** (install +
  `navigator.storage.persist()` + byte budget; whole-origin eviction is possible under disk
  pressure — a real-device test on the largest Capture is required before relying on it
  mid-flight).
- Weaker capture fidelity on heavy-JS / SPA sites and video (scripts are stripped); fine for
  the intended reading material.
- Whole-site navigation + search are **not free** — we build a manifest-driven TOC + link
  rewriting (see [ADR-0006](0006-offline-reader-model.md)); client-side search is deferred
  from v1.

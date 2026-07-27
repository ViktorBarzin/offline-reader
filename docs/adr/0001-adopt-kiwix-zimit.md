# 0001 — Adopt Kiwix + zimit instead of building a bespoke offline-reader PWA

Status: superseded by [ADR-0005](0005-build-custom-pwa-single-file.md) (2026-07-27)

> **Superseded.** The user later required a Reader that stores captures natively on the
> phone with **no manual file handling** — which the Kiwix client cannot do on iOS. See
> ADR-0005. The analysis below (why Kiwix + zimit beat ArchiveBox / custom / reader-mode
> tools) remains accurate for the adopt-Kiwix _option_; it was outcompeted by the
> seamless-offline requirement, not by an error in this reasoning.

We need faithful, multi-page website capture that reads on a phone with **zero
network** (the plane use case). Research against primary sources found that
**Kiwix + zimit already delivers exactly this**: `zimit` runs a real headless-browser
crawl (Browsertrix → WARC → `warc2zim`) producing a faithful, multi-page archive, and
the **Kiwix** clients (iOS/Android/desktop/PWA) read a ZIM **100% offline on-device**.
All free, open-source, and self-hostable as Docker/K8s. We therefore adopt Kiwix+zimit
wholesale and build only a **thin trigger/glue**: submit URL → run a `zimit` job →
publish the resulting ZIM to a `kiwix-serve` catalog the phone downloads from.

## Considered and rejected

- **ArchiveBox** — best-in-class faithful capture, but **no offline-mobile story**: its
  web UI requires the server reachable, so we'd still have to build the entire PWA on
  top. (This reverses an earlier lean toward ArchiveBox as the capture engine.)
- **Fully custom SvelteKit PWA + capture backend** — maximal control and the exact
  crawl→select→read UX, but weeks of build, and we would own iOS offline-storage
  correctness ourselves (whole-origin eviction, `navigator.storage.persist()`, byte
  budgeting).
- **Reader-mode tools (Wallabag, Readeck)** — mature true-offline mobile apps, but they
  store only reader-mode text, failing the faithful-snapshot requirement (ADR relies on
  the fidelity decision).

## Consequences

- We give up **per-page tick-box selection** (replaced by zimit **Scope** patterns), a
  **bespoke Reader UI** (replaced by the Kiwix client), and **seamless in-app iOS sync**
  (replaced by catalog download / Files import).
- **Capture fidelity is site-dependent** — JS-heavy/SPA/login-walled sites capture
  imperfectly. This is inherent to any faithful approach, not specific to zimit.

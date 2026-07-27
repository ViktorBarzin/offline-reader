# Offline Reader

Self-hosted way to read whole websites offline (e.g. on a plane). Feed a URL to the
endpoint; the server crawls and faithfully preserves the site as self-contained HTML
pages; an installable PWA downloads chosen captures onto your phone and reads them with
no network — no manual file handling.

- **Backend** (`backend/`) — FastAPI. Captures = one Kubernetes Job per capture running
  the capture image (`single-file-cli`), pages + a manifest stored on an NFS PVC, metadata
  in SQLite. Serves the pages and the SvelteKit PWA same-origin.
- **Capture image** (`capture/`) — `single-file-cli` + Chromium; crawls a site within its
  path prefix into self-contained HTML pages (assets inlined, scripts stripped).
- **Frontend** (`frontend/`) — SvelteKit `adapter-static` PWA. Downloads a capture's pages
  into IndexedDB and renders them offline in a sandboxed iframe with a table of contents.

Design, glossary, and decisions: [`docs/offline-reader-design.md`](docs/offline-reader-design.md),
[`CONTEXT.md`](CONTEXT.md), [`docs/adr/`](docs/adr/). Published plan:
<https://pages.viktorbarzin.me/2026-07-27-offline-reader-design.html>.

## Run locally (no Docker, no cluster)

```sh
cd frontend && npm ci && npm run build          # build the PWA once
cd ../backend && poetry install
DATA_DIR=/tmp/or CAPTURE_MODE=fake FAKE_AUTO_COMPLETE=1 DEV_USER=viktor \
  poetry run uvicorn offline_reader_api.app:app --port 8000   # http://localhost:8000
```

`CAPTURE_MODE=fake` writes fixture pages so the whole flow works without a cluster;
`FAKE_AUTO_COMPLETE=1` makes a submitted capture finish immediately. In production
`CAPTURE_MODE=k8s` runs real `single-file-cli` Jobs.

## Gates

```sh
cd backend  && poetry run ruff check . && poetry run mypy offline_reader_api tests && poetry run pytest -q
cd frontend && npm run check && npm test && npm run build
```

## Deploy

GitHub Actions builds `ghcr.io/viktorbarzin/offline-reader` (app) and
`ghcr.io/viktorbarzin/offline-reader-capture` (capture image); Woodpecker rolls the app.
Infra stack: `infra/stacks/offline-reader/` (owner-only behind Authentik SSO).

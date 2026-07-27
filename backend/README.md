# offline-reader — backend (`offline_reader_api`)

FastAPI service that captures whole websites as sets of self-contained HTML
Pages and serves them (plus a manifest) to the offline PWA. One Capture = one
root URL crawled by a `single-file-cli` Kubernetes Job (one Job per Capture,
ADR-0002) into `captures/<id>/pages/*.html`, with metadata in SQLite on the
shared NFS PVC (ADR-0004). Identity is Authentik forward-auth
(`X-Authentik-Username`); the app is owner-only behind SSO.

## Layout on the PVC (`DATA_DIR`, default `/data`)

```
${DATA_DIR}/offline-reader.db                  SQLite (captures table)
${DATA_DIR}/captures/<cid>/pages/*.html        self-contained Pages (from the Job)
${DATA_DIR}/captures/<cid>/session.json        single-file-cli crawl session
${DATA_DIR}/captures/<cid>/manifest.json       built by the app after the crawl
```

## API (all under `/api`, every route SSO-authenticated)

| Method | Path | Purpose |
|--------|------|---------|
| POST   | `/api/captures` | Create a Capture and start its crawl. Body: `{url, scope_type="prefix", max_pages=1000, include=[], exclude=[]}`. `url` must be http(s); `scope_type ∈ {page,prefix,host,domain}`. |
| GET    | `/api/captures` | List Captures (newest first). |
| GET    | `/api/captures/{id}` | One Capture; refreshes status from the runner if still in flight. |
| DELETE | `/api/captures/{id}` | Delete the Capture's files and row. |
| POST   | `/api/captures/{id}/refresh` | Re-crawl and replace the Pages in place. |
| GET    | `/api/captures/{id}/manifest` | The `manifest.json` (404 until `done`). |
| GET    | `/api/captures/{id}/pages/{page_id}` | One Page as `text/html`. |
| GET    | `/healthz`, `/metrics` | Liveness + Prometheus. |

`page_id` is the manifest slug `sha1(url)[:12]`. Errors use the envelope
`{"error": {"code", "message"}}`.

## Capture runner

A `CaptureRunner` abstraction (`start` / `poll` / `cancel`) is selected by
`CAPTURE_MODE`:

- `fake` (default) — `FakeRunner`, no cluster: writes deterministic fixture
  Pages so the whole API works for local dev and tests.
- `k8s` — `K8sJobRunner`: creates one `single-file-cli` Job per Capture via the
  official Kubernetes client (`load_incluster_config`), mounting the PVC at
  `/data` and a `/dev/shm` in-memory `emptyDir` for Chrome.

Status advances on GET of a Capture; an optional background poller
(`CAPTURE_POLL_INTERVAL_SECONDS > 0`) advances in-flight Captures without a
client watching.

## Configuration (environment)

| Var | Default | Meaning |
|-----|---------|---------|
| `DATA_DIR` | `/data` | PVC mount holding the DB, Pages and manifests. |
| `OFFLINE_READER_DB_DSN` | `sqlite+aiosqlite:///${DATA_DIR}/offline-reader.db` | SQLAlchemy DSN. |
| `DEV_USER` | — | Dev-only identity fallback when the Authentik header is absent. |
| `CAPTURE_MODE` | `fake` | `fake` or `k8s`. |
| `CAPTURE_MAX_DEPTH` / `CAPTURE_WORKERS` / `CAPTURE_WAIT_MS` | `3` / `2` / `500` | Per-Job crawl tuning. |
| `CAPTURE_POLL_INTERVAL_SECONDS` | `0` | Background poller cadence (0 disables). |
| `POD_NAMESPACE` / `SINGLEFILE_IMAGE` / `NFS_PVC_CLAIM` | `offline-reader` / `ghcr.io/viktorbarzin/offline-reader-capture:latest` / `offline-reader` | K8sJobRunner Job settings. |

## Local run

```bash
DATA_DIR=/tmp/or CAPTURE_MODE=fake DEV_USER=viktor \
  poetry run uvicorn offline_reader_api.app:app --reload
```

Then `http://localhost:8000` (API docs at `/api/docs`).

## Development gate

```bash
poetry install
poetry run ruff check .
poetry run mypy offline_reader_api tests
poetry run pytest -q
```

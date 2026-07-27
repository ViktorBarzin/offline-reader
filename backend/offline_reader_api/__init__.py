"""offline-reader backend.

Captures whole websites as sets of self-contained HTML Pages (crawled by a
``single-file-cli`` Kubernetes Job, one Job per Capture — ADR-0002) and serves
them, plus a manifest, to the offline PWA. Capture metadata lives in SQLite on
the shared NFS PVC (ADR-0004). Identity is Authentik forward-auth
(``X-Authentik-Username``); the app is owner-only behind SSO.
"""

__version__ = "0.1.0"

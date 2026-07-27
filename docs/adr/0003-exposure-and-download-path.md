# 0003 — Public behind SSO; the PWA downloads captures in-app

Status: accepted (download path revised 2026-07-27, see [ADR-0005](0005-build-custom-pwa-single-file.md))

The service is exposed publicly at `offline-reader.viktorbarzin.me` behind the standard
owner-only wall (Traefik + Authentik forward-auth, `auth = "required"`, `allowed_groups`
defaulting to `["Home Server Admins"]`).

Because the Reader is a **PWA served from the same origin**, a download runs in the browser
context and **carries the Authentik SSO cookie automatically**. The PWA fetches a Capture's
Pages straight into on-device storage (IndexedDB) — in-app, no manual file handling. This is
the whole reason a PWA works here where the native Kiwix app did not: the native app's HTTP
client could not pass the SSO oauth redirect, whereas a same-origin PWA fetch is already
authenticated.

## Considered and rejected

- **LAN-only exposure (+ VPN)** — simplest auth and no public surface, but the owner chose
  public + SSO for consistency with the other `*.viktorbarzin.me` services.
- **(Historical) native Kiwix app + Safari→Files→import** — the original plan under ADR-0001;
  rejected because it required manual file handling (see ADR-0005).

## Consequences

- One SSO wall — nothing is reachable without Authentik auth, including the Page downloads.
- Replicate the `tasks` ingress NetworkPolicy (restrict pod ingress to the `traefik` +
  `monitoring` namespaces) so nothing in-cluster can bypass Authentik via the pod IP.

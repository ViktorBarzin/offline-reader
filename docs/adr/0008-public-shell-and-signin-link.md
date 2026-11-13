# 0008 — The app shell is public, and sign-in leaves the shell

Status: accepted 2026-11-13. Amends [ADR-0003](0003-exposure-and-download-path.md).

On 2026-11-13 Viktor's Authentik session expired, and the installed PWA showed "Session
expired — reload the app to sign in". There was no way to sign in from the app. The
service worker answers every in-scope navigation from its precache (ADR-0006), so a
reload never reached Traefik or Authentik. The worker could not update itself either:
its update check fetches `/service-worker.js`, and forward-auth bounced that request to
the login page. The tasks app had the same failure in August (tasks ADR-0003).

Two changes fix it:

1. **The banner has a "Sign in" link to `GET /api/signin`.** The worker sends every
   `/api/` navigation to the network, so the link reaches forward-auth, which sends the
   browser to Authentik. After sign-in, the route redirects to `/`. The route requires
   the identity header like every other `/api` route.
2. **The static app shell is public.** `/`, `/_app/*`, `/service-worker.js`, the manifest
   and the icons are served without forward-auth. `/api` and `/metrics` stay owner-only.
   A device on an old worker can now fetch the new worker and its precache while signed
   out, so it updates itself and keeps the captures in IndexedDB.

## Considered and rejected

- **Keep the shell gated and reinstall the app.** Removing the home-screen app wipes
  IndexedDB, and with it every downloaded capture.
- **All navigations network-first.** This breaks the offline cold start of ADR-0006.

## Consequences

- The built JavaScript and HTML are readable without sign-in. They hold no captures and
  no secrets. All capture data is still behind `/api`.
- The public ingress uses `strip-auth-headers`, so a forged `X-Authentik-*` header never
  reaches the backend through it.
- The Authentik walling-off probe in `infra` guards the public shell.

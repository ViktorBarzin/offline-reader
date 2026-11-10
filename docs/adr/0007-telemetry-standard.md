# 0007 Product events, logs and errors to the shared telemetry standard

Status: accepted (2026-11-09)

Viktor asked for one analytics pipeline across every app he hosts (infra ADR-0041, design
`infra/docs/plans/2026-11-09-product-analytics-design.md`). tv was the pilot; offline-reader
follows the same standard through the shared `viktorbarzin-telemetry` 0.1.0 library.

## Decision

1. Logs. Every backend line is one JSON object on stdout in the OpenTelemetry field names:
   `timestamp`, `severity_text`, `severity_number`, `body`, `logger.name`, `service.name`
   (`offline-reader`), `service.version`, `deployment.environment.name`, `enduser.id` while a
   request from a known Person is served, and `extra={...}` fields as snake_case attributes.
   This replaces the earlier `ts`/`level`/`logger`/`msg` lines on stderr. uvicorn's own
   loggers go through the same handler. The formatter masks `INGEST_TOKEN`, which the iOS
   Shortcut sends as `?token=` and uvicorn's access line would otherwise print.

2. The Person id is the Authentik hashed user id (`uid`). offline-reader has no OIDC provider
   of its own: the forward-auth that sets `X-Authentik-Username` also sets `X-Authentik-Uid`,
   and Traefik overwrites both on every gated route. `/api/ingest` sits outside the gate, so a
   uid sent to it is ignored. `GET /api/me` returns `username` and `person_id` for the PWA.

3. Product events go from the backend to the Event pipeline with the Write key, only when
   `TELEMETRY_WRITE_KEY` is set and `TELEMETRY_ENVIRONMENT=production`, to `TELEMETRY_HOST`.
   Each is sent where the thing happens:

   | Event | Sent from | Properties | Answers |
   |---|---|---|---|
   | `capture.requested` | `CaptureService.create`, from `POST /api/captures` or `/api/ingest` | `source` (`web`, `shortcut`), `scope_type`, `max_pages`, `site` | how often sites are saved, and from which door |
   | `capture.completed` | `CaptureService.advance`, when a crawl turns `done` | `scope_type`, `site`, `page_count`, `size_bytes` | how big Captures are, per Scope |
   | `capture.failed` | `CaptureService._start` (`stage` `start`) or `advance` (`stage` `crawl`) | `stage`, `scope_type`, `site` | how often a crawl fails, and where |
   | `capture.refreshed` | `CaptureService.refresh` | `scope_type`, `site`, `age_days` | whether saved sites are kept current |
   | `capture.deleted` | `CaptureService.delete` | `status`, `page_count`, `age_days` | how long Captures stay in the Library |
   | `download.started` | `GET /api/captures/{id}/manifest`, which the PWA fetches only to Download | `page_count`, `size_bytes`, `age_days` | whether Captures reach a device to be read offline |

   `site` is the captured site's host only. No property carries the URL's path or query, the
   page title or an error text, since any of them can hold a token. A Capture from the iOS
   Shortcut has no Person and carries the fixed anonymous id `ios-shortcut`.

4. Errors go to GlitchTip through Sentry, with `SENTRY_DSN` (the in-cluster form) in
   production only.

5. The PWA loads Rybbit's script from `/_t/r/script.js` on `offline-reader.viktorbarzin.me`
   only, with password fields masked in replay, and `app.html` carries
   `<meta name="analytics" content="sdk">` so the edge injection plugin skips it. After
   `GET /api/me` it calls `rybbit.identify(person_id)`; an SSO wall calls `clearUserId`.
   Browser custom events wait for `@viktorbarzin/telemetry` on npm.

## Consequences

- Tests and local runs send nothing: no Write key, and the environment is not `production`.
- `capture.completed` and `capture.failed` fire when a crawl's end is first observed, on a
  `GET /api/captures/{id}` from the PWA. If the background poller is turned on, the poller
  observes it instead and the event carries no Person.
- `service.version` is the package's `__version__`, which does not change per image.

## Open questions

- Whether `X-Authentik-Uid` stays equal to the OIDC `sub` other apps send. It does while those
  apps' providers keep Authentik's default `hashed_user_id` mode.

## Update 2026-11-10: one person per browser (telemetry 0.2.0)

`viktorbarzin-telemetry` 0.1.0 gave every backend event without an anonymousId a new random
id, so Rybbit counted each anonymous event as a new person. offline-reader moves to 0.2.0 and
`RequestContextMiddleware` (with the same `person_id` resolver) in place of
`EnduserMiddleware`: an event sent during a request carries the browser's Rybbit visitor id as
its anonymousId, the visitor's IP (`X-Real-Ip`) and User-Agent, so it lands on the browser's
Rybbit user with a country and a device. The PWA's API client sends that id as `X-Visitor-Id`
(localStorage `rybbit-visitor-id`, read per call) on every request, and the layout already
calls `rybbit.identify(person_id)` on every app start, not only after sign-in. Events outside a
request (the optional poller) carry the stable `server:offline-reader`; the iOS Shortcut keeps
`ios-shortcut`.

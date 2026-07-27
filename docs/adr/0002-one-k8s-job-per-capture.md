# 0002 — One Kubernetes Job per Capture, orchestrated by the app

Status: accepted

A Capture is a heavy but bounded headless-Chrome crawl (`single-file-cli` driving Chrome).
We run **each Capture as its own Kubernetes Job**, created at runtime by the FastAPI app.
The app holds a **namespaced** ServiceAccount + Role + RoleBinding (least privilege,
modelled on `infra/stacks/android-emulator/gate.tf`):

```
rule { api_groups=["batch"]; resources=["jobs"];            verbs=["create","get","list","watch","delete"] }
rule { api_groups=[""];      resources=["pods","pods/log"]; verbs=["get","list","watch"] }
```

Each Job runs a `single-file-cli` image with: resource requests/limits, an
`activeDeadlineSeconds` matching the crawl time cap, `ttlSecondsAfterFinished` for
auto-cleanup, and a `/dev/shm` `emptyDir` (`medium: Memory`) because Chrome needs shared
memory. It writes the captured **Pages** (self-contained HTML) plus a **manifest** (page
list, titles, link graph) to the shared RWX NFS PVC. Live progress is read from the Job
status + pod logs; concurrency is capped (default 1–2 simultaneous Jobs).

## Considered and rejected

- **Bundle the crawler + Chrome into the app image, run crawls as a subprocess** — a large
  image, a long crawl occupies (and can OOM) the always-on web pod, and no per-crawl
  resource isolation.
- **Persistent queue + worker deployment** — more standing infrastructure than occasional
  captures justify.

## Consequences

- The web app holds Job-management RBAC **in its own namespace only** — a deliberate,
  scoped privilege (not cluster-wide).
- If a finished Job is TTL-reaped, live progress detail is gone, but the resulting Pages and
  the SQLite Capture record persist — the Library is derived from those, not from the Job.
- Egress is open (cluster has no default-deny), so the crawl reaches the internet with no
  extra config.

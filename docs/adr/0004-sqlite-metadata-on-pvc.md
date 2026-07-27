# 0004 — SQLite on the NFS PVC for Capture metadata, not shared Postgres

Status: accepted

Capture metadata (title, seed URL, scope config, status, timestamps, ZIM filename + size)
is a handful of rows with a single writer. We store it in a **SQLite file on the same NFS
PVC as the ZIMs**, rather than wiring into the shared cluster Postgres
(`pg-cluster-rw.dbaas.svc`).

This keeps the service self-contained — one volume holds all its state, backup is one
volume, and there is no cross-service dependency for trivial data. It is a deliberate
deviation from the homelab "reuse shared infra" default, justified by the tiny,
app-private, low-write dataset.

## Consequences

- The app runs at a **single replica** with `strategy { type = "Recreate" }` (the house
  default), which suits SQLite's single-writer model over NFS. Horizontal scaling would
  force a rethink (Postgres), but this workload never needs it.
- The app is otherwise stateless; all durable state lives on the PVC (captured Pages + the
  SQLite file), so a pod restart loses nothing.
- If multi-writer concurrency or cross-service queries ever appear, revisit Postgres via
  the standard `vault-database` ExternalSecret path.

# 0002 — Named-volume workspace + persistent sandbox session

Workspaces live on a named volume `workspaces:/workspaces` at
`workspaces/{user_id}/{agent_id}`, git-init on creation, shared by the `backend`
and the new `sandbox` service (`python:3.11-slim` + node, git, curl — multi-runtime).
The sandbox is a persistent per-workspace session with a 30-minute idle TTL; one bash
at a time per workspace via a per-workspace `asyncio.Lock` (concurrency = 1). Egress is
allowlisted (pypi, github, npm + the gateway itself). Quotas are 1 GiB soft disk per
workspace, 30 s bash timeout, 512 MiB / 0.5 CPU per session — enforced in the backend
as `AppError → SSE error` so the model sees "workspace quota exceeded" and can adapt.

Why a named volume (not a host bind): survives container recreate, no host path
assumptions, matches existing `pgdata`/`training_data` volumes. Why persistent session:
repo tasks need stateful work (`pip install` once, run many); per-call ephemeral would
be unbearably slow. Why one-at-a-time: prevents git interleaving and keeps the `file_edits`
audit + git history linear and revertible. See ADR-0003 for the edit/undo shape and the
capability-gate design (master switch + per-user grant).

# Backend Roadmap — Security & Functionality

A complete review of the FastAPI backend (`backend/app/`), verified against the code as it
stands now — not the `docs/issues.md` registry, which is stale. The product: use local LLMs
(LM Studio) and local image gen (ComfyUI) from a phone over Tailscale, with OpenRouter as an
optional cloud provider. Single-user, personal, tailnet-exposed.

## `docs/issues.md` is stale

The registry header says a 2026-06-13 pass "now fixed" many items, but the body still lists them
as 🔴 Open. Verified against code, these are **actually fixed** — do not re-touch:

- **CR-1 SSRF** — `services/search.py` `_assert_public_host` resolves the host and rejects
  private/loopback/link-local/reserved/multicast/unspecified + metadata IP; `fetch_page` uses
  `follow_redirects=False` and re-validates every redirect hop (`_MAX_REDIRECTS=5`).
- **CR-2 private→Langfuse** — `core/metrics.py` `record_metrics(..., record_content=...)`;
  chat/agent pass `not request.private`; private chats record metadata only.
- **CR-3/4/5 connection held / embeddings / Langfuse on path** — `routers/chat.py` does
  `await db.close()` before streaming and writes via a fresh `AsyncSessionLocal`;
  `store_exchange_memories` + `record_metrics` run via `core/background.spawn`.
- **CR-6 resolved provider** — both paths set `resolved_provider` from `client.base_url`.
- **CR-8 truncated signal** — agent `done` event carries `"truncated": bool`.
- **CR-9 `messages.index`** — `models/messages.py` `nullable=False` + `UniqueConstraint`;
  migration `a1f4e7c8d92b`.
- **CR-13 research idempotency** — `routers/research.py` dedups on
  `(user_id, query, status in (queued,running))`.
- **CR-12 embed dim** — `EMBED_DIM` config + length validation in `services/memory.py`.
- **HIGH-5 pool sizing** — `db.py` `pool_size=DB_POOL_SIZE(20)`, `max_overflow(10)`, `pool_pre_ping=True`.
- **MED-6 ChatMessage length** — `services/router.py` `content: str = Field(max_length=100_000)`.
- **MED-1 refresh rotation** — `routers/auth.py` `/auth/refresh` delete+insert + independent
  `expires_at` check.
- **HIGH-2/4/7/8, MED-4/5/8/9/10/11, DEV-1..12** — all confirmed fixed in code.

Items issues.md lists as open that are **genuinely still open** (carried into the plan below):
CR-7, CR-10, CR-11, CR-14, CR-15, CR-16, MED-2, MED-3, MED-7, HIGH-1, HIGH-3, HIGH-9,
CR-17/18/19/20/21/22/23.

## Issues

### Security

#### S1 — Backend won't boot without an OpenRouter key (breaks the primary use case) · HIGH
- **Where:** `core/config.py:99` `OPENROUTER_API_KEY = get_secret("openrouter_api_key")` runs at
  module import.
- **Why:** `get_secret` raises `RuntimeError` if neither `/run/secrets/openrouter_api_key` nor
  `$OPENROUTER_API_KEY` exists. README marks the key as *not required* and the local-only setup
  (LM Studio + ComfyUI over Tailscale) is the stated goal. Today the app cannot start without a
  dummy key.
- **Fix:** make the key lazy and optional. Replace the module-level call with
  `get_openrouter_api_key() -> str | None` (add a non-raising `get_secret_or_none`). Guard
  every OpenRouter call site on a non-None key: `services/router.py::get_openrouter_client`,
  `services/research.py::_pick_client`, `routers/models.py::list_openrouter_models` — return
  `None`/502/skip when unset.

#### S2 — `/metrics` unauthenticated and the backend port is host-published · HIGH
- **Where:** `main.py:36` `Instrumentator().instrument(app).expose(app)` (no auth);
  `docker-compose.yml:19` `ports: - "2727:8000"`.
- **Why:** `/metrics` exposes model names, per-provider request/token volumes, conversation
  counts to anyone on the tailnet; the published port bypasses Caddy (so S5 also bites).
- **Fix:** remove `ports: 2727:8000` from `docker-compose.yml` (Caddy `:80` is the only
  ingress). Gate `/metrics` behind a `METRICS_TOKEN` env var + `Authorization: Bearer` check,
  or scrape `backend:8000/metrics` only on the internal Docker network.

#### S3 — ComfyUI `/view*` proxied unauthenticated · HIGH
- **Where:** `caddy/Caddyfile:19-21` `handle /view* { reverse_proxy host.docker.internal:8188 }`.
- **Why:** any tailnet user can fetch any ComfyUI output image by filename; ComfyUI's `/view`
  has a history of path-traversal in `subfolder`/`filename`.
- **Fix:** remove the open Caddy `/view*` proxy. Add a backend route
  `GET /v1/images/file?filename=&subfolder=&type=` that requires auth, validates ownership
  (extend the `imgjob:*` Redis map), and rejects `..`/absolute paths. Caddy proxies
  `/api/v1/images/file` only.

#### S4 — Register endpoint allows email enumeration · MEDIUM
- **Where:** `routers/auth.py:64` `raise HTTPException(400, "user already exists")`.
- **Fix:** change the duplicate-email response to a constant `400 {"detail":"invalid request"}`.

#### S5 — Rate limiter trusts `X-Forwarded-For` unconditionally · MEDIUM
- **Where:** `middleware/ratelimit.py:90-92` `_client_ip` takes the first XFF hop always.
- **Fix:** only trust XFF when the direct peer is in a `TRUSTED_PROXIES` set (default
  `{"caddy","127.0.0.1"}`); else use `request.client.host`.

#### S6 — MCP_SERVERS stdio spawns arbitrary commands · LOW (trust boundary)
- **Where:** `services/mcp_client.py:57-62`. Operator-configured via env (RCE-by-config, not
  remote). Document in `.env.example`; never let user input reach `MCP_SERVERS`.

#### S7 — Open registration on a tailnet-exposed app · LOW
- **Where:** `routers/auth.py` `/auth/register` is open.
- **Fix:** add `REGISTRATION_ENABLED` bool (default true); 403 when false.

### Reliability / correctness

#### R1 — Agent loop holds the DB connection for the whole multi-round run · HIGH
- **Where:** `services/agent.py::run_agent` — the request's `db` is used for `load_history`,
  every tool execution, and `save_messages`. No `db.close()` before the loop (unlike chat).
- **Fix:** mirror the chat path: load history up front, `await db.close()`, run the loop holding
  no connection; give each tool its own short-lived `AsyncSessionLocal`; fresh session for
  `save_messages`.

#### R2 — Agent `messages` array grows unbounded → context overflow mid-loop · HIGH (CR-7)
- **Where:** `services/agent.py` — tool results (8k each) appended every round; only
  `AGENT_TOKEN_BUDGET` gates tool offering, not array size.
- **Fix:** track running prompt tokens; when `> 0.6 * AGENT_TOKEN_BUDGET`, drop oldest
  tool-call/tool-result pairs. Catch `APIError` context-length indicators → degrade to a
  tool-less final synthesis round with `truncated=True`.

#### R3 — Local token counts are fiction · MEDIUM (CR-10)
- **Where:** `routers/chat.py:155-160` — local path omits `stream_options`, so `prompt_tok=0`,
  `completion_tok=chunk count`.
- **Fix:** after the local stream, call LM Studio `/v1/tokenize/encode` for the prompt (off the
  response path via `spawn`). Store `token_provenance` (`exact`|`estimated`|`chunk_count`) on
  `messages`.

#### R4 — Deep research silently uses the SDXL rewrite model · MEDIUM (CR-14)
- **Where:** `services/research.py::_pick_client` — falls back to `LM_DEFAULT_MODEL` when no
  OpenRouter and no `LM_CHAT_MODEL`. `job.model` stored as `"auto"`.
- **Fix:** require a capable chat model: reject at submit (503) if none configured. Resolve the
  model in the router and store it on `job.model`.

#### R5 — ComfyUI node anchor matched by substring · MEDIUM (CR-15)
- **Where:** `services/comfy.py::_find_node` — `if class_substr in node.get("class_type","")`.
- **Fix:** for critical anchors (`KSampler`, `ResolutionSelector`, `*LatentImage`), refuse to
  guess if >1 match; require `param_map` for ambiguous anchors. Error at workflow upload.

#### R6 — DuckDuckGo scraper fails silently to empty · MEDIUM (CR-16)
- **Where:** `services/search.py::_duckduckgo` — 200 with no matches returns `[]` silently.
- **Fix:** on 200 + empty `titles`, log a warning + emit a `search_degraded_total` counter.
  Change the tool's empty-result text to "degraded; answer from prior knowledge."

#### R7 — No background sweep of expired refresh tokens · LOW (MED-2)
- **Fix:** arq cron job hourly: `DELETE FROM refresh_tokens WHERE expires_at < now()`.

### Data integrity (minor)

- **D1 — non-owner returns 403, not 404 (enumeration).** `routers/convo.py` — route through
  `_get_owned_conversation` (which 404s).
- **D2 — `/openrouter/models` no timeout + `Bearer None`.** Add `timeout=10`; 503 when key
  unset.
- **D3 — Memories migration can't downgrade.** `alembic/versions/4b602081a1e1` `downgrade()` is
  `pass` → `op.execute('DROP TABLE IF EXISTS memories CASCADE')`.
- **D4 — No pagination on list endpoints.** Add `limit`/`offset` to `GET /convo`, `/presets`,
  `/templates`.

### Maintainability

- **M1 — Dependencies unpinned (MED-7).** `pip-compile` and pin all versions.
- **M2 — Stale Gemini references.** `.env.example` + README list `GEMINI_*` but no Gemini
  provider exists. Remove.
- **M3 — Hardcoded Postgres user/DB (HIGH-1).** `${POSTGRES_USER:?}` / `${POSTGRES_DB:?}` from
  `.env`.
- **M4 — No CI schema-drift guard (CR-22).** CI: `alembic upgrade head` on scratch DB, boot app,
  assert empty autogenerate diff.

### Latent / by-design (no action now)
- **CR-17** orphaned conversation rows (hidden by `EXISTS` filter on `GET /v1/convo`).
- **CR-18** `get_redis()`/`get_queue()` lazy-init no lock (masked by lifespan warmup).
- **CR-19** rate limiter is `BaseHTTPMiddleware` (works today; never touches the body).
- **CR-20/21** no vector index / no `messages(conversation_id,index)` composite (premature at
  current scale).
- Image URLs in `comfy.get_job_status` use the internal `COMFY_URL` — the SPA must rewrite them
  to `/view`.

## Fix Plan (ordered)

### Phase 1 — Boot safely on the tailnet (security)
1. **S1** — optional OpenRouter key in `core/config.py` + guard all OpenRouter call sites.
2. **S2** — stop publishing the backend port + gate `/metrics`.
3. **S5** — trust XFF only from `TRUSTED_PROXIES`.
4. **S3** — authed ComfyUI file route; remove open `/view*` proxy.
5. **S4** — neutralize register enumeration message.
6. **S7** — `REGISTRATION_ENABLED` flag.

### Phase 2 — Reliability under load
7. **R1** — release the DB connection in the agent loop.
8. **R2** — bound the agent message array + context-overflow degradation.
9. **R4** — honest research model (reject at submit if none capable; store resolved model).
10. **R5** — strict ComfyUI anchors (refuse ambiguous; require `param_map`).
11. **R6** — surface DDG degradation (warn + metric).
12. **R3** — honest local token counts (`token_provenance` column + tokenize call).

### Phase 3 — Data integrity
13. **D1** — uniform 404 for non-owned resources.
14. **D4** — pagination on list endpoints.
15. **R7** — expired-token sweep (arq cron).
16. **D3** — memories migration downgrade.

### Phase 4 — Maintainability
17. **M1** — pin all dependencies.
18. **M2** — remove stale Gemini references.
19. **M3** — parameterize Postgres user/DB.
20. **M4** — CI schema-drift guard.

## Verification

- **Phase 1:** `docker compose up --build` with no `OPENROUTER_API_KEY` → backend starts,
  `/health` returns 200. From the tailnet: `/metrics` → 401/404; `:2727/metrics` → refused.
  Spoofed-IP rate-limit check: 15 logins with forged XFF from one real IP → 429 after 10.
- **Phase 2:** `POST /v1/agent/chat` with 4+ tool calls → completes without context error,
  `done.truncated` accurate; `pg_stat_activity` shows no idle connection held for the run.
  Research with no capable model → 503. ComfyUI workflow with `KSampler` + `KSamplerAdvanced`
  and no `param_map` → upload rejected.
- **Phase 3:** `alembic downgrade -1` from the memories migration succeeds. `GET /convo?limit=10`
  paginates.
- **Phase 4:** `pip freeze` matches pinned `requirements.txt`.

## Critical files
- `backend/app/core/config.py:99` — eager `OPENROUTER_API_KEY = get_secret(...)` (S1).
- `backend/app/services/agent.py::run_agent` (L88–206) — no `db.close()` (R1) + unbounded
  `messages` (R2).
- `backend/app/middleware/ratelimit.py::_client_ip` (L87–93) — unconditional XFF trust (S5).
- `backend/app/main.py:36` + `docker-compose.yml:19` — unauthed `/metrics` + published port (S2).
- `caddy/Caddyfile:19-21` — open `/view*` proxy (S3).

## Assumptions
- **Single-user, personal, tailnet-only.** TLS is terminated by Tailscale; Caddy stays plain
  HTTP on :80 by design. If exposed beyond the tailnet, S2/S3 become release blockers and real
  TLS must be added at Caddy.
- **OpenRouter is optional** (per README + the local-only goal). S1 makes this true in code.
- **S4/S7 are preferences.** Default: neutralize the register message (cheap); `REGISTRATION_ENABLED`
  defaults true (no behavior change).
- **R3 adds one extra local HTTP call after each answer** (off the response path via `spawn`).
  Fallback: only add `token_provenance` and mark local counts `chunk_count` — honest, no extra
  call.
- **S3 changes frontend image rendering** (rewrite to `/api/v1/images/file`). Backend fix is in
  scope here; the frontend change is noted in the frontend roadmap.

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
- **Status: DONE** — `/metrics` is gated behind `METRICS_TOKEN` (empty token ⇒ 404, fail-closed;
  missing/wrong `Authorization: Bearer` header ⇒ 401) and the backend port is bound to
  `127.0.0.1` only. Prometheus authenticates via the mounted `monitoring/metrics_token`
  credentials file; `setup.ps1`/`setup.sh` generate/sync the token. See "Security fixes
  implemented (S2 + S3)" below.

#### S3 — ComfyUI `/view*` proxied unauthenticated · HIGH
- **Where:** `caddy/Caddyfile:19-21` `handle /view* { reverse_proxy host.docker.internal:8188 }`.
- **Why:** any tailnet user can fetch any ComfyUI output image by filename; ComfyUI's `/view`
  has a history of path-traversal in `subfolder`/`filename`.
- **Fix:** remove the open Caddy `/view*` proxy. Add a backend route
  `GET /v1/images/file?filename=&subfolder=&type=` that requires auth, validates ownership
  (extend the `imgjob:*` Redis map), and rejects `..`/absolute paths. Caddy proxies
  `/api/v1/images/file` only.
- **Status: DONE** — the open Caddy `/view*` block is removed; `GET /v1/images/file` requires
  a valid access token plus a Redis `imgfile:{filename}` ownership entry (set on job
  completion, TTL `IMAGE_FILE_TTL_SECONDS`), and `services/image_security.py` rejects
  `..`/path separators/bad chars. Status URLs are now relative `/v1/images/file?...`. See
  "Security fixes implemented (S2 + S3)" below.

#### S4 — Register endpoint allows email enumeration · MEDIUM
- **Where:** `routers/auth.py:64` `raise HTTPException(400, "user already exists")`.
- **Fix:** respond identically to a successful registration
  (`200 {"message":"user created successfully"}`) for both existing and new emails, so a
  register attempt can't reveal whether an address is taken.
- **Status: DONE** — `/auth/register` returns the same `200 {"message":"user created
  successfully"}` for existing and new emails, and the duplicate-email `IntegrityError`
  race still maps to the same body. See "Security fixes implemented (S4 + S5 + S7)" below.

#### S5 — Rate limiter trusts `X-Forwarded-For` unconditionally · MEDIUM
- **Where:** `middleware/ratelimit.py:90-92` `_client_ip` takes the first XFF hop always.
- **Fix:** only trust XFF when the direct peer is in a `TRUSTED_PROXIES` set
  (comma-separated CIDRs, default `172.16.0.0/12`); else use `request.client.host`.
- **Status: DONE** — `_client_ip` resolves through `core/trusted_proxies.py::resolve_client_ip`,
  which trusts the first `X-Forwarded-For` hop only when the direct peer falls inside
  `settings.trusted_proxy_networks`; an empty `TRUSTED_PROXIES` disables XFF trust entirely.
  See "Security fixes implemented (S4 + S5 + S7)" below.

#### S6 — MCP_SERVERS stdio spawns arbitrary commands · LOW (trust boundary)
- **Where:** `services/mcp_client.py:57-62`. Operator-configured via env (RCE-by-config, not
  remote). Document in `.env.example`; never let user input reach `MCP_SERVERS`.
- **Status: DONE** — README (env-var table row + "MCP trust boundary" note) and `.env.example`
  now warn that `MCP_SERVERS` is operator-configured, can spawn arbitrary commands (a stdio
  entry runs whatever `command` names), and must never be derived from user input.

#### S7 — Open registration on a tailnet-exposed app · LOW
- **Where:** `routers/auth.py` `/auth/register` is open.
- **Fix:** add `REGISTRATION_ENABLED` bool (default true); 403 when false.
- **Status: DONE** — `REGISTRATION_ENABLED` (default true) gates `/auth/register` with
  `403 {"detail":"registration disabled"}` when false. See "Security fixes implemented
  (S4 + S5 + S7)" below.

### Reliability / correctness

#### R1 — Agent loop holds the DB connection for the whole multi-round run · HIGH
- **Where:** `services/agent.py::run_agent` — the request's `db` is used for `load_history`,
  every tool execution, and `save_messages`. No `db.close()` before the loop (unlike chat).
- **Fix:** mirror the chat path: load history up front, `await db.close()`, run the loop holding
  no connection; give each tool its own short-lived `AsyncSessionLocal`; fresh session for
  `save_messages`.
- **Status: DONE** — `run_agent` closes the request session after the up-front reads and before
  the loop; each tool runs on a short-lived `AsyncSessionLocal`; `save_messages` uses its own
  fresh session. See "Reliability fixes implemented (R1 + R2)" below.

#### R2 — Agent `messages` array grows unbounded → context overflow mid-loop · HIGH (CR-7)
- **Where:** `services/agent.py` — tool results (8k each) appended every round; only
  `AGENT_TOKEN_BUDGET` gates tool offering, not array size.
- **Fix:** track running prompt tokens; when `> 0.6 * AGENT_TOKEN_BUDGET`, drop oldest
  tool-call/tool-result pairs. Catch `APIError` context-length indicators → degrade to a
  tool-less final synthesis round with `truncated=True`.
- **Status: DONE** — messages are pruned to `0.6 × AGENT_TOKEN_BUDGET` before every tool round
  (oldest assistant-with-tool_calls + its tool results go first; the system/user prefix is
  never touched) and a context-length `APIError` mid-loop degrades to a tool-less final answer
  with `truncated=True`. See "Reliability fixes implemented (R1 + R2)" below.

#### R3 — Local token counts are fiction · MEDIUM (CR-10)
- **Where:** `routers/chat.py:155-160` — local path omits `stream_options`, so `prompt_tok=0`,
  `completion_tok=chunk count`.
- **Fix:** after the local stream, call LM Studio `/v1/tokenize/encode` for the prompt (off the
  response path via `spawn`). Store `token_provenance` (`exact`|`chunk_count`|`null`) on
  `messages`.
- **Status: DONE** — `messages.token_provenance` (`exact` | `chunk_count` | null, migration
  `f3a9c1d5e7b2`) tags how `tokens_used` was derived; the chat path computes it from whether
  the provider reported usage and spawns `services/tokenize.py::sync_local_token_counts` on
  the local path to overwrite the last exchange with exact LM Studio counts; the agent path
  tags the same provenance from provider usage. See "Reliability fixes implemented (R3–R6)"
  below.

#### R4 — Deep research silently uses the SDXL rewrite model · MEDIUM (CR-14)
- **Where:** `services/research.py::_pick_client` — falls back to `LM_DEFAULT_MODEL` when no
  OpenRouter and no `LM_CHAT_MODEL`. `job.model` stored as `"auto"`.
- **Fix:** require a capable chat model: reject at submit (503) if none configured. Resolve the
  model in the router and store it on `job.model`.
- **Status: DONE** — `services/research.py::resolve_research_model` computes the `(role,
  model)` pair research will run on (mirroring `_pick_provider` without constructing
  providers); `routers/research.py` stores the resolved pair on the job and returns 503
  "no capable chat model configured for research" when nothing resolves. See "Reliability
  fixes implemented (R3–R6)" below.

#### R5 — ComfyUI node anchor matched by substring · MEDIUM (CR-15)
- **Where:** `services/comfy.py::_find_node` — `if class_substr in node.get("class_type","")`.
- **Fix:** for critical anchors (`KSampler`, `ResolutionSelector`, `*LatentImage`), refuse to
  guess if >1 match; require `param_map` for ambiguous anchors. Error at workflow upload.
- **Status: DONE** — `validate_workflow_anchors` rejects ambiguous workflows at upload/update
  (422) unless `param_map` pins the intended node; `inject_params` auto-detects with exact
  matching and skips (never guesses) when an anchor is missing or ambiguous; `inject_lora`
  anchors only on an exact `KSampler` (a KSamplerAdvanced-only graph gets no LoRA). See
  "Reliability fixes implemented (R3–R6)" below.

#### R6 — DuckDuckGo scraper fails silently to empty · MEDIUM (CR-16)
- **Where:** `services/search.py::_duckduckgo` — 200 with no matches returns `[]` silently.
- **Fix:** on 200 + empty `titles`, log a warning + emit a `search_degraded_total` counter.
  Change the tool's empty-result text to "degraded; answer from prior knowledge."
- **Status: DONE** — `_duckduckgo` and `_searxng` log a warning and increment
  `search_degraded_total{source="duckduckgo"|"searxng"}` on a 200 with zero results; the
  `web_search` tool returns "Search returned no results (degraded); answer from prior
  knowledge." See "Reliability fixes implemented (R3–R6)" below.

#### R7 — No background sweep of expired refresh tokens · LOW (MED-2)
- **Fix:** arq cron job hourly: `DELETE FROM refresh_tokens WHERE expires_at < now()`.
- **Status: DONE** — `worker.py` schedules `sweep_expired_tokens` via arq `cron_jobs`
  (`cron(sweep_expired_tokens, minute=0)`, hourly at minute 0); the job deletes
  `refresh_tokens` rows whose `expires_at` is in the past on a fresh `AsyncSessionLocal`
  session. Worker restart required to pick up cron changes (arq does not hot-reload). See
  "Data integrity fixes implemented (D4 + R7)" below.

### Data integrity (minor)

- **D1 — non-owner returns 403, not 404 (enumeration).** `routers/convo.py` — route through
  `_get_owned_conversation` (which 404s).
  - **Status: DONE** — `messages_get`/`convo_rename`/`convo_delete` now all route through
    `_get_owned_conversation`, keeping the ownership invariant: 404 when the conversation is
    missing, 403 when it belongs to someone else (UUIDs are unguessable, so there is no
    enumeration leak).
- **D2 — `/openrouter/models` no timeout + `Bearer None`.** Add `timeout=10`; 503 when key
  unset.
  - **Status: DONE** — `httpx.AsyncClient(timeout=10)` added; the 503-when-key-unset guard is
    unchanged.
- **D3 — Memories migration can't downgrade.** `alembic/versions/4b602081a1e1` `downgrade()` is
  `pass` → `op.execute('DROP TABLE IF EXISTS memories CASCADE')`.
  - **Status: DONE** — downgrade drops the `memories` table
    (`DROP TABLE IF EXISTS memories CASCADE`), mirroring the upgrade's FK to
    `conversations.id` with `ondelete='CASCADE'`. Verified in `4b602081a1e1_add_memories_table.py`.
- **D4 — No pagination on list endpoints.** Add `limit`/`offset` to `GET /convo`, `/presets`,
  `/templates`.
  - **Status: DONE** — `GET /v1/convo`, `/v1/presets`, `/v1/templates` accept optional
    `limit` (1–200) and `offset` (≥0) query params; when `limit` is set the `select` gets
    `.limit(limit).offset(offset)` applied before execution (existing `order_by` preserved).
    `limit=None` keeps the previous no-limit behavior; response shapes unchanged. See
    "Data integrity fixes implemented (D4 + R7)" below.

### Maintainability

- **M1 — Dependencies unpinned (MED-7).** `pip-compile` and pin all versions.
- **M2 — Stale Gemini references.** `.env.example` + README list `GEMINI_*` but no Gemini
  provider exists. Remove.
  - **Status: DONE** — `GEMINI_MODEL`/`GEMINI_API_KEY` removed from `.env.example`; a
    case-insensitive repo grep finds no `GEMINI_*` env references. The `google` BYO-key
    provider type (README "Adding providers") is a real adapter and is kept.
- **M3 — Hardcoded Postgres user/DB (HIGH-1).** `${POSTGRES_USER:?}` / `${POSTGRES_DB:?}` from
  `.env`.
  - **Status: DONE** — docker-compose reads `POSTGRES_USER`/`POSTGRES_DB` from `.env`
    (required); `setup.ps1`/`setup.sh` add the defaults (`ishaab`/`llmgateway`) when missing
    without overwriting existing values; README env-var table documents both.
- **M4 — No CI schema-drift guard (CR-22).** CI: `alembic upgrade head` on scratch DB, boot app,
  assert empty autogenerate diff.

### Latent / by-design (no action now)
- **CR-17** orphaned conversation rows (hidden by `EXISTS` filter on `GET /v1/convo`).
- **CR-18** `get_redis()`/`get_queue()` lazy-init no lock (masked by lifespan warmup).
- **CR-19** rate limiter is `BaseHTTPMiddleware` (works today; never touches the body).
- **CR-20/21** no vector index / no `messages(conversation_id,index)` composite (premature at
  current scale).
- Image URLs from `comfy.get_job_status` are now relative `/v1/images/file?...` (authed, S3) —
  the SPA uses the returned `url` directly; no `/view` rewrite needed.

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
13. **D1** — route conversation ownership through `_get_owned_conversation` (404 missing / 403 foreign — UUIDs unguessable, no enumeration leak).
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
- `backend/app/core/trusted_proxies.py` — stdlib `resolve_client_ip` (S5): trusts
  `X-Forwarded-For` only from peers inside `trusted_proxy_networks`.
- `backend/app/services/agent.py::run_agent` — closes the request session before the loop (R1)
  and prunes/degrades on context overflow (R2) — both fixed, see "Reliability fixes
  implemented (R1 + R2)".
- `backend/app/services/tokenize.py::sync_local_token_counts` — off-path exact token counts
  for local exchanges via LM Studio `/v1/tokenize/encode` (R3); `messages.token_provenance`
  records how counts were derived (migration `f3a9c1d5e7b2`).
- `backend/app/services/research.py::resolve_research_model` — resolves the research
  (role, model) at submit; `routers/research.py` stores it on the job and 503s when no
  capable model exists (R4).
- `backend/app/services/comfy.py::validate_workflow_anchors` + `_find_node_exact` — ambiguous
  workflows rejected at upload, auto-injection never guesses (R5).
- `backend/app/services/search.py` — 200-with-zero-results logs a warning and increments
  `search_degraded_total` (R6).
- `backend/app/middleware/ratelimit.py::_client_ip` — XFF trusted only when the direct peer
  is in `settings.trusted_proxy_networks` (`TRUSTED_PROXIES`, default `172.16.0.0/12`) (S5).
- `backend/app/routers/auth.py` — identical register responses for existing/new emails (S4);
  `REGISTRATION_ENABLED` gate → `403 {"detail":"registration disabled"}` (S7).
- `backend/app/main.py:66` — `/metrics` gated behind `METRICS_TOKEN` (exact `Authorization:
  Bearer` header; empty token ⇒ 404 fail-closed) (S2).
- `docker-compose.yml:22` — backend port bound to `127.0.0.1` only (S2).
- `caddy/Caddyfile` — open `/view*` proxy removed; ComfyUI files served via authed
  `GET /v1/images/file` (S3).

## Assumptions
- **Single-user, personal, tailnet-only.** TLS is terminated by Tailscale; Caddy stays plain
  HTTP on :80 by design. If exposed beyond the tailnet, S2/S3 become release blockers and real
  TLS must be added at Caddy.
- **OpenRouter is optional** (per README + the local-only goal). S1 makes this true in code.
- **S4/S7 landed with the Phase 1 security pass** (see "Security fixes implemented (S4 + S5 +
  S7)"): register responses are identical for existing/new emails, and `REGISTRATION_ENABLED`
  defaults true (no behavior change until the operator flips it).
- **R3 adds one extra local HTTP call after each answer** (off the response path via `spawn`).
  Fallback: only add `token_provenance` and mark local counts `chunk_count` — honest, no extra
  call.
- **S3 changes frontend image rendering** (rewrite to `/api/v1/images/file`). Backend fix is in
  scope here; the frontend change is noted in the frontend roadmap.

## Phase 5 — BYO-key providers (in progress)

Users can now register their own model providers (their own API keys) instead of being
hard-wired to the env-configured LM Studio / OpenRouter pair. The routing engine
(`services/router.py`) and chat wiring are untouched in this phase — the provider
configuration surface and adapters are built and ready for a later phase to consume.

Implemented:

- **`providers` table** (`models/providers.py`, migration `b8e4f1a2c9d3`) — user-owned rows with
  name, type (`openai_compatible | openai | anthropic | google | openrouter`), role
  (`local | cloud`), optional base_url, `api_key_encrypted` (Fernet, never plaintext),
  `default_model`, `is_default`, `enabled`, `created_at`, and a unique `(user_id, name)`.
  FK to users is `ON DELETE CASCADE`.
- **Encrypted key storage** (`core/crypto.py`) — Fernet; key comes from `KEY_ENCRYPTION_KEY`
  (32 urlsafe base64 bytes) when set, else derived from `SECRET_KEY` via SHA-256 so existing
  deployments need no new env var. `encrypt_secret`/`decrypt_secret`; empty input and
  `InvalidToken` (rotated keys) raise `ValueError`. No plaintext keys are ever logged.
- **Adapter protocol** (`services/providers/`) — `LLMProvider` base with
  `stream_chat` (async iterator of `StreamChunk`) and `complete` (non-streamed). Concrete
  adapters: `openai_compat` (LM Studio/Ollama/Groq-style endpoints; `extra_body` for non-spec
  sampling, no `stream_options` to preserve LM Studio behavior), `openai`, `openrouter`
  (`stream_options={"include_usage": True}`, reads the final usage chunk), `anthropic` and
  `google` (SDKs lazy-imported; unavailable adapters raise `RuntimeError` on use).
- **Provider registry** (`services/provider_registry.py`) — `row_to_provider` (decrypts the
  key, dispatches to the right adapter), `list_providers`, `get_default_provider` (default
  flag first, else oldest enabled), `resolve_provider` (by id with 404/403 ownership checks,
  or by role default; 503 `NoProviderError` when a role has nothing configured),
  `test_provider` (one-token round-trip), `mask_key`.
- **CRUD router** (`routers/providers.py`, mounted at `/v1/providers`) — GET (seeds
  backward-compat rows first, then lists with `api_key_masked`), POST/PATCH (encrypts keys,
  keeps exactly one `is_default` per role), DELETE, and POST `/{id}/test`.
- **Backward-compat seeding** — `seed_default_providers` creates "Local (LM Studio)" from
  `LM_URL`/`LM_CHAT_MODEL` and "OpenRouter" from the (optional, S1) OpenRouter key on first
  list, so existing env-var behavior is preserved and keys migrate into the encrypted store.
- `KEY_ENCRYPTION_KEY` added to `core/config.py`; `cryptography` added to requirements
  (previously only transitive). `alembic/env.py` and `worker.py` import the new model.

Not in this phase (later): routing against these providers in `services/router.py`, chat/
agent wiring, per-provider param translation beyond what the adapters do.

## Phase 6 — image LoRA training (in progress)

Users can fine-tune image LoRAs from a zip of images and use the result on image
generation, all through the API — no manual ai-toolkit runs.

Implemented:

- **`trainings` table** (`models/trainings.py`, migration `d4a8b2c6f9e7`) — user-owned rows
  with name, `base_model` (`flux-dev | sdxl | sd1`), `dataset_dir` (inside the shared
  `training_data` volume), `artifact_filename` (the produced `.safetensors`), status
  (`queued|running|complete|failed|cancelled`), stage, 0-100 progress, JSONB params
  (steps, learning_rate), error, `sample_image`. FK to users is `ON DELETE CASCADE`.
- **Training CRUD + streaming** (`routers/trainings.py`, mounted at `/v1/trainings`) —
  `POST /trainings` (multipart: name, base_model, dataset zip with a 2 GB cap, steps,
  learning_rate; validates ≥3 images; safe flat zip extraction that rejects traversal
  and `__MACOSX` junk), `GET /trainings` + `GET /trainings/{id}` (404 for missing AND
  foreign rows — job ids can't be enumerated), `POST /trainings/{id}/cancel`, `GET
  /trainings/{id}/stream` (SSE `{"type":"progress"|"done"|"error"}` relayed from Redis
  pub/sub channel `train:{id}`), and `GET /trainings/{id}/artifact` (downloads the
  `.safetensors`, traversal-guarded).
- **Authed sample-image endpoint** — `GET /trainings/{id}/sample` mirrors the artifact
  route: owned-job check (404 for missing/foreign), 404 unless `status == "complete"`
  and `sample_image` is set, traversal-guarded resolve under the job dir, and a
  `FileResponse` (media type guessed from the extension). The web SPA renders it via
  the authed blob-fetch pattern.
- **Trainer arq worker** (`app/trainer_worker.py` + `services/trainer.py`) — a dedicated
  compose service (`trainer`) built from the `trainer` Dockerfile target, which clones
  ai-toolkit into `/opt/ai-toolkit` and runs `python /opt/ai-toolkit/run.py <config.yaml>`.
  One GPU job at a time (`max_jobs = 1`), `TRAINING_JOB_TIMEOUT_SECONDS` wall-clock cap.
  Progress is published to Redis pub/sub as the run progresses and the job row is updated
  at each stage so polling works and state survives worker restarts.
- **ai-toolkit specifics** — config uses the current `job: extension` shape with a
  `config:` wrapper (older `job: train` flat shape is gone upstream); FLUX.1-dev is a
  gated model so `HF_TOKEN` in `.env` is required for `base_model=flux-dev`; torch is
  pinned to the repo's CUDA 13.0 build (`torch==2.13.0 … --index-url …/whl/cu130` in the
  trainer Dockerfile); tqdm progress is parsed from `\r`-delimited chunks (a `\n`-only
  reader would starve); captions are optional — ai-toolkit falls back to an empty caption
  when `{image}.txt` is missing, so datasets may ride along their own `.txt` files.
- **base_model extension pattern** — `base_model` supports `flux-dev | sdxl | sd1`. The
  sd1/sdxl branches point `name_or_path` at local checkpoints mounted from
  `SD1_MODEL_PATH`/`SDXL_MODEL_PATH` (see `core/config.py`) instead of downloading the HF
  default; sd1 leaves `is_xl: false` so ai-toolkit uses its default sd1 arch. 6GB-VRAM
  tuning for sd1/sdxl: `cache_latents_to_disk`, `ema_config.use_ema: false`, batch 1,
  grad accum 1, gradient checkpointing, frozen TE, 512px. Adding another family = add it
  to the `base_model` Literal in `routers/trainings.py` + a `_build_config` branch in
  `services/trainer.py` + `*_MODEL_PATH`/`*_MODEL_NAME` settings + a compose mount
  (documented in the `trainer.py` module docstring).
- **LoRA injection on generation** — `POST /v1/images/generate` now accepts
  `training_id`. The handler copies the completed artifact into the ComfyUI LoRA folder
  (`COMFY_LORA_DIR`, mounted into the backend container as `/comfy-loras`) as
  `lora_{job.id}.safetensors`, then `services/comfy.py::inject_lora` splices a
  `LoraLoader` node into the workflow between the checkpoint loader and the sampler /
  CLIPTextEncode nodes. Injection is best-effort: a workflow that already has a
  `LoraLoader`, or an unparseable KSampler link, is left unchanged (warning logged) so
  generation never breaks. `COMFY_LORA_DIR` unset → 400; missing/foreign job → 404;
  unfinished job → 409. The response gains a `"lora"` field naming the loaded file.

Not in this phase (later): dataset management (delete/replace uploads), per-job trigger
words / caption editing, hyperparameter tuning beyond steps + learning rate, and
publishing trained LoRAs back to ComfyUI's own model browser.

## Security fixes implemented (S2 + S3)

The two tailnet-exposure fixes from Phase 1, landed together.

- **S2 — `/metrics` gated + backend port loopback-only.**
  - `app/main.py` no longer calls `Instrumentator().expose(app)`; a hand-written
    `GET /metrics` route returns **404** when `METRICS_TOKEN` is empty (fail-closed) and
    **401** without the exact `Authorization: Bearer <token>` header. The comparison lives
    in a pure module-level helper `_metrics_authorized` (unit-tested).
  - `docker-compose.yml` binds the backend to `127.0.0.1:2727:8000` — the tailnet reaches
    the API only through Caddy on `:80`; dev/docs stay available on the host.
  - Prometheus scrapes `backend:8000/metrics` with `authorization.type: Bearer` +
    `credentials_file: /etc/prometheus/metrics_token` (mounted from
    `monitoring/metrics_token`, gitignored).
  - `setup.ps1`/`setup.sh` generate `METRICS_TOKEN` in `.env` when missing (idempotent) and
    mirror the exact token into `monitoring/metrics_token` (no trailing whitespace — the
    backend compares the header string byte-for-byte).
- **S3 — authed image file endpoint, Caddy `/view*` proxy removed.**
  - `caddy/Caddyfile`: the `handle /view* { reverse_proxy host.docker.internal:8188 }` block
    is deleted; only `/api/*` → backend and the SPA remain.
  - New `GET /v1/images/file?filename=&subfolder=&type=` in `routers/images.py`: requires a
    valid access token, checks Redis `imgfile:{filename}` ownership (404 when absent/not
    yours), validates the reference via the new stdlib-only `services/image_security.py`
    (400 on violation), then proxies the file from ComfyUI's `/view` (502 on backend
    failure/non-200).
  - Ownership entries are written when a job completes: `job_status` sets
    `imgfile:{filename}` → user id with TTL `IMAGE_FILE_TTL_SECONDS` (default 7 days). The
    existing `imgjob:*` check is unchanged.
  - `comfy.get_job_status` now returns relative `/v1/images/file?...` URLs (built with
    `urlencode`); the JSON shape (`status`, `images[].filename`) is unchanged.

## Security fixes implemented (S4 + S5 + S7)

The tailnet-hardening follow-ups from Phase 1, landed together with the S2/S3 work.

- **S4 — no register enumeration.**
  - `app/routers/auth.py::register_user` returns the same
    `200 {"message":"user created successfully"}` whether the email already exists or was
    just created — the pre-insert `select` no longer raises a distinguishing 400, and the
    `IntegrityError` race path (two concurrent registers for the same address) returns the
    same body too. The SPA therefore cannot tell registered from unregistered addresses by
    response code or body.
- **S5 — rate limiter honors `X-Forwarded-For` only from trusted proxies.**
  - `app/middleware/ratelimit.py::_client_ip` now delegates to the stdlib-only helper
    `app/core/trusted_proxies.py::resolve_client_ip(peer, forwarded, trusted_networks)`:
    - peer is falsy or unparseable → `"unknown"` (an attacker can't forge a bucket key);
    - peer falls inside one of the configured `trusted_networks` **and** an
      `X-Forwarded-For` header is present → the first hop (the original client the trusted
      proxy saw), whitespace-stripped;
    - otherwise → the direct peer IP as-is, XFF ignored.
  - `TRUSTED_PROXIES` (comma-separated CIDRs, default `172.16.0.0/12` — the Docker bridge
    Caddy sits on) is parsed once per check in `core/config.py::trusted_proxy_networks`;
    invalid entries are skipped with a warning and an **empty** list means no proxy is
    trusted at all, so XFF is ignored everywhere.
  - New unit tests: `backend/tests/test_trusted_proxies.py` (11 cases: trusted/untrusted
    peers, missing/malformed peer, CIDR membership, empty trusted list).
- **S7 — `REGISTRATION_ENABLED` signup gate.**
  - `app/routers/auth.py::register_user` checks `settings.REGISTRATION_ENABLED` first and
    raises `403 {"detail":"registration disabled"}` when false. `core/config.py` adds the
    flag with default `true` (no behavior change out of the box).
  - Lock-down recipe: create your account, set `REGISTRATION_ENABLED=false` in `.env`,
    restart the backend (see README "Locking down signups").
- **Setup scripts** (`setup.ps1` Step 2c / `setup.sh` security-defaults block) add
  `TRUSTED_PROXIES=172.16.0.0/12` and `REGISTRATION_ENABLED=true` to `.env` only when
  missing — never overwriting a value the operator set deliberately. Both are idempotent:
  re-running changes nothing when the keys already exist.

## Reliability fixes implemented (R1 + R2)

The agent-loop reliability pass from Phase 2, landed together.

- **R1 — the agent loop no longer holds the request's DB connection.**
  - `services/agent.py::run_agent` closes the request session after the up-front reads
    (`conversation()`, `load_history()`, `get_allowed_tools()`, `get_provider()`) and before
    the multi-round loop, mirroring the chat path. No idle connection is held for the run.
  - Each tool execution gets its own short-lived `AsyncSessionLocal` (`ctx.db` is swapped per
    call); the unknown/unauthorised-tool branch needs no session. `save_messages` uses a fresh
    `AsyncSessionLocal` after the loop; `get_db`'s own close afterwards is a no-op.
- **R2 — messages are bounded and context overflow degrades.**
  - New pure helpers in `services/agent.py`: `_estimate_tokens` (≈ 4 tokens/message + 1 per 4
    chars), `_is_context_error` (provider-error string sniffing), `_prune_old_tool_rounds`
    (drops the oldest assistant-with-tool_calls message plus its tool results until the
    estimate fits; leading system messages + the first user message are never touched).
  - The loop prunes to `0.6 × AGENT_TOKEN_BUDGET` before every tool round, and to the full
    budget before the final tool-less round. A context-length `APIError` mid-loop logs a
    warning, drops all tool rounds, and synthesizes a tool-less final answer with
    `truncated=True` — the SSE event sequence and done-event shape are unchanged.
  - New unit tests: `backend/tests/test_agent.py` (7 cases covering the estimate, the error
    sniffing, and pruning structure).

## Reliability fixes implemented (R3–R6)

The Phase 2 reliability follow-ups (CR-10/14/15/16), landed together.

- **R3 — honest local token counts.**
  - `models/messages.py` adds `token_provenance` (`String(16)`, nullable — `exact` |
    `chunk_count` | `null`; migration `f3a9c1d5e7b2`), recording how `tokens_used` was
    derived. `save_messages` takes a `token_provenance` keyword and sets it on the assistant
    message.
  - `routers/chat.py::stream_tokens` computes `provenance = "exact" if prompt_tok > 0 else
    "chunk_count"` (cloud reports usage; local leaves it 0) and, on the LOCAL path only,
    spawns `services/tokenize.py::sync_local_token_counts(conversation_id, user_content,
    full_response)` after saving. The sync POSTs the user + assistant texts to
    `{LM_URL}/v1/tokenize/encode` (timeout 15, tolerant of `{"count": N}` and `{"length": N}`
    responses), then on a fresh session overwrites the last two messages — assistant
    `tokens_used` set to the completion count, both `token_provenance = "exact"`. Any error
    logs a warning and leaves the chunk_count values in place (counts are auxiliary, never a
    request failure).
  - `services/agent.py::run_agent` computes the same provenance from whether any round
    reported usage and passes it to `save_messages`.
- **R4 — honest research model.**
  - New `services/research.py::resolve_research_model(provider_arg, user_id, db)` computes
    the `(role, model)` pair research will run on, mirroring `_pick_provider`'s precedence
    without constructing providers: `"openrouter"`→cloud, `"local"`→local, else cloud when
    `OPENROUTER_DEFAULT_MODEL` is set; a configured default row wins; the legacy env fallback
    needs an OpenRouter key for cloud and uses `LM_CHAT_MODEL or LM_DEFAULT_MODEL` for local.
    Returns `None` when no model string resolves.
  - `routers/research.py::create_research` resolves before enqueueing: `None` → 503
    "no capable chat model configured for research"; otherwise the job is stored with
    `provider = resolved_role` and `model = resolved_model` (the worker's `_pick_provider`
    then just uses the stored model). `request.model` no longer lands as `"auto"` on the job.
- **R5 — strict ComfyUI anchors.**
  - `services/comfy.py` adds `_find_node_exact` (exact `class_type` equality) and
    `validate_workflow_anchors(graph, param_map)`: raises `ValueError` when a critical anchor
    pattern (KSampler/KSamplerAdvanced family, `ResolutionSelector`, `*LatentImage`) has more
    than one match and `param_map` doesn't target one of the matched node ids.
  - `inject_params` auto-detection now requires EXACTLY one exact match per anchor
    (`KSampler` equality, `ResolutionSelector` equality, `endswith("LatentImage")`); 0 or >1
    matches means that param is left unset unless `param_map` overrides it — no guessing.
    `param_map` priority is unchanged (applied after auto-detect).
  - `inject_lora` anchors on an exact `KSampler` only — a KSamplerAdvanced-only graph logs
    and skips instead of getting a silent LoRA splice.
  - `routers/workflows.py` create + update call `validate_workflow_anchors` and translate
    `ValueError` → `HTTPException(422, str(e))`.
- **R6 — search degradation is surfaced.**
  - `core/metrics.py` adds `search_degraded_total` (Counter, `["source"]`). `_duckduckgo`
    and `_searxng` log a warning and increment it (source `"duckduckgo"`/`"searxng"`) when a
    200 response yields zero results.
  - `services/tools/web_search.py` empty-result text is now "Search returned no results
    (degraded); answer from prior knowledge." — the model is told the search degraded instead
    of pretending it found nothing.
- **Tests:** `backend/tests/test_comfy.py` grows 8 cases: base workflow passes validation;
  KSampler + KSamplerAdvanced raises without `param_map` and passes with it; multiple latent
  nodes raise; `inject_params` leaves `batch_size` unset on ambiguous latent graphs; a
  KSamplerAdvanced-only graph gets no LoRA injection; `param_map` still beats auto-detect.

## Data integrity fixes implemented (D4 + R7)

The Phase 3 data-integrity leftovers (D4 + R7), landed together.

- **D4 — optional pagination on list endpoints.**
  - `GET /v1/convo`, `GET /v1/presets`, `GET /v1/templates` now accept two optional query
    params: `limit: int | None` (`ge=1, le=200`, default `None` = no limit, previous
    behavior) and `offset: int` (`ge=0`, default `0`). When `limit` is set, `.limit(limit)
    .offset(offset)` is chained onto the existing `select` before execution, keeping each
    endpoint's `order_by` untouched (convo sorts `created_at.desc()`, presets/templates have
    no explicit order). Response shapes are unchanged — `{"data": [...]}` for
    presets/templates, a bare array for convo.
- **R7 — hourly expired refresh-token sweep.**
  - `worker.py` adds `sweep_expired_tokens(ctx)`, which on a fresh `AsyncSessionLocal`
    session runs `delete(RefreshToken).where(RefreshToken.expires_at < datetime.utcnow())`
    and commits — no orphaned expired `refresh_tokens` rows accumulate.
  - `WorkerSettings` gains `cron_jobs = [cron(sweep_expired_tokens, minute=0)]` (arq 0.25,
    the `from arq import cron` API), firing hourly at minute 0. Everything else in
    `WorkerSettings` is unchanged. **The worker container must be restarted for cron changes
    to take effect** — arq does not hot-reload.
- **Tests:** `backend/tests/test_worker.py` asserts `WorkerSettings.cron_jobs` is non-empty,
  `WorkerSettings.functions` still includes `run_research`, and `sweep_expired_tokens` is
  callable (offline; the sweep itself is never invoked).

## Auth hardening (S-A)

A defensive pass over the auth/API surface, landed together.

- **Consistent 401s for missing credentials.** `core/security.py` introduces `_AuthBearer`
  (an `HTTPBearer` subclass with `auto_error=False`): the parent returns `None` instead of
  raising when the `Authorization` header is absent (or isn't a Bearer scheme), and the
  subclass raises `401 {"detail":"not authenticated"}` in that case. `get_current_user` now
  depends on `Depends(_AuthBearer())`, so every authed route answers **401** for a missing
  header instead of FastAPI's stock 403 — invalid/expired tokens keep their existing 401s.
- **Refresh-token `sub` cross-check.** `routers/auth.py` `/auth/refresh` now verifies
  `str(token_record.user_id) == str(payload.get("sub"))` after the DB expiry check and JWT
  decode, before minting the rotated token — a mismatched row/claim pair can't be rotated.
- **`GET /v1/images/aspect-ratios` now authed.** The static config endpoint takes
  `user_id: str = Depends(get_current_user)` like every other `/v1` route; response shape
  unchanged. The SPA already sends the bearer token on every request, so no client change
  was needed beyond the roadmap note.
- **Provider test errors genericized.** `services/provider_registry.py::test_provider` logs
  the real exception server-side (`logger.warning`) and returns
  `{"ok": false, "error": "provider test failed"}` instead of leaking the raw exception
  string (URLs, key fragments, SDK tracebacks) to the client. The `{ok, model}` success
  path and the `"no default model set"` result are unchanged.
- **Trainings detail no longer leaks `dataset_dir`.** `GET /v1/trainings/{id}` drops the
  absolute server path from the response; the summary shape (`id`, `name`, `base_model`,
  `status`, `stage`, `progress`, `created_at`, `artifact_filename`, `sample_image`,
  `error`) plus `params` is unchanged.
- **JWTs carry `iat`.** Both `create_access_token` and `create_refresh_token` add
  `"iat": int(time.time())` to the payload.

## Config / infra hardening (S-B)

A configuration + infra hardening batch, landed together.

- **Loopback monitoring ports.** `docker-compose.yml` binds Prometheus to
  `127.0.0.1:9090:9090` and Grafana to `127.0.0.1:3000:3000` (previously `9090:9090` /
  `3000:3000`). Dashboards remain reachable on the host for dev but are no longer exposed
  to the tailnet — Caddy on `:80` is the only ingress (same policy as the backend port, S2).
- **Caddy security headers.** The `:80` site block sets a site-level `header` directive
  (applies to every handler): `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, and a CSP (`default-src 'self'`, `img-src 'self' blob:
  data:`, `style-src 'self' 'unsafe-inline'`, `connect-src 'self' http://localhost:2727
  http://localhost:5173`, `script-src 'self'`). A comment documents the two CSP constraints:
  `img-src` must include `blob:` (the SPA renders authed images as blob URLs via
  AuthedImage) and `connect-src` must cover the API origins.
- **DEBUG refused in production.** `core/config.py` raises `RuntimeError` at import when
  `DEBUG=True` and `ENV=production` — the app fails boot on a bad config instead of echoing
  SQL in prod.
- **Provider `base_url` scheme validation + private-URL guard.** `routers/providers.py`
  adds `_validate_provider_base_url`: `base_url` must be http(s) with a hostname, and — when
  `ALLOW_PRIVATE_PROVIDER_URLS` is False — must resolve to a public (non-private/loopback/
  link-local/reserved) address (mirrors `services/search.py::_assert_public_host`; resolution
  failure skips the check). It runs on both create (ProviderCreate `model_validator`) and
  update (the effective-state review-fix block), raising 422 on violation. The new
  `ALLOW_PRIVATE_PROVIDER_URLS` flag defaults to `true` (local LM Studio-style providers keep
  working); set `false` only on locked-down deployments.

## Auth hardening — claims + policy (audit INFO)

Audit INFO items, landed together.

- **JWT `iss`/`aud` claims + validation.** Both `create_access_token` and
  `create_refresh_token` now stamp `"iss": settings.JWT_ISSUER` (`"llm-gateway"`) and
  `"aud": settings.JWT_AUDIENCE` (`"llm-gateway-api"`) onto the payload (next to the
  existing `iat`). `get_current_user` and `/auth/refresh` decode with
  `issuer=settings.JWT_ISSUER, audience=settings.JWT_AUDIENCE`, so tokens from another
  issuer (or for another audience) are rejected with the standard 401s — same try/except
  behavior, no new error paths. **Existing sessions are invalidated once:** previously-issued
  tokens lack the claims, so every client re-logs in a single time after deploy; nothing
  else changes (tokens refresh normally afterwards).
- **Registration password policy.** `routers/auth.py` `UserCreate._password_length` now
  requires `len >= 8` **and** at least one letter **and** at least one digit; violation
  returns 422 `"password must be at least 8 characters with at least one letter and one
  number"`. Login is untouched — it still accepts whatever credentials existing accounts
  were created with (only `UserCreate` validates).
- **Per-user SSE concurrency cap.** New `core/stream_guard.py`: an in-memory per-user
  counter guarded by an `asyncio.Lock`, capped at `settings.MAX_CONCURRENT_STREAMS` (default
  4). `acquire_stream_slot(user_id)` runs in each router handler **before** the
  `StreamingResponse` is created (a 429 "too many concurrent streams" is a real HTTP
  response, not an in-stream SSE error); `release_stream_slot(user_id)` runs in each
  generator's `finally` (fires on normal completion, error, and client disconnect). Wired
  into `/v1/chat/completions`, `/v1/agent/chat`, `/v1/research/{id}/stream`, and
  `/v1/trainings/{id}/stream`. In-memory is correct because the backend is a single
  container; a horizontally-scaled deployment would need a shared counter. Acquire/release
  stays 1:1 even when the stream never starts: `stream_training` wraps every step between
  the acquire and the `StreamingResponse` (Redis pubsub setup + ownership check) in
  `try/except BaseException` that closes any created pubsub and releases the slot before
  re-raising; `stream_research` wraps its ownership check the same way (its pubsub setup
  lives inside the generator, already covered by the relay `finally`).
- **Langfuse content documentation.** `README.md` notes that full chat content is sent to
  Langfuse unless a message is sent with `private: true` (metadata-only), and that
  deployments not using Langfuse should remove the `LANGFUSE_*` keys from `.env`.
- **Refresh tokens bound to an optional client `device_id` (replay protection).**
  `refresh_tokens.device_id` (`String(128)`, nullable — migration `b83db11a1dc0`) stores the
  client-generated device id the token was minted for. `/auth/login` and `/auth/refresh`
  accept an optional `device_id`; the rotated token carries the SAME binding as the row it
  replaced. `/auth/refresh` rejects with 401 "invalid refresh token" when a bound row is
  presented without an exact `device_id` match (missing or mismatched — both are 401).
  Legacy rows with `device_id IS NULL` accept any caller, so pre-existing tokens keep
  working. The `sub` cross-check, DB expiry check, JWT decode, and rotation behavior are
  unchanged.

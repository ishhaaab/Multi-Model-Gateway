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

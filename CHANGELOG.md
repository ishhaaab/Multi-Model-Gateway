# Changelog

## 2026-08-13 — Unified "Models" window (Local | Cloud)

- Frontend: unified single "Models" window — Local | Cloud tabs, Cloud = two-pane HF browser (per-quant GGUF fit), Local = installed-model fit list, compact hardware box at bottom. Removed the separate Cookbook page.

## 2026-08-13 — HF model browser UI (two-pane)

- Web SPA — new `/models` two-pane HF model browser: catalog list (search + 10/25/50 dropdown) fed by `GET /v1/hf/models`, detail pane fed by `GET /v1/hf/models/{repo_id}` (stats, description, PARAMS/ARCH/DOMAIN/FORMAT metadata, capability pills, per-quant GGUF fit verdicts + rationale with a shared context-token selector). Download/install pipeline deferred — the Download affordance renders disabled with a "coming soon" hint. Cookbook HF rows navigate into the browser (`/models?repo=<id>`). Types `HfFitVerdict`/`HfQuantOption`/`HfModelDetail`/`HfModelSummary` + `hfApi.detail` added; route + sidebar "Models" nav item.

## 2026-08-13 — HF model browser follow-up (review fixes)

- Backend: GGUF header walker (`_read_gguf_value`) now skips ARRAY KV payloads in full — fixed-size scalar arrays jump `count × elem_size`, string arrays walk each element — instead of truncating at 4096 elements, which drifted every later key offset on large arrays. Array values are never materialized (the fit fields are all scalars/strings); a payload that overruns the buffer fails the parse instead of silently truncating.
- Tests: `backend/tests/test_hf_detail.py` +3 cases (large scalar array >4096 followed by scalar keys, uneven string array, truncated array payload → None). Full suite 179 tests (was 176).

## 2026-08-13 — HF model browser + GGUF-accurate fit (F1)

- Backend: new `GET /v1/hf/models/{repo_id}` (auth) — HF repo stats (downloads/likes/params/description), capability + format pills, and per-quant VRAM fits computed from each GGUF's own header (real n_layer/n_embd/n_head[_kv], exact KV formula, 10% safety margin; verdicts fits_fully / fits_cpu_offload / likely_too_large / cpu_only / unknown). Header reads are 4MB Range requests cached in-process (600s), capped at 12 quants.
- Backend: `gguf` dependency added (header parser; manual KV walker because GGUFReader needs a real path and reads all tensor data); `HF_TOKEN` / `KV_CACHE_BYTES_PER_ELEMENT` / `FIT_SAFETY_MARGIN` settings.
- Tests: `backend/tests/test_hf_detail.py` (18 cases: quant grouping/regex, fit arithmetic, header walker, mocked end-to-end detail). Full suite 176 tests (was 158).

## 2026-08-13 — Unified model-fit cookbook (Hugging Face tab)

- Backend: new `GET /v1/hf/models` (auth) — searches the Hugging Face Hub API (downloads-sorted, in-process 10-min TTL cache) and fit-scores the results with the same `estimate_fit`/verdict ranking as the local cookbook (`build_hf_cookbook` shares `_VERDICT_RANK`).
- Web SPA — Cookbook page: Local / Hugging Face source tabs; HF tab adds a search box + result-count dropdown and renders the same verdict table (params/downloads/likes sub-label, pipeline tag in Notes); recommendation banner stays local-only.
- Tests: `backend/tests/test_fit_score.py` (7 cases: safetensors parsing, model-id fallback, fetch-failure → [], cache hit, cookbook scoring/sorting, DEFAULT_BYTES_PER_PARAM). Full suite 158 tests.

## 2026-08-11 — Memory files (M2)

- Memory files M2: background curation pipeline (arq job, rule-based curation prompt, strict op parsing, versioned apply with retry-once, private chats excluded).

## 2026-08-11 — Memory files (M1)

- Memory files M1: per-user file store (`memory_files` table), 5 versioned memory tools (read/write/str_replace/append/delete), Tier-1 index + Tier-1.5 injection into chat/agent prompts.

## 2026-08-11 — New first-party agent tools

- Agent tools: added current_datetime, search_conversations, and generate_image (ComfyUI-backed, ownership-aware).
- Agent tool: safe calculate evaluator (AST whitelist — no eval/exec).

## 2026-08-11 — Maintainability (M1 + M4)

- Maintainability: pinned backend dependencies via pip-compile (requirements.in); added CI schema-drift guard + test workflow (M1, M4). The guard's first run uncovered pre-existing drift (ix_research_jobs_user_id / ix_tool_permissions_user_id) which was reconciled by restoring `index=True` on both `user_id` model columns — no new migration needed, the indexes already exist from the original migrations.

## 2026-08-11 — Auth hardening (INFO)

- Auth hardening (INFO): JWT iss/aud claims + validation, registration password policy, per-user SSE stream cap, Langfuse content documentation.
- Auth hardening (INFO): refresh tokens bound to a client device_id (replay protection); legacy tokens unaffected.
- SSE stream-slot leak fix (review HIGH): trainings/research stream setup failures (Redis, DB, cancellation) now release the reserved slot before re-raising, so acquire/release stays 1:1.
- Follow-up: trainings stream setup releases the slot unconditionally even when pubsub unsubscribe/close itself raises — cleanup is best-effort (swallowed + logged) and can no longer mask the release.

## 2026-08-11 — Config/infra hardening (S-B)

- Config/infra hardening: prometheus+grafana bound to loopback; Caddy security headers (CSP/X-Frame/etc.); DEBUG refused in production; provider base_url scheme validation + opt-in private-URL guard (S-B).

## 2026-08-11 — Backend auth hardening (S-A)

- Backend — consistent 401s for missing/invalid credentials, refresh-token sub cross-check, authed aspect-ratios, generic provider-test errors, trainings detail path leak removed, JWT iat.

## 2026-08-11 — Data integrity fixes (D4 + R7)

- Backend — optional limit/offset pagination on convo/presets/templates (D4); hourly expired refresh-token sweep via arq cron (R7).

## 2026-08-11 — Reliability fixes (R3–R6)

- Backend — honest local token counts via token_provenance + off-path tokenize sync (R3); research rejects without a capable model and stores the resolved model (R4); strict ComfyUI anchor detection + upload validation (R5); search degradation is surfaced via metric + honest tool text (R6).

## 2026-08-11 — Backend cleanup (D1–D3, M2–M3, S6)

- Backend cleanup: unified convo ownership checks (D1); OpenRouter models list timeout (D2); memories migration downgrade (D3); removed stale Gemini references (M2); parameterized POSTGRES_USER/POSTGRES_DB (M3); documented MCP_SERVERS operator-trust boundary (S6).

## 2026-08-11 — Security hardening (S2–S7)

- S2: /metrics gated behind METRICS_TOKEN (Bearer; 404 when unset); backend port bound to 127.0.0.1
- S3: removed unauthenticated Caddy /view* proxy; ComfyUI files served via authed GET /v1/images/file (ownership + traversal guards)
- S4: /auth/register no longer reveals whether an email is registered
- S5: rate limiter honors X-Forwarded-For only from TRUSTED_PROXIES (default Docker subnet 172.16.0.0/12)
- S7: REGISTRATION_ENABLED flag (false = signups disabled; register your account first)
- Web SPA — authed image loading (S3 compliance): images fetched via Authorization header as blob URLs (AuthedImage); removed obsolete ComfyUI host rewriting; register page handles generic signup errors + 'registration disabled' (S4/S7)
- Web SPA — Providers settings screen (BYO-key): list/create/edit/delete/test providers against /v1/providers; masked keys; role + type badges; default + enabled toggles.
- Web SPA — LoRA Training screen: dataset zip upload, base model/steps/LR/resolution, live SSE progress, cancel, artifact download, sample preview, and a trained-LoRA picker on image generation; backend adds authed GET /v1/trainings/{id}/sample.
- Review fixes: provider PATCH now enforces base_url for openai_compatible providers; fetchBlob treats every 401 as session expiry (incl. post-refresh retry); use-training-job state updaters guarded against stale/cancelled writes.

## 2026-08-11 — Reliability fixes (R1 + R2)

- Backend — agent loop no longer holds the DB connection for the whole run (R1); agent messages pruned before tool rounds and context-overflow degrades to a tool-less final answer with truncated=True (R2).

## Earlier work (summary)

- BYO-key provider system + provider routing (Phase 1/1b)
- Idempotent setup scripts (Phase 2)
- LoRA training pipeline with ai-toolkit worker (Phase 3) + SD1/SDXL support
- Docker data disk compaction (~57 GB → ~21 GB)

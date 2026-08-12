# Changelog

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

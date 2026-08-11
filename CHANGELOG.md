# Changelog

## 2026-08-11 — Security hardening (S2–S7)

- S2: /metrics gated behind METRICS_TOKEN (Bearer; 404 when unset); backend port bound to 127.0.0.1
- S3: removed unauthenticated Caddy /view* proxy; ComfyUI files served via authed GET /v1/images/file (ownership + traversal guards)
- S4: /auth/register no longer reveals whether an email is registered
- S5: rate limiter honors X-Forwarded-For only from TRUSTED_PROXIES (default Docker subnet 172.16.0.0/12)
- S7: REGISTRATION_ENABLED flag (false = signups disabled; register your account first)
- Web SPA — authed image loading (S3 compliance): images fetched via Authorization header as blob URLs (AuthedImage); removed obsolete ComfyUI host rewriting; register page handles generic signup errors + 'registration disabled' (S4/S7)
- Web SPA — Providers settings screen (BYO-key): list/create/edit/delete/test providers against /v1/providers; masked keys; role + type badges; default + enabled toggles.

## Earlier work (summary)

- BYO-key provider system + provider routing (Phase 1/1b)
- Idempotent setup scripts (Phase 2)
- LoRA training pipeline with ai-toolkit worker (Phase 3) + SD1/SDXL support
- Docker data disk compaction (~57 GB → ~21 GB)

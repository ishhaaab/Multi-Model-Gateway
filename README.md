# llm-gateway

A self-hosted inference orchestration layer — a personal mini-OpenRouter that routes chat requests across local and cloud AI providers, with auth, conversation persistence, semantic memory, image generation, and full observability.

> **Status:** All core features built. Backend complete; frontend client in development.

---

## Quickstart (5 minutes)

**Prereqs:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) or Docker Engine (Linux), and git. Optional — for local models — [LM Studio](https://lmstudio.ai/) (chat / prompt rewriting / embeddings) on port 1234, ComfyUI on 8188, and Ollama on 11434.

1. **Clone and run the setup script** — it generates `.env` from `.env.example` (random secrets, your local model ids), checks Docker, and starts the stack:
   ```bash
   git clone https://github.com/ishaab/llm-gateway
   cd llm-gateway
   .\setup.ps1        # Windows PowerShell
   # or
   ./setup.sh         # Linux / macOS / WSL
   ```
   Already have a `.env`? The script detects it and leaves it unchanged.

   The setup scripts accept two flags: `-SkipStart` / `--skip-start` prepares `.env` without starting Docker (`.\setup.ps1 -SkipStart`, `./setup.sh --skip-start`), and `-NonInteractive` / `--non-interactive` skips the prompts for CI/automation (`.\setup.ps1 -NonInteractive`, `./setup.sh --non-interactive`).

   > Run setup before `docker compose up` so `monitoring/metrics_token` exists — otherwise Docker creates it as a directory and Prometheus can't read the token.
2. **Open the API docs:** http://localhost:2727/docs (Swagger UI).
3. **Register an account** (`POST /auth/register`).
4. **Add your providers** — see [Adding providers](#adding-providers). A "Local (LM Studio)" provider row is seeded automatically when `LM_URL` is set.
5. **Start chatting.**

> From a phone over Tailscale, reach the app through Caddy on port 80 (e.g. `http://<tailscale-ip>`); keep port 2727 internal.

---

## Architecture

![Architecture](arch-dia-4.png)


---

## Features

- **Provider Routing** — Automatically routes requests to the best provider based on privacy needs, task type, model name, and context length. Sensitive data stays local; coding and long tasks go to OpenRouter.
- **Semantic Memory (RAG)** — Every message is embedded (Ollama `nomic-embed-text`, 768-dim) and stored in pgvector. On each turn, the top-3 semantically similar past messages are injected as context.
- **Parameter Presets** — Save and reuse model parameter profiles (temperature, top_k, top_p, min_p, repeat_penalty, etc.). Default preset created on registration.
- **SDXL Prompt Templates** — Rewrite natural language prompts into structured SDXL tags using a dedicated LLM (Qwen 2.5 on LM Studio). User-definable template structures.
- **ComfyUI Image Generation** — Generate images via ComfyUI workflows with optional prompt rewriting. Poll job status and retrieve results.
- **JWT Authentication** — Access token (60 min) + refresh token (7 days, persisted) flow. Password hashing with bcrypt.
- **Rate Limiting** — Sliding-window rate limit per user via Redis sorted sets (30 req/min default, configurable).
- **Observability** — Prometheus metrics (request count, latency, tokens/sec by provider/model) + Langfuse Cloud LLM tracing.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Async API gateway |
| Database | PostgreSQL 16 + pgvector | Relational data + vector embeddings |
| Cache | Redis 7 | Rate limiting |
| Auth | JWT (python-jose) + bcrypt (passlib) | Authentication |
| ORM | SQLAlchemy 2.x (async) + Alembic | Data layer + migrations |
| Providers | LM Studio, Ollama, OpenRouter, ComfyUI | Inference backends |
| Image Gen | ComfyUI + Qwen 2.5 (prompt rewriting) | Text-to-image |
| Observability | Prometheus + Grafana + Langfuse | Metrics, dashboards, LLM tracing |
| Reverse Proxy | Caddy 2 | HTTPS, path-based routing |
| Containerization | Docker + Docker Compose | Service orchestration |

---

## API Endpoints

### Auth

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/auth/register` | Register a new user | No |
| POST | `/auth/login` | Login, get access + refresh tokens | No |
| POST | `/auth/refresh` | Exchange refresh token for new access token | No |
| POST | `/auth/logout` | Invalidate a refresh token | Yes |

### Chat

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/chat/completions` | SSE-streamed chat completion with auto-routing | Yes |

### Models

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/v1/models` | List models loaded in LM Studio | No |
| GET | `/v1/openrouter/models` | List free OpenRouter models | No |

### Conversations

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/convo` | Create conversation | Yes |
| GET | `/v1/convo` | List user's conversations | Yes |
| GET | `/v1/convo/{id}` | Get messages in a conversation | Yes |
| PATCH | `/v1/convo/{id}` | Rename conversation | Yes |
| DELETE | `/v1/convo/{id}` | Delete conversation | Yes |

### Presets

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/presets` | Create a parameter preset | Yes |
| GET | `/v1/presets` | List user's presets | Yes |
| GET | `/v1/presets/{id}` | Get preset details | Yes |
| PATCH | `/v1/presets/{id}` | Update preset | Yes |
| DELETE | `/v1/presets/{id}` | Delete preset | Yes |

### Prompt Templates

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/templates` | Create a prompt template | Yes |
| GET | `/v1/templates` | List user's templates | Yes |
| GET | `/v1/templates/{id}` | Get template details | Yes |
| PATCH | `/v1/templates/{id}` | Update template | Yes |
| DELETE | `/v1/templates/{id}` | Delete template | Yes |
| POST | `/v1/templates/rewrite` | Rewrite a prompt for SDXL | Yes |

### Images

| Method | Path | Description | Auth |
|---|---|---|---|
| POST | `/v1/images/generate` | Generate image via ComfyUI | Yes |
| GET | `/v1/images/status/{prompt_id}` | Poll generation status | Yes |

### Health

| Method | Path | Description | Auth |
|---|---|---|---|
| GET | `/health` | Health check | No |
| GET | `/metrics` | Prometheus metrics | Bearer token (`METRICS_TOKEN`) |

---

## Project Structure

```
llm-gateway/
  .env                          # Environment variables (gitignored)
  docker-compose.yml            # Orchestrates 6 services
  arch-dia.png                  # Architecture diagram
  backend/
    Dockerfile                  # Python 3.11-slim, uvicorn --reload
    requirements.txt            # Python dependencies
    alembic.ini                 # Database migration config
    alembic/                    # Migration versions (6 migrations)
    app/
      main.py                   # FastAPI entry point, middleware, router registration
      db.py                     # Async SQLAlchemy engine + session
      core/
        config.py               # Pydantic settings from .env
        metrics.py              # Prometheus + Langfuse observability
        redis.py                # Async Redis connection pool
        security.py             # JWT creation/verification, password hashing
      middleware/
        ratelimit.py            # Sliding-window rate limiter (Redis)
      models/
        users.py
        conversations.py
        messages.py
        refresh_tokens.py
        memories.py
        presets.py
        templates.py
      routers/
        auth.py                 # Registration, login, token refresh, logout
        chat.py                 # SSE streaming chat completion
        convo.py                # Conversation CRUD
        images.py               # ComfyUI image generation
        models.py               # Model listing (LM Studio + OpenRouter)
        presets.py              # Preset CRUD
        templates.py            # Prompt template CRUD + rewrite
      services/
        router.py               # Provider routing engine
        convo.py                # Conversation management + semantic memory
        memory.py               # pgvector embeddings + retrieval
        template.py             # SDXL prompt rewriting
        comfy.py                # ComfyUI image generation
  caddy/
    Caddyfile                   # Reverse proxy config
  monitoring/
    prometheus.yml              # Prometheus scrape config
  workflows/
    t2i-default.json            # Default ComfyUI workflow
```

---

## Running Locally

**Prerequisites:**
- Docker Desktop
- LM Studio running on port 1234 with at least one chat model loaded (chat + prompt rewriting), plus an embedding model matching `LM_EMBED_MODEL` (default `text-embedding-nomic-embed-text-v1.5`)
- ComfyUI running on port 8188 (optional, for image generation)
- Ollama on port 11434 (optional)

**Setup:**

1. Clone the repo:
   ```bash
   git clone https://github.com/ishaab/llm-gateway
   cd llm-gateway
   ```

2. Create a `.env` file (see [Environment Variables](#environment-variables)).

3. Start everything:
   ```bash
   docker compose up --build
   ```

4. Verify:
   - Health check: `http://localhost:2727/health`
   - API docs (Swagger UI): `http://localhost:2727/docs`
   - Prometheus: `http://localhost:9090`
   - Grafana: `http://localhost:3000` (admin user `admin`, password from `GRAFANA_ADMIN_PASSWORD` in your generated `.env` — the setup script generates one if you don't set it)

---

## Docker Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | internal | Persistent storage + pgvector extension |
| `redis` | `redis:7-alpine` | internal | Rate limiting backend |
| `backend` | Build from `./backend/Dockerfile` | `127.0.0.1:2727:8000` (loopback-only) | FastAPI application |
| `worker` | Build from `./backend/Dockerfile` | internal | arq deep-research job worker (same image as backend) |
| `searxng` | `searxng/searxng` | internal | Optional self-hosted search for `web_search` + research (start with `--profile search`) |
| `prometheus` | `prom/prometheus` | `9090:9090` | Metrics collection |
| `grafana` | `grafana/grafana` | `3000:3000` | Dashboards (admin user `admin`; password = `GRAFANA_ADMIN_PASSWORD` in `.env`) |
| `caddy` | `caddy:2` | `80:80` | Reverse proxy (strips `/api` prefix) |

---

## Caddy Reverse Proxy

The Caddyfile routes:
- `http://<host>/api/*` -> strips `/api`, proxies to `backend:8000`
- `http://<host>/` (WebSocket) -> proxies to `host.docker.internal:6969`
- `http://<host>/` (non-WebSocket) -> proxies to `host.docker.internal:6969`

Auto HTTPS is disabled. The frontend should call `/api/v1/*` and Caddy will forward it as `/v1/*` to the backend.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LM_URL` | Yes | LM Studio base URL (chat + prompt rewriting + embeddings) |
| `LM_DEFAULT_MODEL` | Yes | LM Studio model for SDXL rewriting |
| `COMFY_URL` | No | ComfyUI base URL for image generation (default: `http://host.docker.internal:8188`) |
| `OPENROUTER_API_KEY` | No | OpenRouter API key |
| `OPENROUTER_DEFAULT_MODEL` | No | Default OpenRouter model |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password, required by docker-compose (and embedded in `DATABASE_URL`) |
| `REDIS_URL` | Yes | Redis connection string |
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | Yes | JWT algorithm (`HS256`) |
| `ACCESS_TOKEN_EXPIRY_MINUTES` | Yes | Access token TTL (60) |
| `REFRESH_TOKEN_EXPIRY_DAYS` | Yes | Refresh token TTL (7) |
| `GRAFANA_ADMIN_PASSWORD` | Yes | Grafana admin login password, required by docker-compose; the setup script generates one if you don't set it |
| `METRICS_TOKEN` | No | Bearer token for `GET /metrics`; empty disables the endpoint (fail-closed). The setup scripts generate one and mirror it to `monitoring/metrics_token` for Prometheus |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse Cloud public key |
| `LANGFUSE_SECRET_KEY` | No | Langfuse Cloud secret key |
| `LANGFUSE_BASE_URL` | No | Langfuse endpoint |

---

## Provider Routing Logic

The routing engine (`services/router.py`) decides where to send each request using this priority:

1. **`private: true`** in request -> Always route to local LM Studio (privacy override)
2. **`provider: "local"`** in request -> Route to local LM Studio
3. **Model name contains `/`** (e.g. `openrouter/owl-alpha`) -> Route to OpenRouter
4. **`provider: "openrouter"`** in request -> Route to OpenRouter
5. **Coding keywords in last message** (e.g. `script`, `code`, `function`, `debug`, `python`, `c++`, `javascript`) -> Route to OpenRouter
6. **More than 80 messages in conversation** -> Route to OpenRouter (longer context windows)
7. **Default** -> Route to local LM Studio

The chat endpoint receives `provider`, `model`, `private` fields in the request body to control this behavior.

---

## Adding providers

The gateway is bring-your-own-key: after registering, create provider rows via `POST /v1/providers` (or the /docs UI). Supported types:

| `type` | Use for |
|---|---|
| `openai_compatible` | Any OpenAI-wire endpoint — LM Studio, Ollama, Groq, vLLM, OpenCode Go, ... |
| `openai` | OpenAI cloud |
| `anthropic` | Anthropic |
| `google` | Google Gemini |
| `openrouter` | OpenRouter |

Keys are stored encrypted (Fernet) and are **write-only** — responses only ever show a masked suffix (`api_key_masked`). Each role (`local` / `cloud`) can have one default provider; a request can also pin a specific provider by passing its `provider_id` in the chat/agent body (overrides every routing heuristic).

Example — an OpenAI-compatible endpoint (LM Studio, Ollama, Groq, ...):

```json
{
  "name": "LM Studio",
  "type": "openai_compatible",
  "role": "local",
  "base_url": "http://host.docker.internal:1234",
  "api_key": "",
  "default_model": "qwen2.5-7b-instruct",
  "is_default": true
}
```

`base_url` gets `/v1` appended automatically when it's missing (so `http://host:1234` and `http://host:1234/v1` both work). A "Local (LM Studio)" row is seeded for you when `LM_URL` is set, and an "OpenRouter" row only when an OpenRouter key is configured. If you never create rows, the gateway falls back to the legacy env-var configuration (`LM_URL`, `LM_CHAT_MODEL`, `OPENROUTER_API_KEY`, ...).

---

## Training LoRAs

Fine-tune an image LoRA from a zip of images and use it on image generation — the gateway
runs ai-toolkit in a dedicated GPU worker and injects the trained LoRA into ComfyUI
workflows automatically.

**Prerequisites:**

- An NVIDIA GPU on the host (the `trainer` compose service needs `gpus: all`).
- `HF_TOKEN` in `.env` if you train `flux-dev` (it's a gated model on Hugging Face; SDXL
  and SD1 train without it).
- `COMFY_LORA_DIR` in `.env` pointing at your ComfyUI `models/loras` folder — the backend
  copies finished LoRAs there so ComfyUI can load them (when unset, image generation with a
  `training_id` returns a 400).
- **Point at local models to skip the Hugging Face downloads.** For SDXL set
  `SDXL_MODEL_PATH` in `.env` to a host folder containing your SDXL model — either a
  diffusers-format model folder, or a directory with a single-file `.safetensors`
  checkpoint (set `SDXL_MODEL_NAME` to the filename, e.g. `sdxl-base.safetensors`). The
  folder is bind-mounted into the trainer at `/models/sdxl`; ai-toolkit loads single-file
  checkpoints directly, no conversion needed. For SD1 (stable-diffusion-1.x) the pattern
  is identical with `SD1_MODEL_PATH` / `SD1_MODEL_NAME` (mounted at `/models/sd1`). Leave
  the vars unset to fall back to the HF model (a one-time ~7GB / ~4GB download).

**`base_model` values:**

- `flux-dev` — FLUX.1-dev (gated; needs `HF_TOKEN`). Native resolution 1024, capped at
  1024 server-side.
- `sdxl` — Stable Diffusion XL. Honors the requested `resolution` as given (default 1024).
- `sd1` — Stable Diffusion 1.x (e.g. SD1.5 checkpoints like Realistic Vision). Native
  resolution 512 — use `resolution=512` (the default for sd1, capped at 1024) and smaller
  image counts for a 6GB GPU.

Adding a future model type is a three-part pattern: add the name to the `base_model`
Literal in `backend/app/routers/trainings.py`, add a branch in
`backend/app/services/trainer.py` `_build_config` (model name_or_path, `is_flux`/`is_xl`
arch flags, sample params), and add `*_MODEL_PATH`/`*_MODEL_NAME` settings in
`backend/app/core/config.py` plus a compose mount if local checkpoints should be
supported.

**The two LoRA folder variables:**

- `COMFY_LORA_DIR` is the **host** path of your ComfyUI `models/loras` folder. docker-compose
  bind-mounts it into the backend container — it never has to exist inside the container.
- `COMFY_LORA_CONTAINER_PATH` is the **container** path the backend writes trained LoRAs to
  (default `/comfy-loras`, which matches the compose mount target). In Docker you set
  `COMFY_LORA_DIR` and leave the container path at its default. If you run the backend on the
  host directly (no Docker), set **both** to the same real folder.

**The flow:**

1. **Upload a dataset** — `POST /v1/trainings` (multipart): `name`, `base_model`
   (`flux-dev` | `sdxl` | `sd1`), `dataset` (a zip of **3+ images**; optional per-image
   `{name}.txt` caption files ride along), plus `steps`, `learning_rate`, and
   `resolution` if you want to override the defaults (1000 / 1e-4 / 1024, or 512 for
   `sd1`). `resolution` is the training width=height in pixels — use 512 for small GPUs;
   FLUX is capped at 1024 and SD1 at 1024 server-side.
2. **Watch it train** — `GET /v1/trainings` lists your jobs; `GET /v1/trainings/{id}/stream`
   streams SSE progress events (`{"type":"progress","stage","progress"}` then
   `{"type":"done","artifact_filename"}`); `POST /v1/trainings/{id}/cancel` stops a run.
3. **Download the artifact** — `GET /v1/trainings/{id}/artifact` returns the trained
   `.safetensors`.
4. **Use it on generation** — pass `training_id` on `POST /v1/images/generate`; the
   gateway copies the LoRA into `COMFY_LORA_CONTAINER_PATH` (the bind-mounted folder) and
   injects a ComfyUI `LoraLoader` node, so the result reflects your trained subject. The
   response includes the loaded `lora` filename.

Training jobs live in the `trainings` table (migration `d4a8b2c6f9e7`); artifacts are
stored under the `training_data` volume. The worker does **not** hot-reload — restart the
`trainer` service after changing training code.

---

## Authentication Flow

1. **Register** (`POST /auth/register`) -> Creates user, default preset, default SDXL template.
2. **Login** (`POST /auth/login`) -> Returns `access_token` (60 min) + `refresh_token` (7 days).
3. **Use API** -> Send `Authorization: Bearer <access_token>` header on every protected endpoint.
4. **Refresh** (`POST /auth/refresh`) -> Exchange `refresh_token` for a new `access_token`.
5. **Logout** (`POST /auth/logout`) -> Invalidates the specific `refresh_token` in the database.

---

## Image Generation Flow

1. User sends `POST /v1/images/generate` with a natural language prompt.
2. If `rewrite: true`, the prompt is rewritten using LM Studio Qwen 2.5 into comma-separated SDXL tags via a template structure.
3. The rewritten prompt is submitted to ComfyUI (`host.docker.internal:8188`) as a KSampler workflow.
4. The endpoint returns a `prompt_id` for polling.
5. Client polls `GET /v1/images/status/{prompt_id}` until `status: "complete"`, then renders image URLs from the response.

---

## Semantic Memory (RAG)

- Every user and assistant message is embedded via Ollama `nomic-embed-text:latest` into a 768-dim vector.
- Embeddings are stored in the `memories` table via pgvector.
- On each new message in a conversation, the top 3 semantically similar past messages (lowest cosine distance `<=>`) are injected as a `system` context message before the conversation history.

---

## Presets

Presets are reusable parameter profiles for LLM generation. Each user has their own presets. The default preset has:

| Field | Default |
|---|---|
| `temperature` | 0.8 |
| `context_overflow` | `truncate_middle` |

Additional supported fields: `system_prompt`, `token_limit`, `stop_strings` (array), `top_k`, `top_p`, `min_p`, `repeat_penalty`.

Local provider parameters (`top_k`, `min_p`, `repeat_penalty`) are sent via `extra_body` in the OpenAI-compatible API call.

---

## Observability

- **Prometheus** scrapes `backend:8000/metrics` every 15s.
- Custom metrics: `chat_requests_total`, `chat_latency_seconds`, `tokens_per_second`, `prompt_tokens_total`, `active_conversations_total`.
- **Grafana** runs on port 3000.
- **Langfuse** traces every chat generation with input, output, model, provider, latency, and token metadata.

---

## Contributing

This is a personal project. Issues and PRs are welcome.

## License

MIT

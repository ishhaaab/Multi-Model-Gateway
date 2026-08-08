# llm-gateway

A self-hosted inference orchestration layer — a personal mini-OpenRouter that routes chat requests across local and cloud AI providers, with auth, conversation persistence, semantic memory, image generation, and full observability.

> **Status:** All core features built. Backend complete; frontend client in development.

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
| GET | `/metrics` | Prometheus metrics | No |

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
- LM Studio running with at least one model loaded on port 8008
- Ollama running with `nomic-embed-text` pulled on port 11434
- ComfyUI running on port 8188 (optional, for image generation)

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
   - Grafana: `http://localhost:3000` (admin/admin)

---

## Docker Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | internal | Persistent storage + pgvector extension |
| `redis` | `redis:7-alpine` | internal | Rate limiting backend |
| `backend` | Build from `./backend/Dockerfile` | `2727:8000` | FastAPI application |
| `prometheus` | `prom/prometheus` | `9090:9090` | Metrics collection |
| `grafana` | `grafana/grafana` | `3000:3000` | Dashboards (admin/admin) |
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
| `LOCAL_URL` | Yes | Ollama base URL (default: `http://host.docker.internal:11434/v1`) |
| `LOCAL_DEFAULT_MODEL` | Yes | Default local chat model |
| `LM_URL` | Yes | LM Studio base URL (for prompt rewriting) |
| `LM_DEFAULT_MODEL` | Yes | LM Studio model for SDXL rewriting |
| `OPENROUTER_API_KEY` | No | OpenRouter API key |
| `OPENROUTER_DEFAULT_MODEL` | No | Default OpenRouter model |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `GEMINI_MODEL` | No | Default Gemini model |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `SECRET_KEY` | Yes | JWT signing secret |
| `ALGORITHM` | Yes | JWT algorithm (`HS256`) |
| `ACCESS_TOKEN_EXPIRY_MINUTES` | Yes | Access token TTL (60) |
| `REFRESH_TOKEN_EXPIRY_DAYS` | Yes | Refresh token TTL (7) |
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

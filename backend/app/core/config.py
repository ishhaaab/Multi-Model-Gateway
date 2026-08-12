import ipaddress
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    LM_URL: str
    LM_DEFAULT_MODEL: str
    LM_CHAT_MODEL: str = ""   # default chat model on LM Studio; empty => falls back to LM_DEFAULT_MODEL

    COMFY_URL: str = "http://host.docker.internal:8188"   # ComfyUI server for image generation
    IMAGE_FILE_TTL_SECONDS: int = 604800   # ownership TTL for generated image filenames

    # HOST path of your ComfyUI models/loras folder; used by docker-compose as
    # the bind source mounted into the backend container at
    # COMFY_LORA_CONTAINER_PATH. When unset, using a trained LoRA on image
    # generation returns a 400 (the mount isn't configured).
    COMFY_LORA_DIR: str = ""

    # path INSIDE the container the backend writes trained LoRAs to; must match
    # the compose mount target for ${COMFY_LORA_DIR}. When running the backend
    # on the host directly, set both to the same real folder.
    COMFY_LORA_CONTAINER_PATH: str = "/comfy-loras"

    # HOST path to your SDXL model for training (a diffusers-format folder OR
    # a directory containing a single-file .safetensors checkpoint). Mounted
    # into the trainer container at /models/sdxl. Leave empty to fall back to
    # the Hugging Face model (large download — not recommended).
    SDXL_MODEL_PATH: str = ""

    # optional filename inside SDXL_MODEL_PATH when it points at a directory of
    # checkpoints (e.g. "sdxl-base.safetensors").
    SDXL_MODEL_NAME: str = ""

    # HOST path to your SD1 (stable-diffusion-1.x) model for training (a
    # diffusers-format folder OR a directory containing a single-file
    # .safetensors checkpoint). Mounted into the trainer container at
    # /models/sd1. Leave empty to fall back to the Hugging Face model
    # (~4GB download — not recommended).
    SD1_MODEL_PATH: str = ""

    # optional filename inside SD1_MODEL_PATH when it points at a directory of
    # checkpoints (e.g. "sd15-base.safetensors").
    SD1_MODEL_NAME: str = ""

    TRAINING_ROOT: str = "/app/training_data"   # shared volume for fine-tuning datasets + artifacts
    TRAINING_JOB_TIMEOUT_SECONDS: int = 7200    # max wall-clock for one image-LoRA training run

    
    APP_HOST: str = "0.0.0.0"
    APP_PORT:int=8008
    ENV: str = "dev"   # set to "production" to disable interactive API docs
    DEBUG: bool = False   # when True, echo all SQL (noisy and leaks data; never enable in prod)
    
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    MAX_CONCURRENT_STREAMS: int = 4   # per-user cap on open SSE streams

    METRICS_TOKEN: str = ""   # bearer token for GET /metrics; empty disables the endpoint (fail-closed)

    # comma-separated CIDRs of trusted reverse proxies (e.g. Caddy) whose
    # X-Forwarded-For header the rate limiter may trust
    TRUSTED_PROXIES: str = "172.16.0.0/12"

    # set False to disable open registration (POST /auth/register -> 403)
    REGISTRATION_ENABLED: bool = True

    # provider base_urls may point at private/loopback hosts (e.g. local LM
    # Studio); set False to enforce public-only URLs — breaks local providers,
    # use only on locked-down deployments
    ALLOW_PRIVATE_PROVIDER_URLS: bool = True

    # max recent messages pulled into the prompt as direct context
    # (older turns remain reachable via semantic memory / RAG)
    MAX_HISTORY_MESSAGES: int = 30

    # comma separated list of allowed CORS origins ie the frontend URLs
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    OPENROUTER_DEFAULT_MODEL: str= ""

    # Agent / MCP tools
    AGENT_MAX_ITERATIONS: int = 6        # hard cap on model to tool round-trips per run
    AGENT_TOKEN_BUDGET: int = 24000      # total prompt+completion tokens per agent run
    TOOL_TIMEOUT_SECONDS: int = 30       # per tool execution
    TOOL_RESULT_MAX_CHARS: int = 8000    # tool output fed back to the model is truncated to this
    WEB_SEARCH_MAX_RESULTS: int = 5
    SEARXNG_URL: str = ""                # optional self-hosted SearXNG; empty => DuckDuckGo HTML fallback
    # JSON list of MCP servers to connect at startup, e.g.
    # [{"name":"fs","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","/data"]},
    #  {"name":"remote","transport":"sse","url":"http://mcp-host:8080/sse"}]
    MCP_SERVERS: str = ""

    # Per-user memory files (Claude-style file store, read via agentic tools —
    # NOT the pgvector RAG in services/memory.py). Files are versioned; every
    # mutating memory_* tool takes an if_version and gets a conflict back when
    # the file moved underneath it.
    MEMORY_FILE_CAP_BYTES: int = 32768   # per-file cap; writes at/over cap are rejected, never truncated
    MEMORY_TIER1_5_PATHS: str = "/profile.md,/preferences.md"   # always-injected full files (comma-separated)

    # Deep research 
    RESEARCH_MAX_QUERIES: int = 4          # search queries the planner may issue
    RESEARCH_RESULTS_PER_QUERY: int = 4    # results kept per search
    RESEARCH_MAX_SOURCES: int = 6          # pages actually fetched and read
    RESEARCH_PAGE_MAX_CHARS: int = 6000    # per-page text fed to the synthesizer
    RESEARCH_JOB_TIMEOUT_SECONDS: int = 900

    # Embeddings (LM Studio, OpenAI-compatible /v1/embeddings)
    # Load an embedding model in LM Studio; set this to its API id (see GET /v1/models).
    LM_EMBED_MODEL: str = "text-embedding-nomic-embed-text-v1.5"
    # Must match the memories.embedding column dimension (nomic-embed-text v1.5 = 768).
    # Changing to a different-dimension embedder is a migrate-and-reindex, not just an
    # env tweak — see issues.md CR-12.
    EMBED_DIM: int = 768
    COOKBOOK_CONTEXT_TOKENS: int = 8192    # context size assumed for KV-cache estimates

    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    REDIS_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str

    # JWT issuer/audience claims, validated on every decode. Tokens minted
    # before these existed lack the claims and are rejected once — users
    # simply re-login (documented in backend-roadmap.md).
    JWT_ISSUER: str = "llm-gateway"
    JWT_AUDIENCE: str = "llm-gateway-api"

    # Optional explicit Fernet key (32 urlsafe base64 bytes) for encrypting
    # user-provided provider API keys at rest. Empty => derived from SECRET_KEY
    # via sha256 so existing deployments don't need a new env var.
    KEY_ENCRYPTION_KEY: str = ""

    ACCESS_TOKEN_EXPIRY_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRY_DAYS: int= 7

    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "http://langfuse:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def trusted_proxy_networks(self) -> list:
        """TRUSTED_PROXIES parsed into ipaddress networks. Invalid entries are
        skipped with a warning; an empty list means no proxy is trusted, so
        X-Forwarded-For is ignored entirely."""
        networks = []
        for part in self.TRUSTED_PROXIES.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                networks.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                logger.warning("ignoring invalid TRUSTED_PROXIES entry: %r", part)
        return networks

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()

# Fail boot on a bad config instead of echoing SQL in prod: DEBUG dumps every
# query and leaks data, so it must never combine with ENV=production.
if settings.DEBUG and settings.ENV == "production":
    raise RuntimeError("DEBUG=True is not allowed when ENV=production")


import os

def get_secret(name: str) -> str:
    path = f"/run/secrets/{name}"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    # fall back to a plain env var so the app can run outside Docker
    # (host-side alembic, tests, scripts) where compose secrets don't exist
    env_value = os.environ.get(name.upper())
    if env_value:
        return env_value
    raise RuntimeError(f"Secret '{name}' not found at {path} or in ${name.upper()}")


def get_secret_or_none(name: str) -> str | None:
    """Like get_secret() but returns None instead of raising when the secret
    is absent — for optional secrets the app must boot without."""
    path = f"/run/secrets/{name}"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    env_value = os.environ.get(name.upper())
    return env_value if env_value else None


def get_openrouter_api_key() -> str | None:
    """OpenRouter key if configured, else None. Optional (roadmap S1): the app
    must boot without it; callers decide how to degrade."""
    return get_secret_or_none("openrouter_api_key")
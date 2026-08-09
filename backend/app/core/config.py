from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LM_URL: str
    LM_DEFAULT_MODEL: str
    LM_CHAT_MODEL: str = ""   # default chat model on LM Studio; empty => falls back to LM_DEFAULT_MODEL

    COMFY_URL: str = "http://host.docker.internal:8188"   # ComfyUI server for image generation

    
    APP_HOST: str = "0.0.0.0"
    APP_PORT:int=8008
    ENV: str = "dev"   # set to "production" to disable interactive API docs
    DEBUG: bool = False   # when True, echo all SQL (noisy and leaks data; never enable in prod)
    
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()


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
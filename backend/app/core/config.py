from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LOCAL_URL:str
    LOCAL_DEFAULT_MODEL: str

    LM_URL: str
    LM_DEFAULT_MODEL: str
    LM_CHAT_MODEL: str = ""   # default chat model on LM Studio; empty => falls back to LM_DEFAULT_MODEL

    
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

    # comma-separated list of allowed CORS origins ie the frontend URLs
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    OPENROUTER_DEFAULT_MODEL: str= ""

    DATABASE_URL: str
    REDIS_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str

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
    raise RuntimeError(f"Secret '{name}' not found at {path}")

OLLAMA_API_KEY = get_secret("ollama_api_key")
OPENROUTER_API_KEY = get_secret("openrouter_api_key")
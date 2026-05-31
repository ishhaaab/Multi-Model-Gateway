from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LOCAL_URL:str
    LOCAL_DEFAULT_MODEL: str

    LM_URL: str
    LM_DEFAULT_MODEL: str

    OLLAMA_API_KEY: str= ""

    APP_HOST: str = "0.0.0.0"
    APP_PORT:int=8008
    
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    OPENROUTER_DEFAULT_MODEL: str= ""
    OPENROUTER_API_KEY: str = ""

    GEMINI_MODEL: str= ""
    GEMINI_API_KEY: str = ""

    DATABASE_URL: str
    REDIS_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str

    ACCESS_TOKEN_EXPIRY_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRY_DAYS: int= 7

    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_BASE_URL: str = "http://langfuse:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
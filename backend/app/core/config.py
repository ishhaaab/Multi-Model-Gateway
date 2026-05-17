from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LM_URL:str
    LM_DEFAULT_MODEL: str
    APP_HOST: str = "0.0.0.0"
    APP_PORT:int=8008
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()
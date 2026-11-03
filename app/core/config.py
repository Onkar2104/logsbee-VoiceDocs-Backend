from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    api_v1_prefix: str
    environment: str
    debug: bool

    database_url: str

    logsbee_user_api_base_url: str
    logsbee_user_api_timeout_seconds: float

    # Comma-separated browser origins allowed to call this API.
    cors_origins: str

    # Keep the higher-accuracy multilingual model as the default.
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_cpu_threads: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

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
    cors_origins: str

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    google_token_encryption_key: str
    frontend_app_url: str

    # Transcription
    transcription_provider: str
    whisper_model_size: str
    whisper_device: str
    whisper_compute_type: str
    whisper_cpu_threads: int
    whisper_batch_size: int

    # IndicConformer
    indicconformer_device: str

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
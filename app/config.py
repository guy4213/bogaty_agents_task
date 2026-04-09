from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str = Field(...)
    google_ai_api_key: str = Field(...)
    aws_access_key_id: str = Field(...)
    aws_secret_access_key: str = Field(...)
    s3_bucket_name: str = Field(default="content-engine-prod")
    s3_region: str = Field(default="eu-west-1")

    langsmith_api_key: str = Field(default="")
    langsmith_tracing: bool = Field(default=False)

    claude_model: str = Field(default="claude-sonnet-4-5")
    claude_timeout_sec: int = Field(default=30)
    claude_max_retries: int = Field(default=3)

    image_model: str = Field(default="gemini-2.0-flash-preview-image-generation")
    image_timeout_sec: int = Field(default=45)
    image_max_retries: int = Field(default=3)

    veo_model: str = Field(default="veo-3.1-generate-preview")
    veo_timeout_sec: int = Field(default=90)
    veo_max_retries: int = Field(default=2)
    veo_initial_duration_sec: int = Field(default=8)
    veo_extend_duration_sec: int = Field(default=7)
    veo_target_duration_sec: int = Field(default=29)

    content_validator_min_score: int = Field(default=6)
    max_retries_per_item: int = Field(default=2)
    jaccard_similarity_threshold: float = Field(default=0.7)

    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_window_sec: int = Field(default=120)
    circuit_breaker_recovery_sec: int = Field(default=60)

    dry_run: bool = Field(default=False)  # ← NEW: skip all real API calls

    log_level: str = Field(default="INFO")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
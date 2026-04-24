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

    image_model_first: str = Field(default="imagen-4.0-fast-generate-001")
    image_model_style_ref: str = Field(default="gemini-3.1-flash-image-preview")
    image_timeout_sec: int = Field(default=45)
    image_max_retries: int = Field(default=3)
    # Vertex AI
    vertex_project_id: str = Field(default="")
    vertex_location: str = Field(default="us-central1")
    google_application_credentials: str = Field(default="")
    veo_model: str = Field(default="veo-3.1-generate-preview")
    veo_timeout_sec: int = Field(default=90)
    veo_max_retries: int = Field(default=2)
    veo_initial_duration_sec: int = Field(default=8)
    veo_extend_duration_sec: int = Field(default=7)
    veo_target_duration_sec: int = Field(default=29)
    gcs_bucket_name: str = Field(default="bogaty-492815-video-temp")
    content_validator_min_score: int = Field(default=6)
    max_retries_per_item: int = Field(default=2)
    jaccard_similarity_threshold: float = Field(default=0.7)

    circuit_breaker_threshold: int = Field(default=5)
    circuit_breaker_window_sec: int = Field(default=120)
    circuit_breaker_recovery_sec: int = Field(default=60)

    dry_run: bool = Field(default=False)  # ← NEW: skip all real API calls

    # ── kie.ai / Kling (video generation) ─────────────────────────────────────
    kie_api_key: str = Field(default="", env="KIE_API_KEY")
    kie_api_base: str = Field(default="https://api.kie.ai", env="KIE_API_BASE")
    kie_model_t2v: str = Field(default="kling/v2-1-master", env="KIE_MODEL_T2V")
    kie_model_i2v: str = Field(default="kling/v2-1-master-image-to-video", env="KIE_MODEL_I2V")
    kie_clip_duration: int = Field(default=10, env="KIE_CLIP_DURATION")   # 5 or 10
    kie_poll_interval_sec: int = Field(default=5, env="KIE_POLL_INTERVAL_SEC")
    kie_poll_timeout_sec: int = Field(default=300, env="KIE_POLL_TIMEOUT_SEC")
    video_provider: str = Field(default="kling", env="VIDEO_PROVIDER")    # "kling" | "veo"

    log_level: str = Field(default="INFO")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(_env_file=".env")
    return _settings
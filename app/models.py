from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator
import uuid


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Platform(str, Enum):
    instagram = "instagram"
    tiktok = "tiktok"
    twitter = "twitter"
    telegram = "telegram"
    facebook = "facebook"


class ContentType(str, Enum):
    post = "post"
    reels = "reels"
    story = "story"
    comment = "comment"


class Language(str, Enum):
    he = "he"
    en = "en"


class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    waiting_for_service = "waiting_for_service"


class PipelineType(str, Enum):
    text_only = "text_only"
    text_image = "text_image"
    full_video = "full_video"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    platform: Platform
    content_type: ContentType
    language: Language
    quantity: int = Field(..., ge=1, le=100)
    description: str = Field(..., min_length=5, max_length=2000)

    @field_validator("quantity")
    @classmethod
    def validate_quantity_for_type(cls, v: int) -> int:
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class FailedItem(BaseModel):
    index: int
    stage: str
    error: str
    retryable: bool = True


class AssetRecord(BaseModel):
    item_index: int
    asset_type: str          # text | image | video | caption | batch
    s3_key: str
    file_format: str
    validation_passed: bool
    generation_cost_usd: float = 0.0
    note: str = ""


class TaskManifest(BaseModel):
    task_id: str
    status: TaskStatus
    platform: str
    content_type: str
    language: str
    quantity_requested: int
    quantity_delivered: int
    quantity_failed: int
    total_cost_usd: float
    cost_saved_by_checkpoint: float
    created_at: str
    completed_at: str | None
    failed_items: list[FailedItem]
    assets: list[AssetRecord]


class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    platform: str
    content_type: str
    quantity_requested: int
    quantity_delivered: int
    quantity_failed: int
    total_cost_usd: float
    cost_saved_by_checkpoint: float
    manifest_s3_key: str | None = None
    presigned_manifest_url: str | None = None
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class ServiceHealth(BaseModel):
    service: str
    status: str          # healthy | degraded | down
    circuit_state: str   # closed | open | half_open
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    overall: str         # healthy | degraded | down
    services: list[ServiceHealth]
    timestamp: str
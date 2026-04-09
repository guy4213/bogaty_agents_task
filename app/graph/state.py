from __future__ import annotations
from typing import Literal, Optional, TypedDict


class ContentEngineState(TypedDict):
    # Input — immutable after Orchestrator initialises
    task_id: str
    item_index: int
    thread_id: str
    platform: str
    content_type: str
    language: str
    quantity: int
    description: str

    # Routing — set by Orchestrator
    pipeline_type: Literal["text_only", "text_image", "full_video"]

    # Style reference — set by Image Agent after first image generation
    style_reference_image: Optional[str]   # S3 key of first generated image — style anchor
    visual_style_descriptor: str           # One-sentence style guide from Content Agent

    # Agent outputs — accumulated progressively
    generated_texts: list[dict]
    generated_images: list[dict]
    generated_videos: list[dict]

    # Video Agent node-level checkpoint (Tier 3)
    current_video_ref: Optional[str]
    completed_extends: int

    # Content Validator
    validation_results: list[dict]
    retry_count: int

    # Cost tracking (per item)
    cost_accumulated: float

    # Output
    s3_manifest: Optional[dict]
    status: Literal["pending", "processing", "completed", "partial", "failed"]
    errors: list[str]
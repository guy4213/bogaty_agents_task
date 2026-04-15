from __future__ import annotations
from typing import Literal, Optional, TypedDict


class ContentEngineState(TypedDict):
    # ------------------------------------------------------------------
    # Input — immutable after Orchestrator initialises
    # ------------------------------------------------------------------
    task_id: str
    item_index: int           # Which item in the batch (0-based)
    thread_id: str            # LangGraph thread: "{task_id}__item_{n}"
    platform: str
    content_type: str
    language: str
    quantity: int
    description: str
    food_reference_image: Optional[str]   
    # ------------------------------------------------------------------
    # Routing — set by Orchestrator
    # ------------------------------------------------------------------
    pipeline_type: Literal["text_only", "text_image", "full_video"]

    # ------------------------------------------------------------------
    # Style reference — set by Image Agent after first image generation
    # ------------------------------------------------------------------
    style_reference_image: Optional[str]   # S3 key or local path of anchor image

    # ------------------------------------------------------------------
    # Agent outputs — accumulated progressively
    # ------------------------------------------------------------------
    generated_texts: list[dict]
    # Each dict: {text, hashtags, persona, scene_markers, caption_per_scene}

    generated_images: list[dict]
    # Each dict: {s3_key, prompt, dimensions, aspect_ratio, is_thumbnail}

    generated_videos: list[dict]
    # Each dict: {s3_key, duration_sec, has_captions, has_audio, scenes_completed}

    # ------------------------------------------------------------------
    # Video Agent node-level checkpoint (Tier 3)
    # ------------------------------------------------------------------
    current_video_ref: Optional[str]   # Veo video ID / URI in progress
    completed_extends: int             # How many Extend calls have succeeded

    # ------------------------------------------------------------------
    # Content Validator
    # ------------------------------------------------------------------
    validation_results: list[dict]
    # Each dict: {item_id, passed, score, errors, retry_feedback}

    retry_count: int                   # Retries used for this item

    # ------------------------------------------------------------------
    # Cost tracking (per item)
    # ------------------------------------------------------------------
    cost_accumulated: float

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    s3_manifest: Optional[dict]
    status: Literal["pending", "processing", "completed", "partial", "failed"]
    errors: list[str]
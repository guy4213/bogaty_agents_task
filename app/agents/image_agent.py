from __future__ import annotations
import asyncio
import logging

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.gemini_client import generate_image
from app.services.s3_client import upload_bytes, upload_text, asset_key

logger = logging.getLogger(__name__)

ASPECT_RATIOS = {
    ("instagram", "post"):  "1:1",
    ("instagram", "story"): "9:16",
    ("instagram", "reels"): "9:16",
    ("tiktok",    "reels"): "9:16",
    ("twitter",   "post"):  "16:9",
    ("facebook",  "post"):  "16:9",
    ("telegram",  "post"):  "1:1",
}

DEFAULT_ASPECT = "1:1"

def _build_image_prompt(state: ContentEngineState, is_thumbnail: bool = False) -> str:
    desc = state["description"]
    platform = state["platform"]
    lang = state["language"]
    
    # שליפת הקטגוריה שה-Content Agent הגדיר
    category = state.get("content_category", "general").lower()

    # גם כאן הורדתי את ה-"food photography aesthetic" מה-Instagram כדי שיהיה גנרי
    platform_style = {
        "instagram": "warm cinematic lighting, shallow depth of field, high-end editorial aesthetic, magazine quality",
        "tiktok":    "vibrant, high-contrast, mobile-optimized, dynamic composition",
        "twitter":   "clean, editorial, wide shot, professional photography",
        "facebook":  "warm, inviting, lifestyle photography",
        "telegram":  "clean, well-lit, clear subject",
    }.get(platform, "professional photography")

    thumbnail_note = " This is a video thumbnail — visually compelling, click-worthy." if is_thumbnail else ""
    lang_note = " No text overlays." if lang == "en" else ""
    
    # התאמה דינמית של הפרומפט לתמונה רגילה (פוסט) לפי הקטגוריה
    if category == "food":
        prefix = "Photorealistic food photography:"
        suffix = "appetizing presentation."
    else:
        prefix = f"Photorealistic {category} photography:"
        suffix = "striking presentation."

    return (
        f"{prefix} {desc}. "
        f"Style: {platform_style}.{thumbnail_note}{lang_note} "
        f"Ultra high quality, 8K, professional studio lighting, {suffix}"
    )
async def run(state: ContentEngineState) -> dict:
    task_id      = state["task_id"]
    item_index   = state["item_index"]
    platform     = state["platform"]
    content_type = state["content_type"]
    is_thumbnail = content_type == "reels"
    desc         = state["description"]

    aspect_ratio = ASPECT_RATIOS.get((platform, content_type), DEFAULT_ASPECT)
    scene_prompt = _build_image_prompt(state, is_thumbnail=is_thumbnail)
    visual_style_descriptor: str = state.get("visual_style_descriptor", "")

    logger.info(
        "[%s] ImageAgent: item_%d platform=%s type=%s ratio=%s has_style_descriptor=%s",
        task_id, item_index, platform, content_type, aspect_ratio,
        bool(visual_style_descriptor),
    )

    # Load style reference bytes
    style_reference_bytes: bytes | None = None
    style_ref_key = state.get("style_reference_image")

    if style_ref_key:
        try:
            cfg = get_settings()
            if cfg.dry_run:
                from app.mocks.mock_clients import _LOCAL_S3_ROOT
                local_path = _LOCAL_S3_ROOT / style_ref_key
                if local_path.exists():
                    style_reference_bytes = local_path.read_bytes()
                    logger.info(
                        "[%s] ImageAgent: style reference loaded (%d bytes) from local mock: %s",
                        task_id, len(style_reference_bytes), local_path,
                    )
            else:
                from app.services.s3_client import _get_client
                loop = asyncio.get_event_loop()
                s3 = _get_client()
                resp = await loop.run_in_executor(
                    None,
                    lambda: s3.get_object(Bucket=cfg.s3_bucket_name, Key=style_ref_key),
                )
                style_reference_bytes = resp["Body"].read()
                logger.info(
                    "[%s] ImageAgent: style reference loaded (%d bytes) from %s",
                    task_id, len(style_reference_bytes), style_ref_key,
                )
        except Exception as exc:
            logger.warning(
                "[%s] ImageAgent: could not load style reference (%s) — proceeding without",
                task_id, exc,
            )

    # Generate main image (thumbnail or post)
    image_bytes = await generate_image(
        prompt=scene_prompt,
        aspect_ratio=aspect_ratio,
        style_reference_bytes=style_reference_bytes,
        visual_style_descriptor=visual_style_descriptor,
    )

    filename = "thumbnail.png" if is_thumbnail else "image.png"
    s3_key = asset_key(task_id, platform, content_type, item_index, filename)
    await upload_bytes(s3_key, image_bytes, content_type="image/png")

    # Upload caption
    texts = state.get("generated_texts", [])
    if texts:
        caption_data = texts[0] if isinstance(texts[0], dict) else {}
        caption_text = caption_data.get("text", "")
        hashtags     = caption_data.get("hashtags", [])
        full_caption = caption_text + "\n\n" + " ".join(hashtags) if hashtags else caption_text
        if full_caption.strip():
            caption_key = asset_key(task_id, platform, content_type, item_index, "caption.txt")
            await upload_text(caption_key, full_caption)

    image_record = {
        "s3_key":                 s3_key,
        "prompt":                 scene_prompt,
        "visual_style_descriptor": visual_style_descriptor,
        "dimensions":             "native",
        "aspect_ratio":           aspect_ratio,
        "is_thumbnail":           is_thumbnail,
        "format":                 "png",
    }

    updates: dict = {
        "generated_images": state.get("generated_images", []) + [image_record],
        "cost_accumulated": state.get("cost_accumulated", 0.0) + 0.04,
    }

    if not state.get("style_reference_image"):
        updates["style_reference_image"] = s3_key
        logger.info("[%s] ImageAgent: style reference anchor set -> %s", task_id, s3_key)

    logger.info(
        "[%s] ImageAgent: item_%d uploaded -> %s (used_reference=%s)",
        task_id, item_index, s3_key, style_reference_bytes is not None,
    )
    return updates







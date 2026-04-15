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

    platform_style = {
        "instagram": "warm cinematic lighting, shallow depth of field, food photography aesthetic, magazine quality",
        "tiktok":    "vibrant, high-contrast, mobile-optimized, dynamic composition",
        "twitter":   "clean, editorial, wide shot, professional photography",
        "facebook":  "warm, inviting, lifestyle photography",
        "telegram":  "clean, well-lit, clear subject",
    }.get(platform, "professional photography")

    thumbnail_note = " This is a video thumbnail — visually compelling, click-worthy." if is_thumbnail else ""
    lang_note = " No text overlays." if lang == "en" else ""

    return (
        f"Photorealistic food photography: {desc}. "
        f"Style: {platform_style}.{thumbnail_note}{lang_note} "
        f"Ultra high quality, 8K, professional studio lighting, appetizing presentation."
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
            from app.services.s3_client import _get_client
            cfg = get_settings()
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

    # ── Food Reference Image (ללא אנשים) — לשימוש כ-style anchor בסצנה 4 ──
    if is_thumbnail and not state.get("food_reference_image"):
        try:
            food_prompt = (
                f"Photorealistic food photography: {desc}. "
                f"The finished dish beautifully plated on a white ceramic bowl. "
                f"NO people, NO hands, NO humans — food only. "
                f"Garnished with fresh herbs. "
                f"Style: {visual_style_descriptor}. "
                f"9:16 vertical format. Cinematic food photography. "
                f"Ultra high quality, professional studio lighting."
            )
            food_image_bytes = await generate_image(
                prompt=food_prompt,
                aspect_ratio="9:16",
                style_reference_bytes=None,          # ← ללא reference כדי למנוע חסימה
                visual_style_descriptor=visual_style_descriptor,
            )
            food_key = asset_key(task_id, platform, content_type, item_index, "food_reference.png")
            await upload_bytes(food_key, food_image_bytes, content_type="image/png")
            updates["food_reference_image"] = food_key
            logger.info("[%s] ImageAgent: food reference image -> %s", task_id, food_key)
        except Exception as exc:
            logger.warning(
                "[%s] ImageAgent: food reference image failed (%s) — continuing without",
                task_id, exc,
            )

    logger.info(
        "[%s] ImageAgent: item_%d uploaded -> %s (used_reference=%s)",
        task_id, item_index, s3_key, style_reference_bytes is not None,
    )
    return updates








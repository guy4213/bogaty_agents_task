from __future__ import annotations
import logging

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.gemini_client import generate_video_initial, extend_video, download_video
from app.services.s3_client import upload_bytes, asset_key, upload_text

logger = logging.getLogger(__name__)


def _build_initial_prompt(scene: dict, lang: str, visual_style: str = "") -> str:
    visual = scene.get("visual_description", "")
    audio_mood = scene.get("audio_mood", "ambient kitchen sounds")
    style_anchor = f" Visual style: {visual_style}." if visual_style else ""

    return (
        f"{visual}.{style_anchor} "
        f"Audio: {audio_mood}. "
        f"9:16 vertical format, 1080x1920, cinematic food videography, "
        f"warm lighting, professional grade. No text overlays whatsoever."
    )


def _build_extend_prompt(scene: dict, lang: str, visual_style: str = "") -> str:
    visual = scene.get("visual_description", "")
    style_anchor = f" Maintain this exact visual style: {visual_style}." if visual_style else ""

    return (
        f"Continue seamlessly: {visual}.{style_anchor} "
        f"SAME ingredients, SAME kitchen, SAME lighting. "
        f"No text overlays whatsoever."
    )



async def run(state: ContentEngineState) -> dict:
    """
    Video Agent with Tier 3 (node-level) checkpointing.

    If this node is retried after a partial failure, the state will contain:
      - current_video_ref: the Veo URI of the video generated so far
      - completed_extends: how many Extend calls already succeeded

    The loop resumes from where it left off, avoiding redundant Veo API calls.
    """
    cfg = get_settings()
    task_id = state["task_id"]
    item_index = state["item_index"]
    platform = state["platform"]
    content_type = state["content_type"]
    lang = state["language"]

    # Visual style descriptor — constant across all scenes for consistency
    visual_style = state.get("visual_style_descriptor", "")

    # Extract scene data from the Content Agent's output
    texts = state.get("generated_texts", [])
    script = texts[0] if texts else {}
    scenes: list[dict] = script.get("scenes", [])

    if not scenes:
        logger.error("[%s] VideoAgent: no scenes found in generated_texts", task_id)
        raise ValueError("No scene data available for video generation")

    required_extends = len(scenes) - 1  # 4 scenes = 3 extends = 29 seconds

    # ------------------------------------------------------------------
    # Tier 3: Resume from checkpoint if partial work was done
    # ------------------------------------------------------------------
    current_video_ref: str | None = state.get("current_video_ref")
    completed_extends: int = state.get("completed_extends", 0)

    if current_video_ref:
        logger.info(
            "[%s] VideoAgent: RESUMING from checkpoint — "
            "video_ref=%s completed_extends=%d/%d",
            task_id, current_video_ref, completed_extends, required_extends,
        )
    else:
        # ------------------------------------------------------------------
        # Step 1: Initial 8-second generation
        # ------------------------------------------------------------------
        logger.info(
            "[%s] VideoAgent: item_%d generating initial clip (scene 1, %ds)",
            task_id, item_index, cfg.veo_initial_duration_sec,
        )
        initial_prompt = _build_initial_prompt(scenes[0], lang, visual_style)
        current_video_ref = await generate_video_initial(initial_prompt)
        completed_extends = 0
        logger.info(
            "[%s] VideoAgent: initial clip ready — video_ref=%s",
            task_id, current_video_ref,
        )

    # ------------------------------------------------------------------
    # Step 2: Extend loop — Tier 3 checkpoint saved after each iteration
    # ------------------------------------------------------------------
    for extend_idx in range(completed_extends, required_extends):
        scene = scenes[extend_idx + 1]  # scenes[0] was the initial clip
        extend_prompt = _build_extend_prompt(scene, lang, visual_style)

        logger.info(
            "[%s] VideoAgent: extend %d/%d (scene %d)",
            task_id, extend_idx + 1, required_extends, scene.get("scene", extend_idx + 2),
        )

        try:
            current_video_ref = await extend_video(
                video_uri=current_video_ref,
                prompt=extend_prompt,
                extend_index=extend_idx,
            )
            completed_extends = extend_idx + 1
            logger.info(
                "[%s] VideoAgent: extend %d complete — video_ref=%s",
                task_id, completed_extends, current_video_ref,
            )

        except Exception as exc:
            logger.error(
                "[%s] VideoAgent: extend %d FAILED (%s) — "
                "state preserved: completed_extends=%d video_ref=%s",
                task_id, extend_idx + 1, exc, completed_extends, current_video_ref,
            )
            raise _PartialVideoError(
                str(exc),
                current_video_ref=current_video_ref,
                completed_extends=completed_extends,
            ) from exc

    # ------------------------------------------------------------------
    # Step 3: Download final video and upload to S3
    # ------------------------------------------------------------------
    logger.info(
        "[%s] VideoAgent: all %d extends complete — downloading final video",
        task_id, required_extends,
    )
    video_bytes = await download_video(current_video_ref)

    total_duration = cfg.veo_initial_duration_sec + (required_extends * cfg.veo_extend_duration_sec)

    video_key = asset_key(task_id, platform, content_type, item_index, "video.mp4")
    await upload_bytes(video_key, video_bytes, content_type="video/mp4")

    # Upload script alongside video — Hebrew captions preserved here
    script_text = "\n\n".join(
        f"Scene {s.get('scene', i+1)} ({s.get('duration_sec', 7)}s):\n"
        f"Visual: {s.get('visual_description', '')}\n"
        f"Caption (HE): {s.get('caption_text', '')}\n"
        f"Caption (EN): {s.get('caption_text_en', '')}"
        for i, s in enumerate(scenes)
    )
    script_key = asset_key(task_id, platform, content_type, item_index, "script.txt")
    await upload_text(script_key, script_text)

    # Rough Veo cost: ~$0.50/clip initial + $0.20/extend
    veo_cost = 0.50 + (required_extends * 0.20)

    video_record = {
        "s3_key": video_key,
        "duration_sec": total_duration,
        "has_captions": True,
        "has_audio": True,
        "scenes_completed": len(scenes),
        "format": "mp4",
    }

    logger.info(
        "[%s] VideoAgent: item_%d video uploaded %s (%.0fs) cost~$%.2f",
        task_id, item_index, video_key, total_duration, veo_cost,
    )

    return {
        "generated_videos": state.get("generated_videos", []) + [video_record],
        "current_video_ref": current_video_ref,
        "completed_extends": completed_extends,
        "cost_accumulated": state.get("cost_accumulated", 0.0) + veo_cost,
    }



class _PartialVideoError(Exception):
    """Carries partial progress so the runner can persist checkpoint state."""

    def __init__(self, message: str, current_video_ref: str, completed_extends: int):
        super().__init__(message)
        self.current_video_ref = current_video_ref
        self.completed_extends = completed_extends
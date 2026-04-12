from __future__ import annotations
import logging

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.gemini_client import generate_video_initial, extend_video, download_video
from app.services.s3_client import upload_bytes, asset_key, upload_text

logger = logging.getLogger(__name__)


def _build_initial_prompt(scene: dict, lang: str, visual_style: str = "") -> str:
    visual       = scene.get("visual_description", "")
    audio_mood   = scene.get("audio_mood", "ambient kitchen sounds")
    style_anchor = f" Visual style: {visual_style}." if visual_style else ""

    if lang == "en":
        caption = scene.get("caption_text", "")
        caption_instruction = (
            f' Render burnt-in subtitle text at the bottom of the frame: "{caption}".'
            if caption else ""
        )
    else:
        # עברית — Veo לא תומך RTL, FFmpeg יטפל בזה
        caption_instruction = " No text overlays."

    return (
        f"{visual}.{style_anchor}"
        f"{caption_instruction} "
        f"Audio: {audio_mood}. "
        f"9:16 vertical format, 1080x1920, cinematic food videography, "
        f"warm lighting, professional grade."
    )


def _build_extend_prompt(scene: dict, lang: str, visual_style: str = "", first_scene_visual: str = "") -> str:
    visual       = scene.get("visual_description", "")
    style_anchor = f" Maintain this exact visual style: {visual_style}." if visual_style else ""
    anchor       = f" Reference scene 1: {first_scene_visual}." if first_scene_visual else ""

    if lang == "en":
        caption = scene.get("caption_text", "")
        caption_instruction = f' Subtitle at bottom: "{caption}".' if caption else ""
    else:
        caption_instruction = " No text overlays."

    return (
        f"Continue seamlessly: {visual}.{style_anchor}{anchor} "
        f"CRITICAL — FORBIDDEN: No bananas, no unrelated food, no new ingredients. "
        f"ONLY the exact same ingredients and kitchen from scene 1. "
        f"SAME kitchen, SAME lighting, SAME food."
        f"{caption_instruction} "
    )

async def run(state: ContentEngineState) -> dict:
    """
    Video Agent with Tier 3 (node-level) checkpointing.
    If this node is retried after a partial failure, the state will contain:
      - current_video_ref: the Veo URI of the video generated so far
      - completed_extends:  how many Extend calls already succeeded
    The loop resumes from where it left off, avoiding redundant Veo API calls.
    """
    cfg          = get_settings()
    task_id      = state["task_id"]
    item_index   = state["item_index"]
    platform     = state["platform"]
    content_type = state["content_type"]
    lang         = state["language"]
    visual_style = state.get("visual_style_descriptor", "")

    texts  = state.get("generated_texts", [])
    script = texts[0] if texts else {}
    scenes: list[dict] = script.get("scenes", [])

    if not scenes:
        logger.error("[%s] VideoAgent: no scenes found in generated_texts", task_id)
        raise ValueError("No scene data available for video generation")

    required_extends = len(scenes) - 1  # 4 scenes = 3 extends = 29s
    first_scene_visual = scenes[0].get("visual_description", "")

    # ------------------------------------------------------------------
    # Tier 3: Resume from checkpoint if partial work was done
    # ------------------------------------------------------------------
    current_video_ref: str | None = state.get("current_video_ref")
    completed_extends: int        = state.get("completed_extends", 0)
    all_video_refs: list[str]      = state.get("all_video_refs", [])
    if current_video_ref:
        logger.info(
            "[%s] VideoAgent: RESUMING checkpoint — ref=%s extends=%d/%d",
            task_id, current_video_ref, completed_extends, required_extends,
        )
    else:
        logger.info(
            "[%s] VideoAgent: item_%d initial clip (scene 1, %ds) caption_en='%s'",
            task_id, item_index, cfg.veo_initial_duration_sec,
            scenes[0].get("caption_text_en", "⚠️ MISSING"),
        )
        initial_prompt    = _build_initial_prompt(scenes[0], lang, visual_style)
        current_video_ref = await generate_video_initial(initial_prompt)
        completed_extends = 0
        all_video_refs    = [current_video_ref]    
        logger.info("[%s] VideoAgent: initial clip ready — ref=%s", task_id, current_video_ref)

    # ------------------------------------------------------------------
    # Extend loop — Tier 3 checkpoint saved after each iteration
    # ------------------------------------------------------------------
    for extend_idx in range(completed_extends, required_extends):
        scene         = scenes[extend_idx + 1]
        extend_prompt = _build_extend_prompt(scene, lang, visual_style, first_scene_visual)
        logger.info(
            "[%s] VideoAgent: extend %d/%d scene=%d caption_en='%s'",
            task_id, extend_idx + 1, required_extends,
            scene.get("scene", extend_idx + 2),
            scene.get("caption_text_en", "⚠️ MISSING"),
        )

        try:
            current_video_ref = await extend_video(
                video_uri=current_video_ref,
                prompt=extend_prompt,
                extend_index=extend_idx,
            )
            completed_extends = extend_idx + 1
            all_video_refs.append(current_video_ref)
            logger.info(
                "[%s] VideoAgent: extend %d done — ref=%s total_refs=%d",
                task_id, completed_extends, current_video_ref, len(all_video_refs),
            )
        except Exception as exc:
            logger.error(
                "[%s] VideoAgent: extend %d FAILED (%s) — "
                "preserving state: completed_extends=%d ref=%s",
                task_id, extend_idx + 1, exc, completed_extends, current_video_ref,
            )
            raise _PartialVideoError(
                str(exc),
                current_video_ref=current_video_ref,
                completed_extends=completed_extends,
                all_video_refs=all_video_refs,
            ) from exc

    # ------------------------------------------------------------------
    # Step 3: Download final video from GCS
    # ------------------------------------------------------------------
    logger.info("[%s] VideoAgent: merging %d clips from GCS", task_id, len(all_video_refs))
    if get_settings().dry_run:
        from app.mocks.mock_clients import mock_download_video
        video_bytes = await mock_download_video(all_video_refs[-1])
    else:
        from app.services.caption_service import download_and_merge_clips
        video_bytes = await download_and_merge_clips(
            gcs_uris=all_video_refs,
            project_id=cfg.vertex_project_id,
            initial_duration=cfg.veo_initial_duration_sec,
            extend_duration=cfg.veo_extend_duration_sec,
        )
    total_duration = cfg.veo_initial_duration_sec + required_extends * cfg.veo_extend_duration_sec

    # ------------------------------------------------------------------
    # Step 4: Burn Hebrew captions with FFmpeg (language=he only)
    # ------------------------------------------------------------------
    if lang == "he":
        logger.info("[%s] VideoAgent: burning Hebrew captions with FFmpeg", task_id)
        if get_settings().dry_run:
            from app.mocks.mock_clients import mock_burn_hebrew_captions
            video_bytes = await mock_burn_hebrew_captions(
                video_bytes, scenes,
                cfg.veo_initial_duration_sec,
                cfg.veo_extend_duration_sec,
            )
        else:
            from app.services.caption_service import burn_hebrew_captions
            video_bytes = await burn_hebrew_captions(
                video_bytes=video_bytes,
                scenes=scenes,
                initial_duration=cfg.veo_initial_duration_sec,
                extend_duration=cfg.veo_extend_duration_sec,
            )
        logger.info("[%s] VideoAgent: captions done", task_id)

    # ------------------------------------------------------------------
    # Step 5: Upload final video to S3
    # ------------------------------------------------------------------
    video_key = asset_key(task_id, platform, content_type, item_index, "video.mp4")
    await upload_bytes(video_key, video_bytes, content_type="video/mp4")

    # Upload script — Hebrew captions preserved here
    script_text = "\n\n".join(
        f"Scene {s.get('scene', i+1)} ({s.get('duration_sec', 7)}s):\n"
        f"Visual: {s.get('visual_description', '')}\n"
        f"Caption (HE): {s.get('caption_text', '')}\n"
        f"Caption (EN): {s.get('caption_text_en', '')}"
        for i, s in enumerate(scenes)
    )
    script_key = asset_key(task_id, platform, content_type, item_index, "script.txt")
    await upload_text(script_key, script_text)

    veo_cost = 0.50 + required_extends * 0.20

    has_captions = all(bool(s.get("caption_text_en")) for s in scenes)

    video_record = {
        "s3_key":           video_key,
        "duration_sec":     total_duration,
        "has_captions":     has_captions,
        "has_audio":        True,
        "scenes_completed": len(scenes),
        "format":           "mp4",
    }

    logger.info(
        "[%s] VideoAgent: item_%d uploaded %s (%ds) has_captions=%s cost~$%.2f",
        task_id, item_index, video_key, total_duration, has_captions, veo_cost,
    )

    return {
        "generated_videos":  state.get("generated_videos", []) + [video_record],
        "current_video_ref": current_video_ref,
        "completed_extends": completed_extends,
        "all_video_refs":    all_video_refs,
        "cost_accumulated":  state.get("cost_accumulated", 0.0) + veo_cost,
    }


class _PartialVideoError(Exception):
    def __init__(self, message: str, current_video_ref: str, completed_extends: int, all_video_refs: list[str] | None = None):
        super().__init__(message)
        self.current_video_ref = current_video_ref
        self.completed_extends = completed_extends
        self.all_video_refs    = all_video_refs or []
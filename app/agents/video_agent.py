from __future__ import annotations
from asyncio import subprocess
import logging
import pathlib

from app.config import get_settings
from app.graph.state import ContentEngineState
from app.services.gemini_client import generate_video_initial, extend_video, download_video,generate_video_from_frame
from app.services.s3_client import upload_bytes, asset_key, upload_text
from app.services.caption_service import extract_last_frame

logger = logging.getLogger(__name__)


def _sanitize_narrator(text: str) -> str:
    """Remove dashes that cause Veo TTS to insert filler words."""
    import re
    # em-dash and en-dash → comma+space; plain hyphen between words → comma+space
    text = re.sub(r"\s*[—–]\s*", ", ", text)
    text = re.sub(r"(\w)\s*-\s*(\w)", r"\1, \2", text)
    # collapse multiple commas/spaces
    text = re.sub(r",\s*,", ",", text)
    return text.strip()


def _build_initial_prompt(scene: dict, lang: str, visual_style: str = "", canonical_subject: str = "") -> str:
    visual      = scene.get("visual_description", "")
    audio_mood  = scene.get("audio_mood", "ambient sounds")
    narrator    = _sanitize_narrator(scene.get("narrator_text", ""))
    style_anchor = f" Visual style: {visual_style}." if visual_style else ""
    subject_lock = (
        f" CANONICAL SUBJECT FOR THIS ENTIRE VIDEO: [{canonical_subject}]."
        f" Establish this exact subject clearly in the opening frame."
    ) if canonical_subject else ""
    return (
        f"{visual}.{style_anchor}{subject_lock}"
        f" Camera framing: medium shot with subject fully visible and centered."
        f" Leave breathing room around the subject — do NOT crop or cut off edges."
        f" Subject must be 100% in frame at all times."
        f" IMPORTANT: This is a self-contained scene."
        f" Do NOT anticipate or begin any next action."
        f" The scene ends exactly as described — no transitions, no preparation for what comes next."
        f" No text overlays."
        f" Audio: {audio_mood}. No voice-over — music and ambient sounds only."
        f" 9:16 vertical format, 1080x1920, cinematic videography, "
        f"professional grade."
    )


def _build_extend_prompt(
    scene: dict, lang: str, visual_style: str = "",
    first_scene_visual: str = "", canonical_subject: str = "",
    content_category: str = "",
) -> str:
    visual      = scene.get("visual_description", "")
    entry_state = scene.get("entry_state", "")
    audio_mood  = scene.get("audio_mood", "")

    style_anchor = f" Maintain this exact visual style: {visual_style}." if visual_style else ""

    is_open = content_category not in ("food", "fitness", "technology", "")
    subject_lock = (
        f" LOCKED SUBJECT: [{canonical_subject}]."
        f" The core subject and theme is {canonical_subject}."
        f" FORBIDDEN: Do NOT replace {canonical_subject} with a completely unrelated subject."
        + (
            # CLOSED: strict lock — no new elements
            f" VISUAL LOCK: What appears in frame is EXCLUSIVELY {canonical_subject}."
            f" ALL elements of {canonical_subject} MUST remain visible at all times."
            f" No variations. No new elements."
            if not is_open else
            # OPEN: allow new logical locations but keep theme
            f" New environments or locations are allowed IF they logically belong to the {content_category} journey."
            f" FORBIDDEN: Do NOT introduce elements that are unrelated to {canonical_subject}."
        )
    ) if canonical_subject else ""

    scene_anchor = (
        f" Reference opening scene: {first_scene_visual}."
    ) if first_scene_visual else ""

    continuity = (
        f" START FROM THIS EXACT STATE: {entry_state}."
        f" Do NOT go back in time. Do NOT repeat previous steps."
    ) if entry_state else ""

    no_repeat = (
        f" STRICTLY FORBIDDEN: Do NOT repeat any action that already occurred"
        f" in a previous scene."
        f" Any actions involving {canonical_subject} that occurred in previous scenes have already happened and must NOT be shown again."
        f" This scene continues AFTER all previous actions are fully complete."
    ) if canonical_subject else ""

    audio_instruction = (
        f" Continue audio: {audio_mood}."
        f" SAME music genre and energy as previous scene."
        f" No voice-over — music and ambient sounds only."
    ) if audio_mood else " No voice-over — music and ambient sounds only."

    # Open journeys (travel, real estate) may change location between scenes
    is_open = content_category not in ("food", "fitness", "technology", "")
    location_instruction = (
        f" SAME location, SAME lighting as previous scene."
        if not is_open else
        f" SAME visual style, color grade and lighting TEMPERATURE as previous scene."
        f" Location may change if the narrative requires it."
    )
    return (
        f"Continue seamlessly: {visual}.{style_anchor}{subject_lock}{scene_anchor}"
        f"{continuity}"
        f"{no_repeat}"
        f" Camera framing: medium shot with subject fully visible and centered."
        f" Leave breathing room around the subject — do NOT crop or cut off edges."
        f" Subject must be 100% in frame at all times."
        f"{location_instruction}"
        f"{audio_instruction}"
        f" No text overlays."
    )


def _build_payoff_prompt(
    scene: dict, lang: str, visual_style: str = "",
    canonical_subject: str = ""
) -> str:
    audio_mood  = scene.get("audio_mood", "")
    entry_state = scene.get("entry_state", "")

    style_anchor = f" Maintain this exact visual style: {visual_style}." if visual_style else ""

    subject_lock = (
        f" SUBJECT: [{canonical_subject}] — fully completed and presented in its final state."
        f" ALL elements of {canonical_subject} are visible and complete."
    ) if canonical_subject else ""

    continuity = (
        f" CONFIRMED STATE: {entry_state}."
        f" Everything described above is already done. Do not redo any of it."
    ) if entry_state else ""

    audio_instruction = (
        f" Continue audio: {audio_mood}."
        f" Same genre, slower and more cinematic energy — this is the final scene."
        f" No voice-over — music and ambient sounds only."
    ) if audio_mood else " No voice-over — music and ambient sounds only."

    return (
            f"FINAL SCENE — everything is complete. No more actions.{style_anchor}{subject_lock}"
            f"{continuity}"
            f" FORBIDDEN: Do NOT show any active process, building, moving, or assembly."
            f" FORBIDDEN: Do NOT repeat any action from previous scenes."
            f" The subject is already in its ultimate final state — only reveal it cinematically."
            f" Camera slowly and smoothly pushes in from medium shot to close-up."
            f" NOTHING MOVES except the camera."
            f" Subject fully visible, centered, 100% in frame."
            f" SAME location, SAME lighting as previous scene."
            f"{audio_instruction}"
            f" No text overlays."
            f" 9:16 vertical format, 1080x1920, cinematic videography, professional grade."
        )

async def _download_single_clip(gcs_uri: str, project_id: str) -> bytes:
    """הורד קליפ בודד מ-GCS."""
    from google.cloud import storage as gcs
    import asyncio
    loop = asyncio.get_event_loop()

    def _dl():
        client = gcs.Client(project=project_id)
        bucket_name = gcs_uri.split("/")[2]
        blob_name   = "/".join(gcs_uri.split("/")[3:])
        return client.bucket(bucket_name).blob(blob_name).download_as_bytes()

    return await loop.run_in_executor(None, _dl)


async def _trim_clip_async(video_bytes: bytes, duration: float) -> bytes:
    """חתוך קליפ ל-duration שניות."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _trim_clip_sync, video_bytes, duration)


def _trim_clip_sync(video_bytes: bytes, duration: float) -> bytes:
    import static_ffmpeg, shutil
    static_ffmpeg.add_paths()
    ffmpeg_exe = shutil.which("ffmpeg")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    inp = tmp_dir / "trim_in.mp4"
    out = tmp_dir / "trim_out.mp4"
    inp.write_bytes(video_bytes)

    proc = subprocess.run(
        [ffmpeg_exe, "-y", "-i", "trim_in.mp4",
         "-t", str(duration), "-c", "copy", "trim_out.mp4"],
        cwd=str(tmp_dir),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg trim failed: {proc.stderr[-300:]}")

    result = out.read_bytes()
    for f in [inp, out]:
        try: f.unlink()
        except Exception: pass
    return result

async def run(state: ContentEngineState) -> dict:
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
        logger.error("[%s] item_%d · VideoAgent: no scenes found in generated_texts", task_id, item_index)
        raise ValueError("No scene data available for video generation")

    required_extends   = len(scenes) - 1
    last_extend_idx    = required_extends - 1
    first_scene_visual = scenes[0].get("visual_description", "")
    canonical_subject  = script.get("canonical_subject", first_scene_visual)

    current_video_ref: str | None = state.get("current_video_ref")
    completed_extends: int        = state.get("completed_extends", 0)
    all_video_refs: list[str]     = state.get("all_video_refs", [])

    if current_video_ref:
        logger.info(
            "[%s] item_%d · VideoAgent: RESUMING checkpoint — ref=%s extends=%d/%d",
            task_id, item_index, current_video_ref, completed_extends, required_extends,
        )
    else:
        logger.info(
            "[%s] VideoAgent: item_%d initial clip (scene 1, %ds) caption_en='%s'",
            task_id, item_index, cfg.veo_initial_duration_sec,
            scenes[0].get("caption_text_en", "⚠️ MISSING"),
        )
        initial_prompt    = _build_initial_prompt(scenes[0], lang, visual_style, canonical_subject)
        current_video_ref = await generate_video_initial(initial_prompt)
        completed_extends = 0
        all_video_refs    = [current_video_ref]
        logger.info("[%s] item_%d · VideoAgent: initial clip ready — ref=%s", task_id, item_index, current_video_ref)

    # ------------------------------------------------------------------
    # Extend loop
    # ------------------------------------------------------------------
    for extend_idx in range(completed_extends, required_extends):
        scene     = scenes[extend_idx + 1]
        is_payoff = (extend_idx == last_extend_idx)

        if is_payoff:
            extend_prompt = _build_payoff_prompt(
                scene, lang, visual_style, canonical_subject
            )
            logger.info(
                "[%s] item_%d · VideoAgent: extend %d/%d PAYOFF (image-to-video from Scene 1) scene=%d",
                task_id, item_index, extend_idx + 1, required_extends,
                scene.get("scene", extend_idx + 2),
            )

            # ── Extract frame מScene 1 — consistency מושלמת ──
            logger.info("[%s] item_%d · VideoAgent: downloading Scene 1 for frame extraction", task_id, item_index)
            scene1_bytes = await _download_single_clip(
                all_video_refs[0],  # ← ref של Scene 1 תמיד ראשון
                cfg.vertex_project_id,
            )
            extracted_anchor_frame = extract_last_frame(scene1_bytes)
            logger.info(
                "[%s] item_%d · VideoAgent: scene 1 frame extracted (%d bytes)",
                task_id, item_index, len(extracted_anchor_frame),
            )

            try:
                current_video_ref = await generate_video_from_frame(
                    frame_bytes=extracted_anchor_frame,
                    prompt=extend_prompt,
                    extend_index=extend_idx,
                )
                completed_extends = extend_idx + 1
                all_video_refs.append(current_video_ref)
                logger.info(
                    "[%s] item_%d · VideoAgent: payoff done — ref=%s total_refs=%d",
                    task_id, item_index, current_video_ref, len(all_video_refs),
                )
            except Exception as exc:
                logger.error("[%s] item_%d · VideoAgent: payoff FAILED (%s)", task_id, item_index, exc)
                raise _PartialVideoError(
                    str(exc),
                    current_video_ref=current_video_ref,
                    completed_extends=completed_extends,
                    all_video_refs=all_video_refs,
                    generated_texts=state.get("generated_texts", []),
                ) from exc

        else:
            # ── סצנות 2-3: extend רגיל ──
            extend_prompt = _build_extend_prompt(
                scene, lang, visual_style, first_scene_visual, canonical_subject,
                content_category=state.get("content_category", ""),
            )
            logger.info(
                "[%s] item_%d · VideoAgent: extend %d/%d scene=%d caption_en='%s'",
                task_id, item_index, extend_idx + 1, required_extends,
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
                    "[%s] item_%d · VideoAgent: extend %d done — ref=%s total_refs=%d",
                    task_id, item_index, completed_extends, current_video_ref, len(all_video_refs),
                )
            except Exception as exc:
                logger.error(
                    "[%s] item_%d · VideoAgent: extend %d FAILED (%s) — "
                    "preserving state: completed_extends=%d ref=%s",
                    task_id, item_index, extend_idx + 1, exc, completed_extends, current_video_ref,
                )
                raise _PartialVideoError(
                    str(exc),
                    current_video_ref=current_video_ref,
                    completed_extends=completed_extends,
                    all_video_refs=all_video_refs,
                    generated_texts=state.get("generated_texts", []),
                ) from exc

    # ------------------------------------------------------------------
    # Download + merge
    # ------------------------------------------------------------------
    logger.info("[%s] item_%d · VideoAgent: merging %d clips from GCS", task_id, item_index, len(all_video_refs))
    scene_durations: list[float] = []
    if get_settings().dry_run:
        from app.mocks.mock_clients import mock_download_video
        video_bytes = await mock_download_video(all_video_refs[-1])
        scene_durations = [float(cfg.veo_initial_duration_sec)] + [
            float(cfg.veo_extend_duration_sec)
        ] * required_extends
    else:
        from app.services.caption_service import download_and_merge_clips
        video_bytes, scene_durations = await download_and_merge_clips(
            gcs_uris=all_video_refs,
            project_id=cfg.vertex_project_id,
            initial_duration=cfg.veo_initial_duration_sec,
            extend_duration=cfg.veo_extend_duration_sec,
            task_id=task_id,
            item_index=item_index,
        )
    total_duration = sum(scene_durations) if scene_durations else (
        cfg.veo_initial_duration_sec + required_extends * cfg.veo_extend_duration_sec
    )

    # ------------------------------------------------------------------
    # Google TTS voice track — mix with Veo background music
    # ------------------------------------------------------------------
    if not get_settings().dry_run:
        try:
            import asyncio as _asyncio
            from app.services.tts_service import synthesize
            logger.info("[%s] item_%d · VideoAgent: synthesizing TTS for %d scenes lang=%s",
                        task_id, item_index, len(scenes), lang)
            raw_segments = await _asyncio.gather(*[
                _asyncio.get_event_loop().run_in_executor(
                    None, synthesize, _sanitize_narrator(s.get("narrator_text", "")), lang
                )
                for s in scenes
            ])
            # keep segments paired with their durations — skip empty ones
            paired = [
                (seg, dur) for seg, dur in zip(raw_segments, scene_durations) if seg
            ]
            if paired:
                tts_segments, tts_durations = zip(*paired)
                from app.services.caption_service import mix_tts_voice
                video_bytes = await mix_tts_voice(
                    video_bytes=video_bytes,
                    tts_segments=list(tts_segments),
                    scene_durations=list(tts_durations),
                    music_volume=0.25,
                    task_id=task_id,
                    item_index=item_index,
                )
                logger.info("[%s] item_%d · VideoAgent: TTS mix done", task_id, item_index)
        except Exception as exc:
            logger.warning("[%s] item_%d · VideoAgent: TTS failed (%s) — keeping Veo audio",
                           task_id, item_index, exc)

    # ------------------------------------------------------------------
    # Burn captions (FFmpeg — timed to actual clip durations)
    # ------------------------------------------------------------------
    logger.info("[%s] item_%d · VideoAgent: burning captions lang=%s with FFmpeg", task_id, item_index, lang)
    if get_settings().dry_run:
        from app.mocks.mock_clients import mock_burn_captions
        video_bytes = await mock_burn_captions(
            video_bytes, scenes,
            cfg.veo_initial_duration_sec,
            cfg.veo_extend_duration_sec,
            lang=lang,
        )
    else:
        from app.services.caption_service import burn_captions
        video_bytes = await burn_captions(
            video_bytes=video_bytes,
            scenes=scenes,
            scene_durations=scene_durations,
            lang=lang,
            task_id=task_id,
            item_index=item_index,
        )
    logger.info("[%s] item_%d · VideoAgent: captions done", task_id, item_index)

    # ------------------------------------------------------------------
    # Upload to S3
    # ------------------------------------------------------------------
    video_key = asset_key(task_id, platform, content_type, item_index, "video.mp4")
    await upload_bytes(video_key, video_bytes, content_type="video/mp4")

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

    if lang == "he":
        has_captions = all(bool(s.get("caption_text")) for s in scenes)
    else:
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
    def __init__(
        self, message: str, current_video_ref: str, completed_extends: int,
        all_video_refs: list[str] | None = None,
        generated_texts: list[dict] | None = None,
    ):
        super().__init__(message)
        self.current_video_ref = current_video_ref
        self.completed_extends = completed_extends
        self.all_video_refs    = all_video_refs or []
        self.generated_texts   = generated_texts or []
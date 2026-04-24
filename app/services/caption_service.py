from __future__ import annotations
import asyncio
import json
import logging
import pathlib
import subprocess

logger = logging.getLogger(__name__)


def _seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _get_video_dimensions(video_path: pathlib.Path) -> tuple[int, int]:
    """קרא רזולוציה מהוידאו עם FFprobe."""
    import static_ffmpeg
    import shutil
    static_ffmpeg.add_paths()

    ffprobe_exe = shutil.which("ffprobe")
    if not ffprobe_exe:
        logger.warning("ffprobe not found — using default 720x1280")
        return 720, 1280

    cmd = [
        ffprobe_exe, "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(video_path),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(video_path.parent),
    )

    try:
        data = json.loads(result.stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                w = int(stream["width"])
                h = int(stream["height"])
                logger.info("Video dimensions detected: %dx%d", w, h)
                return w, h
    except Exception as e:
        logger.warning("Could not parse ffprobe output: %s", e)

    return 720, 1280


def _probe_clip_duration(path: pathlib.Path) -> float:
    """Return actual duration of a video file in seconds via ffprobe."""
    import static_ffmpeg
    import shutil
    static_ffmpeg.add_paths()

    ffprobe_exe = shutil.which("ffprobe")
    if not ffprobe_exe:
        return 0.0

    cmd = [
        ffprobe_exe, "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        cwd=str(path.parent),
    )
    try:
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return 0.0


def _wrap_ass_text(text: str, max_chars: int = 35) -> str:
    """Split text into lines of max_chars, joined with ASS line-break \\N."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return r"\N".join(lines)


def _build_ass_content(
    scenes: list[dict],
    scene_durations: list[float],
    width: int = 720,
    height: int = 1280,
    lang: str = "he",
) -> str:
    """Build ASS subtitle file timed to actual clip durations — RTL for Hebrew, LTR for English."""

    font_size = max(38, int(width * 0.064))
    margin_h  = int(width * 0.055)
    margin_v  = int(height * 0.10)

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Hebrew,Arial,{font_size},"
        f"&H00FFFFFF,"
        f"&H00FFFFFF,"
        f"&H00000000,"
        f"&H99000000,"
        f"1,0,0,0,"
        f"100,100,0,0,"
        f"4,"
        f"0,0,"
        f"2,"
        f"{margin_h},{margin_h},{margin_v},"
        f"177\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = ""
    current_time = 0.0

    for i, scene in enumerate(scenes):
        duration = scene_durations[i] if i < len(scene_durations) else 7.0
        start    = current_time
        end      = current_time + duration - 0.3

        # Use narrator_text — the exact words the voice says on screen
        caption = scene.get("narrator_text", "")
        if not caption:
            # fallback to legacy caption fields
            caption = scene.get("caption_text" if lang != "en" else "caption_text_en", "")

        if caption:
            # replace dashes with comma so captions match the sanitized TTS voice
            import re
            caption = re.sub(r"\s*[—–]\s*", ", ", caption)
            caption = re.sub(r"(\w)\s*-\s*(\w)", r"\1, \2", caption)
            # wrap long lines at ~35 chars to keep captions readable
            wrapped = _wrap_ass_text(caption, max_chars=35)
            alignment = "{\\an2}{\\q2}" if lang == "he" else "{\\an2}"
            rtl_text = f"{alignment}{wrapped}"
            events += (
                f"Dialogue: 0,{_seconds_to_ass_time(start)},"
                f"{_seconds_to_ass_time(end)},Hebrew,,0,0,0,,{rtl_text}\n"
            )

        current_time += duration

    return header + events


async def mix_tts_voice(
    video_bytes: bytes,
    tts_segments: list[bytes],
    scene_durations: list[float],
    music_volume: float = 0.25,
    task_id: str = "",
    item_index: int = -1,
) -> bytes:
    """Mix Google TTS voice segments (timed per scene) with Veo background music."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_mix_tts_voice,
        video_bytes,
        tts_segments,
        scene_durations,
        music_volume,
        task_id,
        item_index,
    )


def _sync_mix_tts_voice(
    video_bytes: bytes,
    tts_segments: list[bytes],
    scene_durations: list[float],
    music_volume: float = 0.25,
    task_id: str = "",
    item_index: int = -1,
) -> bytes:
    import static_ffmpeg
    import shutil
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"[{task_id}] item_{item_index}" if task_id else "FFmpeg-TTS"

    # ── שלב 1: כתוב כל סגמנט TTS לקובץ ──
    tts_paths: list[pathlib.Path] = []
    for i, seg in enumerate(tts_segments):
        p = tmp_dir / f"tts_{i}.mp3"
        p.write_bytes(seg)
        tts_paths.append(p)

    # ── שלב 2: בנה voice track — כל סגמנט עם adelay לפי זמן הסצנה ──
    inputs: list[str] = []
    for p in tts_paths:
        inputs += ["-i", p.name]

    accumulated_ms = 0.0
    delay_filters: list[str] = []
    for i, (dur, _) in enumerate(zip(scene_durations, tts_paths)):
        delay_ms = int(accumulated_ms)
        delay_filters.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[tts{i}]")
        accumulated_ms += dur * 1000

    n = len(tts_paths)
    mix_inputs = "".join(f"[tts{i}]" for i in range(n))
    delay_filters.append(
        f"{mix_inputs}amix=inputs={n}:duration=longest:normalize=0[voice]"
    )

    voice_path = tmp_dir / "voice_track.mp3"
    cmd_voice = (
        [ffmpeg_exe, "-y"]
        + inputs
        + ["-filter_complex", ";".join(delay_filters), "-map", "[voice]", voice_path.name]
    )
    proc = subprocess.run(
        cmd_voice, cwd=str(tmp_dir),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        logger.error("%s · voice track build failed: %s", prefix, proc.stderr[-500:])
        raise RuntimeError(f"TTS voice track failed:\n{proc.stderr[-300:]}")

    # ── שלב 3: ערבב מוזיקת Veo (נמוכה) + קול TTS ──
    video_path  = tmp_dir / "tts_input.mp4"
    output_path = tmp_dir / "tts_output.mp4"
    video_path.write_bytes(video_bytes)

    filter_mix = (
        f"[0:a]volume={music_volume}[music];"
        f"[1:a]volume=1.0[voice];"
        f"[music][voice]amix=inputs=2:duration=first:normalize=0[aout]"
    )
    cmd_mix = [
        ffmpeg_exe, "-y",
        "-i", video_path.name,
        "-i", voice_path.name,
        "-filter_complex", filter_mix,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path.name,
    ]
    proc = subprocess.run(
        cmd_mix, cwd=str(tmp_dir),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        logger.error("%s · TTS mix failed: %s", prefix, proc.stderr[-500:])
        raise RuntimeError(f"TTS mix failed:\n{proc.stderr[-300:]}")

    result = output_path.read_bytes()
    logger.info("%s · TTS mix done → %d bytes", prefix, len(result))

    for f in tts_paths + [voice_path, video_path, output_path]:
        try: f.unlink()
        except Exception: pass

    return result


async def burn_captions(
    video_bytes: bytes,
    scenes: list[dict],
    scene_durations: list[float],
    lang: str = "he",
    task_id: str = "",
    item_index: int = -1,
) -> bytes:
    """Burn captions into video using FFmpeg + libass, timed to actual clip durations."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_burn,
        video_bytes,
        scenes,
        scene_durations,
        lang,
        task_id,
        item_index,
    )


def _sync_burn(
    video_bytes: bytes,
    scenes: list[dict],
    scene_durations: list[float],
    lang: str = "he",
    task_id: str = "",
    item_index: int = -1,
) -> bytes:
    import static_ffmpeg
    import shutil
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg executable not found")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    input_path  = tmp_dir / "input.mp4"
    ass_path    = tmp_dir / "captions.ass"
    output_path = tmp_dir / "output.mp4"

    input_path.write_bytes(video_bytes)

    width, height = _get_video_dimensions(input_path)

    ass_content = _build_ass_content(scenes, scene_durations, width, height, lang)
    ass_path.write_text(ass_content, encoding="utf-8")

    cmd = [
        ffmpeg_exe, "-y",
        "-i", "input.mp4",
        "-vf", "ass=captions.ass",
        "-c:a", "copy",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "fast",
        "output.mp4",
    ]

    prefix = f"[{task_id}] item_{item_index}" if task_id else "FFmpeg"
    logger.info("%s · burning %s captions (%dx%d) scene_durations=%s",
                prefix, lang, width, height, scene_durations)

    proc = subprocess.run(
        cmd,
        cwd=str(tmp_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        logger.error("%s · FFmpeg stderr: %s", prefix, proc.stderr[-2000:])
        raise RuntimeError(f"FFmpeg failed:\n{proc.stderr[-500:]}")

    output_bytes = output_path.read_bytes()
    logger.info("%s · captions burned %d → %d bytes", prefix, len(video_bytes), len(output_bytes))

    for f in [input_path, ass_path, output_path]:
        try:
            f.unlink()
        except Exception:
            pass

    return output_bytes
async def download_and_merge_clips(
    gcs_uris: list[str],
    project_id: str,
    initial_duration: int,
    extend_duration: int,
    task_id: str = "",
    item_index: int = -1,
) -> tuple[bytes, list[float]]:
    """הורד קליפי Veo, חתוך כל אחד לחלק החדש שלו, חבר עם audio crossfade.
    Returns (merged_bytes, scene_durations) — actual probed duration per scene."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_merge_clips,
        gcs_uris,
        project_id,
        initial_duration,
        extend_duration,
        task_id,
        item_index,
    )


def _sync_merge_clips(
    gcs_uris: list[str],
    project_id: str,
    initial_duration: int,
    extend_duration: int,
    task_id: str = "",
    item_index: int = -1,
) -> bytes:
    import static_ffmpeg
    import shutil
    import time
    from google.cloud import storage as gcs
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"[{task_id}] item_{item_index}" if task_id else "FFmpeg"
    client = gcs.Client(project=project_id)

    # ------------------------------------------------------------------
    # שלב 1 — הורד כל קליפ עם retry (במקביל)
    # ------------------------------------------------------------------
    import concurrent.futures

    clip_paths = [tmp_dir / f"clip_{i}.mp4" for i in range(len(gcs_uris))]

    def _download_clip(args):
        i, uri = args
        bucket_name = uri.split("/")[2]
        blob_name   = "/".join(uri.split("/")[3:])
        clip_path   = clip_paths[i]
        logger.info("%s · downloading clip %d/%d: %s", prefix, i + 1, len(gcs_uris), uri)

        # retry — I2V עלול להיות לא מוכן מיידית ב-GCS
        for attempt in range(5):
            client.bucket(bucket_name).blob(blob_name).download_to_filename(str(clip_path))
            size = clip_path.stat().st_size
            if size > 10_000:  # קובץ תקין
                break
            logger.warning(
                "%s · clip %d too small (%d bytes) — waiting 5s, retry %d/5",
                prefix, i + 1, size, attempt + 1,
            )
            time.sleep(5)
        else:
            raise RuntimeError(f"Clip {i+1} download failed after 5 retries — size={clip_path.stat().st_size}")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        list(executor.map(_download_clip, enumerate(gcs_uris)))

    # ------------------------------------------------------------------
    # שלב 2 — חתוך כל קליפ לחלק החדש שלו
    # ------------------------------------------------------------------
    trimmed_paths  = []
    scene_durations: list[float] = []
    accumulated    = 0.0

    for i, clip_path in enumerate(clip_paths):
        is_last = (i == len(clip_paths) - 1)
        duration = initial_duration if i == 0 else extend_duration
        start    = accumulated
        trimmed  = tmp_dir / f"trimmed_{i}.mp4"

        if is_last:
            # קליפ אחרון (I2V) — חתוך מהתחלה, כל מה שיש
            cmd = [
                ffmpeg_exe, "-y",
                "-i", clip_path.name,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-crf", "18",
                "-preset", "fast",
                trimmed.name,
            ]
        else:
            cmd = [
                ffmpeg_exe, "-y",
                "-ss", str(start),
                "-i", clip_path.name,
                "-t", str(duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-crf", "18",
                "-preset", "fast",
                trimmed.name,
            ]

        proc = subprocess.run(
            cmd, cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

        if proc.returncode != 0:
            logger.error("%s · FFmpeg trim error clip %d: %s", prefix, i, proc.stderr[-500:])
            raise RuntimeError(f"FFmpeg trim failed for clip {i}")

        trimmed_paths.append(trimmed)

        # probe actual trimmed duration for accurate caption sync
        actual_dur = _probe_clip_duration(trimmed)
        if actual_dur <= 0:
            actual_dur = float(duration)
        scene_durations.append(actual_dur)

        accumulated += duration
        logger.info("%s · trimmed clip %d: %.1fs → %.1fs (actual=%.2fs)",
                    prefix, i, start, start + duration, actual_dur)

    # ------------------------------------------------------------------
    # שלב 3 — חבר: video hard cut + audio crossfade
    # ------------------------------------------------------------------
    n = len(trimmed_paths)
    output_path = tmp_dir / "merged.mp4"

    if n == 1:
        proc = subprocess.run(
            [ffmpeg_exe, "-y", "-i", trimmed_paths[0].name, "-c", "copy", "merged.mp4"],
            cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    else:
        inputs = []
        for p in trimmed_paths:
            inputs += ["-i", p.name]

        filter_parts = []

        # וידאו: scale לרזולוציה אחידה + concat נקי
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale=720:1280:force_original_aspect_ratio=decrease,"
                f"pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
            )
        video_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{video_inputs}concat=n={n}:v=1:a=0[vout]")

        # אודיו: acrossfade בשרשרת — כל הקליפים מחוברים
        first_out = "aout" if n == 2 else "atmp1"
        filter_parts.append(
            f"[0:a][1:a]acrossfade=d=0.4:c1=tri:c2=tri[{first_out}]"
        )
        for j in range(2, n):
            prev = "atmp1" if j == 2 else f"atmp{j - 1}"
            out  = "aout"  if j == n - 1 else f"atmp{j}"
            filter_parts.append(
                f"[{prev}][{j}:a]acrossfade=d=0.4:c1=tri:c2=tri[{out}]"
            )

        filter_complex = ";".join(filter_parts)

        cmd = [
            ffmpeg_exe, "-y",
        ] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-crf", "18",
            "-preset", "fast",
            "merged.mp4",
        ]

        logger.info(
            "%s · merging %d clips — video=hard_cut audio=crossfade(0.4s)",
            prefix, n,
        )
        proc = subprocess.run(
            cmd, cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    if proc.returncode != 0:
        logger.error("%s · FFmpeg merge error: %s", prefix, proc.stderr[-2000:])
        raise RuntimeError(f"FFmpeg merge failed:\n{proc.stderr[-500:]}")

    result = output_path.read_bytes()
    logger.info(
        "%s · merged %d clips — video hard_cut + audio crossfade → %d bytes | scene_durations=%s",
        prefix, n, len(result), scene_durations,
    )

    for f in clip_paths + trimmed_paths + [output_path]:
        try: f.unlink()
        except Exception: pass

    return result, scene_durations

async def download_and_merge_clips_s3(
    s3_keys: list[str],
    clip_duration: int,
    task_id: str = "",
    item_index: int = -1,
) -> tuple[bytes, list[float]]:
    """Download Kling clips from S3, merge with audio crossfade.
    Mirror of download_and_merge_clips() but reads from S3 instead of GCS.
    Returns (merged_bytes, scene_durations).
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_merge_clips_s3,
        s3_keys,
        clip_duration,
        task_id,
        item_index,
    )


def _sync_merge_clips_s3(
    s3_keys: list[str],
    clip_duration: int,
    task_id: str = "",
    item_index: int = -1,
) -> tuple[bytes, list[float]]:
    import static_ffmpeg
    import shutil
    import boto3
    from app.config import get_settings
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found")

    cfg = get_settings()
    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"[{task_id}] item_{item_index}" if task_id else "FFmpeg-S3"

    s3 = boto3.client(
        "s3",
        region_name=cfg.s3_region,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
    )

    # Step 1 — download each clip from S3
    clip_paths = [tmp_dir / f"kling_clip_{i}.mp4" for i in range(len(s3_keys))]
    for i, key in enumerate(s3_keys):
        logger.info("%s · downloading S3 clip %d/%d: %s", prefix, i + 1, len(s3_keys), key)
        response = s3.get_object(Bucket=cfg.s3_bucket_name, Key=key)
        clip_paths[i].write_bytes(response["Body"].read())

    # Step 2 — Kling clips are already full clip_duration each, no trimming needed
    scene_durations: list[float] = [float(clip_duration)] * len(s3_keys)

    # Step 3 — merge: video hard cut + audio crossfade (identical to _sync_merge_clips)
    n = len(clip_paths)
    output_path = tmp_dir / "kling_merged.mp4"

    if n == 1:
        proc = subprocess.run(
            [ffmpeg_exe, "-y", "-i", clip_paths[0].name, "-c", "copy", output_path.name],
            cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    else:
        inputs = []
        for p in clip_paths:
            inputs += ["-i", p.name]

        filter_parts = []
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale=720:1280:force_original_aspect_ratio=decrease,"
                f"pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]"
            )
        video_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{video_inputs}concat=n={n}:v=1:a=0[vout]")

        first_out = "aout" if n == 2 else "atmp1"
        filter_parts.append(
            f"[0:a][1:a]acrossfade=d=0.4:c1=tri:c2=tri[{first_out}]"
        )
        for j in range(2, n):
            prev = "atmp1" if j == 2 else f"atmp{j - 1}"
            out  = "aout"  if j == n - 1 else f"atmp{j}"
            filter_parts.append(
                f"[{prev}][{j}:a]acrossfade=d=0.4:c1=tri:c2=tri[{out}]"
            )

        filter_complex = ";".join(filter_parts)
        cmd = [
            ffmpeg_exe, "-y",
        ] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-crf", "18",
            "-preset", "fast",
            output_path.name,
        ]
        logger.info("%s · merging %d Kling clips — video=hard_cut audio=crossfade(0.4s)", prefix, n)
        proc = subprocess.run(
            cmd, cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    if proc.returncode != 0:
        logger.error("%s · FFmpeg merge error: %s", prefix, proc.stderr[-2000:])
        raise RuntimeError(f"FFmpeg merge failed:\n{proc.stderr[-500:]}")

    result = output_path.read_bytes()
    logger.info(
        "%s · merged %d Kling clips → %d bytes | scene_durations=%s",
        prefix, n, len(result), scene_durations,
    )

    for f in clip_paths + [output_path]:
        try: f.unlink()
        except Exception: pass

    return result, scene_durations


def extract_last_frame(video_bytes: bytes) -> bytes:
    """חותך את הframe האחרון מהוידאו ומחזיר PNG bytes."""
    import static_ffmpeg
    import shutil
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    input_path = tmp_dir / "frame_input.mp4"
    frame_path = tmp_dir / "last_frame.png"

    input_path.write_bytes(video_bytes)

    cmd = [
        ffmpeg_exe, "-y",
        "-sseof", "-0.1",
        "-i", "frame_input.mp4",
        "-vframes", "1",
        "-q:v", "2",
        "last_frame.png",
    ]

    proc = subprocess.run(
        cmd, cwd=str(tmp_dir),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg frame extract failed: {proc.stderr[-300:]}")

    frame_bytes = frame_path.read_bytes()
    logger.info("Extracted last frame: %d bytes", len(frame_bytes))

    for f in [input_path, frame_path]:
        try: f.unlink()
        except Exception: pass

    return frame_bytes

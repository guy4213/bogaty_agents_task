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


def _build_ass_content(
    scenes: list[dict],
    initial_duration: int,
    extend_duration: int,
    width: int = 720,
    height: int = 1280,
) -> str:
    """Build ASS subtitle file with Hebrew RTL captions — auto word wrap."""

    # גודל גופן יחסי לרוחב — ~5% מהרוחב
    font_size = max(38, int(width * 0.064))
    margin_h  = int(width * 0.055)   # margin אופקי — ~5.5% מהרוחב
    margin_v  = int(height * 0.10)  # margin אנכי — ~4.7% מהגובה

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
        f"&H00FFFFFF,"    # PrimaryColour — טקסט לבן
        f"&H00FFFFFF,"    # SecondaryColour
        f"&H00000000,"    # OutlineColour — שחור
        f"&H99000000,"    # BackColour — רקע שחור 60% שקיפות
        f"1,0,0,0,"       # Bold, Italic, Underline, StrikeOut
        f"100,100,0,0,"   # ScaleX, ScaleY, Spacing, Angle
        f"4,"             # BorderStyle: 4 = רקע מלא
        f"0,0,"           # Outline, Shadow
        f"2,"             # Alignment: 2 = bottom center
        f"{margin_h},{margin_h},{margin_v},"  # MarginL, MarginR, MarginV
        f"177\n\n"        # Encoding
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = ""
    current_time = 0.0

    for i, scene in enumerate(scenes):
        duration = initial_duration if i == 0 else extend_duration
        start    = current_time
        end      = current_time + duration - 0.3

        caption = scene.get("caption_text", "")
        if caption:
            rtl_text = f"{{\\an2}}{{\\q2}}{caption}"
            events += (
                f"Dialogue: 0,{_seconds_to_ass_time(start)},"
                f"{_seconds_to_ass_time(end)},Hebrew,,0,0,0,,{rtl_text}\n"
            )

        current_time += duration

    return header + events


async def burn_hebrew_captions(
    video_bytes: bytes,
    scenes: list[dict],
    initial_duration: int,
    extend_duration: int,
) -> bytes:
    """Burn Hebrew RTL captions into video using FFmpeg + libass."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_burn,
        video_bytes,
        scenes,
        initial_duration,
        extend_duration,
    )


def _sync_burn(
    video_bytes: bytes,
    scenes: list[dict],
    initial_duration: int,
    extend_duration: int,
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

    # קרא רזולוציה מהוידאו
    width, height = _get_video_dimensions(input_path)

    # בנה ASS עם רזולוציה נכונה
    ass_content = _build_ass_content(scenes, initial_duration, extend_duration, width, height)
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

    logger.info("FFmpeg: burning Hebrew captions (%dx%d font=%d)",
                width, height, max(28, int(width * 0.052)))

    proc = subprocess.run(
        cmd,
        cwd=str(tmp_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        logger.error("FFmpeg stderr: %s", proc.stderr[-2000:])
        raise RuntimeError(f"FFmpeg failed:\n{proc.stderr[-500:]}")

    output_bytes = output_path.read_bytes()
    logger.info("FFmpeg: done %d → %d bytes", len(video_bytes), len(output_bytes))

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
) -> bytes:
    """הורד קליפי Veo, חתוך כל אחד לחלק החדש שלו, חבר עם audio crossfade."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _sync_merge_clips,
        gcs_uris,
        project_id,
        initial_duration,
        extend_duration,
    )


def _sync_merge_clips(
    gcs_uris: list[str],
    project_id: str,
    initial_duration: int,
    extend_duration: int,
) -> bytes:
    import static_ffmpeg
    import shutil
    from google.cloud import storage as gcs
    static_ffmpeg.add_paths()

    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        raise RuntimeError("FFmpeg not found")

    tmp_dir = pathlib.Path("C:/tmp/ffmpeg_work")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    client = gcs.Client(project=project_id)

    # שלב 1 — הורד כל קליפ
    clip_paths = []
    for i, uri in enumerate(gcs_uris):
        bucket_name = uri.split("/")[2]
        blob_name   = "/".join(uri.split("/")[3:])
        clip_path   = tmp_dir / f"clip_{i}.mp4"
        logger.info("Downloading clip %d/%d: %s", i + 1, len(gcs_uris), uri)
        client.bucket(bucket_name).blob(blob_name).download_to_filename(str(clip_path))
        clip_paths.append(clip_path)

    # שלב 2 — חתוך כל קליפ לחלק החדש שלו עם reencode
    trimmed_paths = []
    accumulated   = 0.0

    for i, clip_path in enumerate(clip_paths):
        duration = initial_duration if i == 0 else extend_duration
        start    = accumulated
        trimmed  = tmp_dir / f"trimmed_{i}.mp4"

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
            logger.error("FFmpeg trim error clip %d: %s", i, proc.stderr[-500:])
            raise RuntimeError(f"FFmpeg trim failed for clip {i}")

        trimmed_paths.append(trimmed)
        accumulated += duration
        logger.info("Trimmed clip %d: %.1fs → %.1fs", i, start, start + duration)

    # שלב 3 — חבר עם audio crossfade
    n = len(trimmed_paths)
    output_path = tmp_dir / "merged.mp4"

    if n == 1:
        # קליפ אחד — אין צורך ב-crossfade
        proc = subprocess.run(
            [ffmpeg_exe, "-y", "-i", trimmed_paths[0].name, "-c", "copy", "merged.mp4"],
            cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    else:
        # בנה inputs
        inputs = []
        for p in trimmed_paths:
            inputs += ["-i", p.name]

        # בנה filter_complex עם acrossfade בין כל קליפים עוקבים
        # וידאו: concat
        # אודיו: acrossfade עם 0.3s
        filter_parts = []

        # video concat
        video_inputs = "".join(f"[{i}:v]" for i in range(n))
        filter_parts.append(f"{video_inputs}concat=n={n}:v=1:a=0[vout]")

        # audio crossfade בשרשרת
        if n == 2:
            filter_parts.append(
                f"[0:a][1:a]acrossfade=d=0.3:c1=tri:c2=tri[aout]"
            )
        else:
            # שרשרת: 0+1 → tmp1, tmp1+2 → tmp2, ...
            filter_parts.append(
                f"[0:a][1:a]acrossfade=d=0.3:c1=tri:c2=tri[tmp1]"
            )
            for i in range(2, n):
                out = "[aout]" if i == n - 1 else f"[tmp{i}]"
                filter_parts.append(
                    f"[tmp{i-1}][{i}:a]acrossfade=d=0.3:c1=tri:c2=tri{out}"
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

        logger.info("FFmpeg: merging %d clips with audio crossfade", n)
        proc = subprocess.run(
            cmd, cwd=str(tmp_dir),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    if proc.returncode != 0:
        logger.error("FFmpeg merge error: %s", proc.stderr[-2000:])
        raise RuntimeError(f"FFmpeg merge failed:\n{proc.stderr[-500:]}")

    result = output_path.read_bytes()
    logger.info("Merged %d clips with crossfade → %d bytes", n, len(result))

    # ניקוי
    for f in clip_paths + trimmed_paths + [output_path]:
        try:
            f.unlink()
        except Exception:
            pass

    return result
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
    font_size = max(38, int(width * 0.052))
    margin_h  = int(width * 0.055)   # margin אופקי — ~5.5% מהרוחב
    margin_v  = int(height * 0.047)  # margin אנכי — ~4.7% מהגובה

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "Bold, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Hebrew,Arial,{font_size},&H00FFFFFF,&H00000000,&H00000000,&HAA000000,"
        f"1,0,0,0,100,100,0,0,4,1,0,2,{margin_h},{margin_h},{margin_v},177\n\n"
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
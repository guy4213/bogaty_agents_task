from __future__ import annotations
import asyncio
import logging
import time

from app.config import get_settings
from app.qa.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)

_VEO_POLL_INTERVAL_SEC = 5
_VEO_MAX_POLL_SEC = 600

# In-memory store for Vertex AI video bytes (Vertex returns bytes, not URIs)
_vertex_video_store: dict[str, bytes] = {}

_NEUTRAL_VARIATIONS = [
    "",
    " Maintain continuous background audio and atmosphere from previous clip.",
    " Seamless continuation. Same audio atmosphere and visual energy.",
    " Same visual flow, same audio continuity, same atmosphere.",
]
def _store_video_bytes(data: bytes, key: str) -> None:
    _vertex_video_store[key] = data

def _is_gemini_unavailable(exc: Exception) -> bool:
    """503 UNAVAILABLE + code 8 overload — שניהם transient"""
    msg = str(exc)
    return (
        "503" in msg or
        "UNAVAILABLE" in msg or
        "'code': 8" in msg or
        "high load" in msg
    )

def _get_stored_video_bytes(vertex_uri: str) -> bytes:
    key = vertex_uri.replace("vertex://", "")
    if key not in _vertex_video_store:
        raise RuntimeError(f"Video bytes not found for key: {key}")
    return _vertex_video_store[key]

def _is_veo_overload(exc: Exception) -> bool:
    msg = str(exc)
    return (
        "'code': 8" in msg or
        "'code': 13" in msg or       # ← Internal error — retryable
        "high load" in msg or
        "Internal error" in msg or   # ← 
        "Resource exhausted" in msg or
        "503" in msg or
        "UNAVAILABLE" in msg
    )
def _get_client():
    import google.genai as genai
    return genai.Client(api_key=get_settings().google_ai_api_key)

def _get_vertex_client():
    """Vertex AI client — used for Veo video generation (supports 9:16 + Extend)."""
    import google.genai as genai
    import os
    cfg = get_settings()

    # Set credentials path if provided
    if cfg.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cfg.google_application_credentials

    return genai.Client(
        vertexai=True,
        project=cfg.vertex_project_id,
        location=cfg.vertex_location,
    )

async def _upload_to_gcs(video_bytes: bytes, filename: str) -> str:
    """Upload video bytes to GCS and return gs:// URI for Veo Extend."""
    from google.cloud import storage as gcs
    cfg = get_settings()
    loop = asyncio.get_event_loop()

    def _upload():
        client = gcs.Client(project=cfg.vertex_project_id)
        bucket = client.bucket(cfg.gcs_bucket_name)
        blob = bucket.blob(f"veo-temp/{filename}")
        blob.upload_from_string(video_bytes, content_type="video/mp4")
        return f"gs://{cfg.gcs_bucket_name}/veo-temp/{filename}"

    return await loop.run_in_executor(None, _upload)
# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
async def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    style_reference_bytes: bytes | None = None,
    visual_style_descriptor: str = "",
) -> bytes:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_generate_image
        return await mock_generate_image(prompt, aspect_ratio, style_reference_bytes, visual_style_descriptor)

    breaker = get_breaker("gemini")
    delays = [10, 20, 40]  # קצר יותר מvideo — image generation מהיר יותר

    for attempt in range(4):
        async def _call() -> bytes:
            if style_reference_bytes:
                return await _generate_with_reference(
                    prompt, aspect_ratio, style_reference_bytes, visual_style_descriptor
                )
            return await _generate_first(prompt, aspect_ratio, visual_style_descriptor)

        try:
            return await breaker.call(_call)

        except Exception as exc:
            if _is_gemini_unavailable(exc) and attempt < len(delays):
                wait = delays[attempt]
                logger.warning(
                    "ImageAgent: 503/overload (attempt %d/4) — waiting %ds then retry.",
                    attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                continue
            raise  # שגיאה אחרת — throw מיידי

    raise RuntimeError("generate_image failed after 4 attempts (all 503/overload)")
async def _generate_first(prompt: str, aspect_ratio: str, visual_style_descriptor: str) -> bytes:
    import google.genai.types as types
    client = _get_client()
    style_section = f" Style guide: {visual_style_descriptor}." if visual_style_descriptor else ""

    response = await client.aio.models.generate_images(
        model=get_settings().image_model_first,   
        prompt=f"{prompt}{style_section}",
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            output_mime_type="image/png",
        ),
    )

    if not response.generated_images:
        raise RuntimeError("Imagen returned no images")
    image_bytes = response.generated_images[0].image.image_bytes
    if not image_bytes:
        raise RuntimeError("Imagen returned empty bytes")
    return image_bytes

async def _generate_with_reference(
    prompt: str,
    aspect_ratio: str,
    style_reference_bytes: bytes,
    visual_style_descriptor: str,
) -> bytes:
    import google.genai.types as types
    client = _get_vertex_client()  # ← Vertex AI נדרש ל-edit_image

    style_desc = visual_style_descriptor or "preserve exact visual style, lighting, color palette, and mood"

    anchored_prompt = (
        f"Using the exact visual style from the reference image: {prompt}. "
        f"PRESERVE: color palette, lighting temperature, camera angle, depth of field, and overall mood. "
        f"Generate a NEW scene — do not copy the subject, only the visual language."
    )  # BUGFIX: removed food-specific "plating style" and "dish"

    response = await client.aio.models.edit_image(
        model=get_settings().image_model_style_ref,   # ← Gemini עם style reference
        prompt=anchored_prompt,
        reference_images=[
            types.StyleReferenceImage(
                reference_id=1,
                reference_image=types.Image(image_bytes=style_reference_bytes),
                config=types.StyleReferenceConfig(style_description=style_desc),
            )
        ],
        config=types.EditImageConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
            output_mime_type="image/png",
        ),
    )

    if not response.generated_images:
        raise RuntimeError("edit_image returned no images")
    image_bytes = response.generated_images[0].image.image_bytes
    if not image_bytes:
        raise RuntimeError("edit_image returned empty bytes")
    return image_bytes

# ---------------------------------------------------------------------------
# Video
# ---------------------------------------------------------------------------

async def generate_video_initial(prompt: str) -> str:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_generate_video_initial
        return await mock_generate_video_initial(prompt)

    breaker = get_breaker("gemini")

    async def _call() -> str:
        import google.genai.types as types
        import uuid
        client = _get_vertex_client()

        gcs_prefix = f"gs://{cfg.gcs_bucket_name}/veo-temp/{uuid.uuid4().hex}"

        operation = await client.aio.models.generate_videos(
            model=cfg.veo_model,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                duration_seconds=cfg.veo_initial_duration_sec,
                aspect_ratio="9:16",
                output_gcs_uri=gcs_prefix,
            ),
        )
        operation = await _poll(client, operation)

        uri = operation.result.generated_videos[0].video.uri
        logger.info("VideoAgent: initial clip -> GCS: %s", uri)
        return uri   # gs://... URI אמיתי מה-result

    return await breaker.call(_call)


async def extend_video(video_uri: str, prompt: str, extend_index: int) -> str:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_extend_video
        return await mock_extend_video(video_uri, prompt, extend_index)

    breaker = get_breaker("gemini")
    delays = [15, 30, 60]
    last_exc: Exception | None = None

    for attempt, variation in enumerate(_NEUTRAL_VARIATIONS):
        final_prompt = prompt + variation

        async def _call(p=final_prompt) -> str:
            import google.genai.types as types
            import uuid
            client = _get_vertex_client()
            gcs_prefix = f"gs://{cfg.gcs_bucket_name}/veo-temp/{uuid.uuid4().hex}"

            operation = await client.aio.models.generate_videos(
                model=cfg.veo_model,
                prompt=p,
                video=types.Video(uri=video_uri, mime_type="video/mp4"),
                config=types.GenerateVideosConfig(
                    duration_seconds=cfg.veo_extend_duration_sec,
                    output_gcs_uri=gcs_prefix,
                ),
            )
            operation = await _poll(client, operation)
            uri = operation.result.generated_videos[0].video.uri
            logger.info("VideoAgent: extend %d -> GCS: %s", extend_index + 1, uri)
            return uri

        try:
            result = await breaker.call(_call)
            return result  

        except Exception as exc:
            last_exc = exc
            if _is_veo_overload(exc) and attempt < len(delays):
                wait = delays[attempt]
                logger.warning(
                    "VideoAgent: extend %d overload (attempt %d/4) — waiting %ds. variation='%s'",
                    extend_index + 1, attempt + 1, wait, variation,
                )
                await asyncio.sleep(wait)
                continue
            raise  # שגיאה שאינה overload — throw מיידי

    raise last_exc or RuntimeError(
        f"extend_video failed after 4 attempts — extend_index={extend_index}"
    )

async def download_video(video_uri: str) -> bytes:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_download_video
        return await mock_download_video(video_uri)

    # GCS URI — download via google-cloud-storage
    if video_uri.startswith("gs://"):
        from google.cloud import storage as gcs
        loop = asyncio.get_event_loop()

        def _download():
            client = gcs.Client(project=cfg.vertex_project_id)
            bucket_name = video_uri.split("/")[2]
            blob_name = "/".join(video_uri.split("/")[3:])
            return client.bucket(bucket_name).blob(blob_name).download_as_bytes()

        return await loop.run_in_executor(None, _download)



    # Gemini API URI
    import httpx
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            video_uri,
            headers={"Authorization": f"Bearer {cfg.google_ai_api_key}"},
        )
        resp.raise_for_status()
        return resp.content
async def _poll(client, operation):
    deadline = time.monotonic() + _VEO_MAX_POLL_SEC
    while not operation.done:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Veo operation timed out after {_VEO_MAX_POLL_SEC}s")
        await asyncio.sleep(_VEO_POLL_INTERVAL_SEC)
        operation = await client.aio.operations.get(operation)
    if operation.error:
        raise RuntimeError(f"Veo operation failed: {operation.error}")
    return operation



def _extract_uri(operation) -> str:
    """
    Vertex AI מחזיר video_bytes ישירות, לא URI.
    נשמור את ה-bytes זמנית ונחזיר placeholder.
    """
    try:
        video = operation.result.generated_videos[0].video
        # Vertex AI — bytes ישירות
        if video.video_bytes:
            return f"vertex_bytes://{id(video.video_bytes)}"
        # Gemini API — URI
        if video.uri:
            return video.uri
        raise RuntimeError("Video operation completed but both URI and bytes are empty")
    except (IndexError, AttributeError) as exc:
        raise RuntimeError(f"Could not extract video from operation: {exc}") from exc


def _extract_video_bytes(operation) -> bytes:
    """Extract raw video bytes from a completed Vertex AI operation."""
    try:
        video = operation.result.generated_videos[0].video
        if video.video_bytes:
            return video.video_bytes
        raise RuntimeError("No video bytes in operation result")
    except (IndexError, AttributeError) as exc:
        raise RuntimeError(f"Could not extract video bytes: {exc}") from exc
    
async def generate_video_from_frame(
    frame_bytes: bytes,
    prompt: str,
    extend_index: int,
) -> str:
    cfg = get_settings()

    if cfg.dry_run:
        from app.mocks.mock_clients import mock_extend_video
        return await mock_extend_video("dry_run_frame", prompt, extend_index)

    breaker = get_breaker("gemini")
    delays  = [15, 30, 60]
    last_exc: Exception | None = None

    for attempt, variation in enumerate(_NEUTRAL_VARIATIONS):
        final_prompt = prompt + variation

        async def _call(p=final_prompt) -> str:
            import google.genai.types as types
            import uuid
            client = _get_vertex_client()

            gcs_prefix = f"gs://{cfg.gcs_bucket_name}/veo-temp/{uuid.uuid4().hex}"

            image = types.Image(
                image_bytes=frame_bytes,
                mime_type="image/png",
            )

            operation = await client.aio.models.generate_videos(
                model=cfg.veo_model,
                prompt=p,
                image=image,
                config=types.GenerateVideosConfig(
                    duration_seconds=8,  # ← I2V תומך רק ב-8,4,6 — לא 7
                    aspect_ratio="9:16",
                    output_gcs_uri=gcs_prefix,
                ),
            )
            operation = await _poll(client, operation)
            uri = operation.result.generated_videos[0].video.uri
            logger.info(
                "VideoAgent: payoff image-to-video -> GCS: %s", uri
            )
            return uri

        try:
            result = await breaker.call(_call)
            return result  # ← חזור מיידי בהצלחה

        except Exception as exc:
            last_exc = exc
            if _is_veo_overload(exc) and attempt < len(delays):
                wait = delays[attempt]
                logger.warning(
                    "VideoAgent: payoff overload (attempt %d/4) — waiting %ds.",
                    attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                continue
            raise

    raise last_exc or RuntimeError(
        f"generate_video_from_frame failed after 4 attempts — extend_index={extend_index}"
    )
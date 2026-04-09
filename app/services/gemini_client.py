from __future__ import annotations
import asyncio
import logging

from app.config import get_settings
from app.qa.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)


async def generate_image(
    prompt: str,
    aspect_ratio: str = "1:1",
    style_reference_bytes: bytes | None = None,
) -> bytes:
    breaker = get_breaker("gemini")

    async def _call() -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _sync_generate_image, prompt, aspect_ratio, style_reference_bytes
        )

    return await breaker.call(_call)


def _sync_generate_image(
    prompt: str,
    aspect_ratio: str,
    style_reference_bytes: bytes | None,
) -> bytes:
    import io
    import google.generativeai as genai

    cfg = get_settings()
    genai.configure(api_key=cfg.google_ai_api_key)

    model = genai.ImageGenerationModel(cfg.image_model)

    final_prompt = prompt
    if style_reference_bytes:
        final_prompt = f"Using the style of the reference image: {prompt}"

    result = model.generate_images(
        prompt=final_prompt,
        number_of_images=1,
        aspect_ratio=aspect_ratio,
    )

    if not result.images:
        raise RuntimeError("Nano Banana 2 returned no images")

    image = result.images[0]
    buf = io.BytesIO()
    image._pil_image.save(buf, format="PNG")
    return buf.getvalue()


async def generate_video_initial(prompt: str) -> str:
    cfg = get_settings()
    breaker = get_breaker("gemini")

    async def _call() -> str:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _sync_generate_video_initial, prompt),
            timeout=cfg.veo_timeout_sec,
        )

    return await breaker.call(_call)


def _sync_generate_video_initial(prompt: str) -> str:
    import google.generativeai as genai

    cfg = get_settings()
    genai.configure(api_key=cfg.google_ai_api_key)

    try:
        model = genai.VideoGenerationModel(cfg.veo_model)
        operation = model.generate_video(
            prompt=prompt,
            generation_config={
                "duration_seconds": cfg.veo_initial_duration_sec,
                "aspect_ratio": "9:16",
                "generate_audio": True,
            },
        )
        video = operation.result()
        return video.uri
    except AttributeError:
        logger.error(
            "Veo SDK interface mismatch — verify google-generativeai version "
            "supports VideoGenerationModel."
        )
        raise


async def extend_video(video_uri: str, prompt: str, extend_index: int) -> str:
    cfg = get_settings()
    breaker = get_breaker("gemini")

    async def _call() -> str:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _sync_extend_video, video_uri, prompt),
            timeout=cfg.veo_timeout_sec,
        )

    return await breaker.call(_call)


def _sync_extend_video(video_uri: str, prompt: str) -> str:
    import google.generativeai as genai

    cfg = get_settings()
    genai.configure(api_key=cfg.google_ai_api_key)

    try:
        model = genai.VideoGenerationModel(cfg.veo_model)
        operation = model.extend_video(
            video_uri=video_uri,
            prompt=prompt,
            generation_config={"duration_seconds": cfg.veo_extend_duration_sec},
        )
        video = operation.result()
        return video.uri
    except AttributeError:
        logger.error(
            "Veo SDK extend_video interface mismatch. "
            "Extend is only available on veo-3.1-generate-preview (Full), not Lite."
        )
        raise


async def download_video(video_uri: str) -> bytes:
    import httpx
    cfg = get_settings()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            video_uri,
            headers={"Authorization": f"Bearer {cfg.google_ai_api_key}"},
        )
        resp.raise_for_status()
        return resp.content
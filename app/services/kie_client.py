from __future__ import annotations
import asyncio
import base64
import logging
import uuid

import httpx

from app.config import get_settings
from app.qa.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().kie_api_key}",
        "Content-Type": "application/json",
    }


def _is_kling_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503, 504)
    msg = str(exc)
    return any(code in msg for code in ("429", "502", "503", "504"))


async def _submit_task(payload: dict) -> str:
    cfg = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{cfg.kie_api_base}/api/v1/jobs/createTask",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Kling submit failed: {data}")
        return data["data"]["taskId"]


async def _poll_task(task_id: str) -> str:
    cfg = get_settings()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + cfg.kie_poll_timeout_sec
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            if loop.time() > deadline:
                raise RuntimeError(
                    f"Kling task {task_id} timed out after {cfg.kie_poll_timeout_sec}s"
                )
            await asyncio.sleep(cfg.kie_poll_interval_sec)
            resp = await client.get(
                f"{cfg.kie_api_base}/api/v1/jobs/queryTask",
                headers=_headers(),
                params={"taskId": task_id},
            )
            resp.raise_for_status()
            data = resp.json()
            status = data["data"]["status"]
            if status == "succeed":
                return data["data"]["works"][0]["resource_list"][0]["url"]
            if status == "failed":
                raise RuntimeError(f"Kling task {task_id} failed")


async def _download_video_url(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def generate_video_initial(prompt: str) -> str:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_generate_video_initial
        return await mock_generate_video_initial(prompt)

    breaker = get_breaker("kling")
    delays = [10, 30, 60]

    for attempt in range(4):
        async def _call() -> str:
            payload = {
                "model": cfg.kie_model_t2v,
                "input": {
                    "prompt": prompt,
                    "duration": str(cfg.kie_clip_duration),
                    "aspect_ratio": "9:16",
                    "mode": "pro",
                    "cfg_scale": 0.5,
                },
            }
            task_id = await _submit_task(payload)
            logger.info("Kling: submitted initial task %s", task_id)
            video_url = await _poll_task(task_id)
            video_bytes = await _download_video_url(video_url)
            s3_key = f"kling-temp/{uuid.uuid4().hex}/clip_initial.mp4"
            from app.services.s3_client import upload_bytes
            await upload_bytes(s3_key, video_bytes, content_type="video/mp4")
            logger.info("Kling: initial clip uploaded -> %s", s3_key)
            return s3_key

        try:
            return await breaker.call(_call)
        except Exception as exc:
            if _is_kling_retryable(exc) and attempt < len(delays):
                wait = delays[attempt]
                logger.warning(
                    "Kling: generate_video_initial retryable error (attempt %d/4) — waiting %ds. err=%s",
                    attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
                continue
            raise

    raise RuntimeError("generate_video_initial failed after 4 attempts")


async def extend_video(video_uri: str, prompt: str, extend_index: int) -> str:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_extend_video
        return await mock_extend_video(video_uri, prompt, extend_index)

    # Download previous clip from S3, extract last frame
    from app.services.s3_client import download_bytes as s3_download
    from app.services.caption_service import extract_last_frame

    loop = asyncio.get_event_loop()
    video_bytes = await s3_download(video_uri)
    frame_bytes = await loop.run_in_executor(None, extract_last_frame, video_bytes)

    return await generate_video_from_frame(frame_bytes, prompt, extend_index)


async def generate_video_from_frame(
    frame_bytes: bytes,
    prompt: str,
    extend_index: int,
) -> str:
    cfg = get_settings()
    if cfg.dry_run:
        from app.mocks.mock_clients import mock_extend_video
        return await mock_extend_video("dry_run_frame", prompt, extend_index)

    breaker = get_breaker("kling")
    delays = [10, 30, 60]
    image_b64 = base64.b64encode(frame_bytes).decode("utf-8")

    for attempt in range(4):
        async def _call() -> str:
            payload = {
                "model": cfg.kie_model_i2v,
                "input": {
                    "prompt": prompt,
                    "image": f"data:image/png;base64,{image_b64}",
                    "duration": str(cfg.kie_clip_duration),
                    "aspect_ratio": "9:16",
                    "mode": "pro",
                    "cfg_scale": 0.5,
                },
            }
            task_id = await _submit_task(payload)
            logger.info("Kling: submitted i2v task %s (extend %d)", task_id, extend_index)
            video_url = await _poll_task(task_id)
            video_bytes = await _download_video_url(video_url)
            s3_key = f"kling-temp/{uuid.uuid4().hex}/clip_{extend_index}.mp4"
            from app.services.s3_client import upload_bytes
            await upload_bytes(s3_key, video_bytes, content_type="video/mp4")
            logger.info("Kling: extend %d clip uploaded -> %s", extend_index, s3_key)
            return s3_key

        try:
            return await breaker.call(_call)
        except Exception as exc:
            if _is_kling_retryable(exc) and attempt < len(delays):
                wait = delays[attempt]
                logger.warning(
                    "Kling: generate_video_from_frame retryable error (attempt %d/4) — waiting %ds. err=%s",
                    attempt + 1, wait, exc,
                )
                await asyncio.sleep(wait)
                continue
            raise

    raise RuntimeError(f"generate_video_from_frame failed after 4 attempts (extend_index={extend_index})")


async def cleanup_kling_temp_clips(s3_keys: list[str]) -> None:
    """Delete intermediate clip files from S3 after successful merge."""
    from app.services.s3_client import delete_object
    for key in s3_keys:
        try:
            await delete_object(key)
        except Exception as exc:
            logger.warning("Kling temp cleanup failed for %s: %s", key, exc)

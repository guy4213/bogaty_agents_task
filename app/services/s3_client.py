from __future__ import annotations
import asyncio
import json
import logging
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_client():
    cfg = get_settings()
    return boto3.client(
        "s3",
        region_name=cfg.s3_region,
        aws_access_key_id=cfg.aws_access_key_id,
        aws_secret_access_key=cfg.aws_secret_access_key,
    )


def _sync_upload_bytes(key: str, data: bytes, content_type: str) -> None:
    cfg = get_settings()
    client = _get_client()
    client.put_object(
        Bucket=cfg.s3_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def _sync_presign(key: str, expiry_sec: int = 3600) -> str:
    cfg = get_settings()
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": cfg.s3_bucket_name, "Key": key},
        ExpiresIn=expiry_sec,
    )


@retry(
    retry=retry_if_exception_type((BotoCoreError, ClientError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _sync_upload_bytes, key, data, content_type)
    logger.info("S3 upload: s3://%s/%s (%d bytes)", get_settings().s3_bucket_name, key, len(data))
    return key


async def upload_json(key: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return await upload_bytes(key, payload, content_type="application/json")


async def upload_text(key: str, text: str) -> str:
    return await upload_bytes(key, text.encode("utf-8"), content_type="text/plain; charset=utf-8")


async def upload_file(local_path: str, key: str, content_type: str = "application/octet-stream") -> str:
    cfg = get_settings()
    loop = asyncio.get_event_loop()
    client = _get_client()
    await loop.run_in_executor(None, lambda: client.upload_file(local_path, cfg.s3_bucket_name, key))
    return key


async def presigned_url(key: str, expiry_sec: int = 3600) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_presign, key, expiry_sec)


def asset_key(task_id: str, platform: str, content_type: str, item_index: int, filename: str) -> str:
    return f"tasks/{task_id}/{platform}/{content_type}/item_{item_index}/{filename}"
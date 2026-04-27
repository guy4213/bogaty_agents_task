from __future__ import annotations
import asyncio
import logging
import time
from typing import NamedTuple

import anthropic
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import get_settings
from app.models import ServiceHealth
from app.qa.circuit_breaker import get_breaker, CircuitOpenError

logger = logging.getLogger(__name__)


class HealthResult(NamedTuple):
    service: str
    healthy: bool
    latency_ms: int | None
    error: str | None


# ---------------------------------------------------------------------------
# Individual service pings
# ---------------------------------------------------------------------------

async def _ping_claude() -> HealthResult:
    cfg = get_settings()
    t0 = time.monotonic()
    try:
        client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
        await client.messages.create(
            model=cfg.claude_model,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("claude", True, latency, None)
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("claude", False, latency, str(exc))


async def _ping_gemini() -> HealthResult:
    """Lightweight Gemini API check — list available models."""
    cfg = get_settings()
    t0 = time.monotonic()
    try:
        import google.generativeai as genai
        genai.configure(api_key=cfg.google_ai_api_key)
        # list_models is a lightweight call that confirms API key validity
        _ = list(genai.list_models())
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("gemini", True, latency, None)
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("gemini", False, latency, str(exc))


async def _ping_s3() -> HealthResult:
    cfg = get_settings()
    t0 = time.monotonic()
    try:
        s3 = boto3.client(
            "s3",
            region_name=cfg.s3_region,
            aws_access_key_id=cfg.aws_access_key_id,
            aws_secret_access_key=cfg.aws_secret_access_key,
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: s3.head_bucket(Bucket=cfg.s3_bucket_name),
        )
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("s3", True, latency, None)
    except (BotoCoreError, ClientError) as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("s3", False, latency, str(exc))
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("s3", False, latency, str(exc))


async def _ping_kling() -> HealthResult:
    """Lightweight kie.ai health check — queries a non-existent task to confirm API is reachable."""
    cfg = get_settings()
    t0 = time.monotonic()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{cfg.kie_api_base}/api/v1/jobs/queryTask",
                headers={
                    "Authorization": f"Bearer {cfg.kie_api_key}",
                    "Content-Type": "application/json",
                },
                params={"taskId": "health-check"},
            )
            latency = int((time.monotonic() - t0) * 1000)
            # 401 = bad key, 4xx with JSON = API is up, key may be wrong
            if resp.status_code == 401:
                return HealthResult("kling", False, latency, "Invalid API key")
            # Any response that isn't a network error means the service is reachable
            # A 404/400 for a fake taskId is expected and means the API is healthy
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            healthy = resp.status_code in (200, 400, 404) or data.get("code") is not None
            return HealthResult("kling", healthy, latency, None if healthy else f"Unexpected status {resp.status_code}")
    except Exception as exc:
        latency = int((time.monotonic() - t0) * 1000)
        return HealthResult("kling", False, latency, str(exc))


# ---------------------------------------------------------------------------
# Aggregate health check
# ---------------------------------------------------------------------------

get_breaker("kling")   # register on startup

_PING_FNS = {
    "claude": _ping_claude,
    "gemini": _ping_gemini,
    "s3":     _ping_s3,
    "kling":  _ping_kling,
}


async def check_all_services() -> list[ServiceHealth]:
    """Run all health checks in parallel and return ServiceHealth records."""
    results = await asyncio.gather(
        *[fn() for fn in _PING_FNS.values()],
        return_exceptions=True,
    )

    health_records: list[ServiceHealth] = []
    for result in results:
        if isinstance(result, Exception):
            # Shouldn't happen since each ping catches its own errors
            logger.error("Unexpected health check error: %s", result)
            continue

        breaker = get_breaker(result.service)
        status = "healthy" if result.healthy else "down"

        # Reflect circuit breaker state in status
        if breaker.state.value == "open":
            status = "down"
        elif breaker.state.value == "half_open":
            status = "degraded"

        health_records.append(
            ServiceHealth(
                service=result.service,
                status=status,
                circuit_state=breaker.state.value,
                latency_ms=result.latency_ms,
                error=result.error,
            )
        )

    return health_records


async def preflight_check(required_services: list[str]) -> dict[str, bool]:
    """
    Check only the services required for this pipeline.
    Returns {service: ok} dict. Raises PreflightError if any required service is down.
    """
    all_health = await check_all_services()
    health_map = {h.service: h for h in all_health}

    results: dict[str, bool] = {}
    failures: list[str] = []

    for svc in required_services:
        if svc not in health_map:
            results[svc] = False
            failures.append(f"{svc}: not checked")
            continue

        h = health_map[svc]
        ok = h.status == "healthy"
        results[svc] = ok

        if not ok:
            failures.append(f"{svc}: {h.error or h.status}")

    if failures:
        raise PreflightError(
            f"Pre-flight failed for services: {'; '.join(failures)}"
        )

    return results


# ---------------------------------------------------------------------------
# Pipeline → required services mapping
# ---------------------------------------------------------------------------

PIPELINE_SERVICES = {
    "text_only":  ["claude", "s3"],
    "text_image": ["claude", "gemini", "s3"],
    "full_video": ["claude", "gemini", "kling", "s3"],  # gemini=images, kling=video
}


class PreflightError(Exception):
    """Raised when one or more required services fail the pre-flight check."""
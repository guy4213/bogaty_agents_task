from __future__ import annotations
import logging
from typing import Any

import anthropic
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, before_sleep_log,
)

from app.config import get_settings
from app.qa.circuit_breaker import get_breaker

logger = logging.getLogger(__name__)

_RETRYABLE = (
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE)


@retry(
    retry=retry_if_exception_type(_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def complete(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 4096,
):
    cfg = get_settings()

    if cfg.dry_run:
        from app.mocks.mock_clients import mock_claude_complete
        return await mock_claude_complete(messages, system, max_tokens)

    breaker = get_breaker("claude")

    async def _call():
        client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
        kwargs: dict[str, Any] = dict(
            model=cfg.claude_model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system
        return await client.messages.create(**kwargs)

    return await breaker.call(_call, is_retryable_error=_is_retryable)


def estimate_cost(message) -> float:
    if not hasattr(message, "usage") or not hasattr(message.usage, "input_tokens"):
        return 0.0
    cost = (message.usage.input_tokens / 1_000_000) * 3.0 \
         + (message.usage.output_tokens / 1_000_000) * 15.0
    return round(cost, 6)
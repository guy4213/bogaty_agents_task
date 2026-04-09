from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Tripped — rejecting all requests
    HALF_OPEN = "half_open" # Recovery probe in progress


@dataclass
class CircuitBreaker:
    """
    Per-service circuit breaker.
    - Trips to OPEN after `threshold` consecutive failures within `window_sec`.
    - Probes recovery every `recovery_sec` with a single test request.
    - Closes on successful probe.
    """

    service_name: str
    threshold: int = 5
    window_sec: float = 120.0
    recovery_sec: float = 60.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _failure_timestamps: list[float] = field(default_factory=list, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _last_probe_at: float | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(
        self,
        fn: Callable[[], Awaitable],
        *,
        is_retryable_error: Callable[[Exception], bool] | None = None,
    ):
        """
        Execute `fn` through the circuit breaker.
        Raises CircuitOpenError immediately if the circuit is open (and not ready to probe).
        """
        async with self._lock:
            await self._maybe_transition_to_half_open()

            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit for '{self.service_name}' is OPEN — "
                    f"service unavailable, retry after {self.recovery_sec}s"
                )

        try:
            result = await fn()
            await self._on_success()
            return result
        except Exception as exc:
            if is_retryable_error is None or is_retryable_error(exc):
                await self._on_failure()
            raise

    async def _on_success(self) -> None:
        async with self._lock:
            self._consecutive_failures = 0
            self._failure_timestamps.clear()
            if self._state != CircuitState.CLOSED:
                logger.info(
                    "Circuit breaker '%s': CLOSED (recovered)", self.service_name
                )
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._last_probe_at = None

    async def _on_failure(self) -> None:
        now = time.monotonic()
        async with self._lock:
            # Purge timestamps outside the window
            self._failure_timestamps = [
                t for t in self._failure_timestamps if now - t < self.window_sec
            ]
            self._failure_timestamps.append(now)
            self._consecutive_failures += 1

            if (
                self._state == CircuitState.CLOSED
                and len(self._failure_timestamps) >= self.threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = now
                logger.warning(
                    "Circuit breaker '%s': OPEN after %d failures in %.0fs window",
                    self.service_name,
                    self.threshold,
                    self.window_sec,
                )

            elif self._state == CircuitState.HALF_OPEN:
                # Probe failed — back to open, reset probe timer
                self._state = CircuitState.OPEN
                self._opened_at = now
                self._last_probe_at = now
                logger.warning(
                    "Circuit breaker '%s': probe FAILED — back to OPEN",
                    self.service_name,
                )

    async def _maybe_transition_to_half_open(self) -> None:
        """Called inside the lock. Transition OPEN → HALF_OPEN if recovery window elapsed."""
        if self._state != CircuitState.OPEN:
            return
        now = time.monotonic()
        last = self._last_probe_at or self._opened_at or 0.0
        if now - last >= self.recovery_sec:
            self._state = CircuitState.HALF_OPEN
            self._last_probe_at = now
            logger.info(
                "Circuit breaker '%s': HALF_OPEN — sending recovery probe",
                self.service_name,
            )

    def status_dict(self) -> dict:
        return {
            "service": self.service_name,
            "circuit_state": self._state.value,
            "consecutive_failures": self._consecutive_failures,
            "failures_in_window": len(self._failure_timestamps),
        }


class CircuitOpenError(Exception):
    """Raised when a request is rejected because the circuit is open."""


# ---------------------------------------------------------------------------
# Global registry — one breaker per external service
# ---------------------------------------------------------------------------

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(service: str) -> CircuitBreaker:
    if service not in _breakers:
        from app.config import get_settings
        cfg = get_settings()
        _breakers[service] = CircuitBreaker(
            service_name=service,
            threshold=cfg.circuit_breaker_threshold,
            window_sec=cfg.circuit_breaker_window_sec,
            recovery_sec=cfg.circuit_breaker_recovery_sec,
        )
    return _breakers[service]


def all_breakers() -> dict[str, CircuitBreaker]:
    return _breakers
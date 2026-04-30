"""Async retry + circuit breaker helper.

Direct port of :java:`com.zqnt.sdk.client.grpc.GrpcResilience` adapted for
``asyncio`` and ``grpc.aio``. Wrap an awaitable factory with
:meth:`GrpcResilience.execute` to gain:

* Retry on transient gRPC status codes (UNAVAILABLE / DEADLINE_EXCEEDED /
  RESOURCE_EXHAUSTED / UNKNOWN / INTERNAL) with exponential backoff.
* A simple half-open circuit breaker: after ``failure_threshold`` consecutive
  failures the breaker OPENS and rejects calls for ``wait_duration_ms``;
  the next call probes — if it succeeds the breaker closes again.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import grpc

from ..config.resilience import ResilienceConfig
from ..exceptions import ZequentClientError, ZequentRetryExhaustedError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Retryable gRPC status codes (matches Java GrpcResilience.isRetryable).
_RETRYABLE_CODES: frozenset[grpc.StatusCode] = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.UNKNOWN,
        grpc.StatusCode.INTERNAL,
    }
)


class CircuitBreakerOpen(ZequentClientError):
    """Raised when a call is rejected because the circuit breaker is OPEN."""


class GrpcResilience:
    """Async retry + circuit breaker. Thread-safe within a single event loop."""

    def __init__(self, config: ResilienceConfig) -> None:
        self._config = config
        self._failure_count = 0
        self._circuit_open = False
        self._opened_at_monotonic: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(self, op: Callable[[], Awaitable[T]]) -> T:
        """Execute *op* with retry + circuit breaker.

        On exhaustion of all retry attempts for a *retryable* error this
        raises :class:`~client_sdk.exceptions.ZequentRetryExhaustedError`
        with the original exception preserved as ``__cause__``.
        Non-retryable errors propagate unchanged.
        """
        await self._check_circuit()

        attempt = 0
        retried = False
        last_exc: BaseException | None = None
        max_attempts = self._config.max_retry_attempts

        while attempt <= max_attempts:
            try:
                result = await op()
                await self._record_success()
                return result
            except CircuitBreakerOpen:
                raise
            except BaseException as exc:  # noqa: BLE001 - we re-raise after policy
                last_exc = exc
                if attempt < max_attempts and _is_retryable(exc):
                    delay = self._config.retry_delay_millis * (attempt + 1) / 1000.0
                    logger.warning(
                        "Attempt %d failed (%s), retrying in %.2fs",
                        attempt + 1,
                        _short_exc(exc),
                        delay,
                    )
                    attempt += 1
                    retried = True
                    await asyncio.sleep(delay)
                    continue
                await self._record_failure()
                # Surface as typed SDK error.
                if retried and _is_retryable(exc):
                    raise ZequentRetryExhaustedError(
                        f"All {attempt + 1} attempts failed: {_short_exc(exc)}",
                        attempts=attempt + 1,
                    ) from exc
                raise

        # Defensive – should be unreachable thanks to raise inside the loop.
        assert last_exc is not None
        raise last_exc

    @property
    def is_circuit_open(self) -> bool:
        return self._circuit_open

    @property
    def failure_count(self) -> int:
        return self._failure_count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _check_circuit(self) -> None:
        if not self._circuit_open:
            return
        async with self._lock:
            if not self._circuit_open:
                return
            elapsed_ms = (time.monotonic() - self._opened_at_monotonic) * 1000
            if elapsed_ms >= self._config.circuit_breaker_wait_duration_millis:
                logger.info("Circuit breaker probing after wait duration")
                self._circuit_open = False
                self._failure_count = 0
                return
            raise CircuitBreakerOpen("Circuit breaker is OPEN - rejecting call")

    async def _record_success(self) -> None:
        async with self._lock:
            if self._failure_count or self._circuit_open:
                logger.debug("Resilience: success — resetting state")
            self._failure_count = 0
            self._circuit_open = False

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            logger.warning(
                "Resilience: failure %d/%d",
                self._failure_count,
                self._config.circuit_breaker_failure_threshold,
            )
            if (
                not self._circuit_open
                and self._failure_count
                >= self._config.circuit_breaker_failure_threshold
            ):
                self._circuit_open = True
                self._opened_at_monotonic = time.monotonic()
                logger.error(
                    "Circuit breaker OPENED after %d failures", self._failure_count
                )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, grpc.aio.AioRpcError):
        return exc.code() in _RETRYABLE_CODES
    if isinstance(exc, grpc.RpcError):
        code = getattr(exc, "code", lambda: None)()
        return code in _RETRYABLE_CODES if code is not None else True
    if isinstance(exc, asyncio.TimeoutError):
        return True
    if isinstance(exc, ValueError):
        # Validation errors — never retry.
        return False
    if isinstance(exc, asyncio.CancelledError):
        return False
    # Unknown exceptions: retry by default (matches Java behaviour).
    return True


def _short_exc(exc: BaseException) -> str:
    if isinstance(exc, grpc.aio.AioRpcError):
        return f"{exc.code().name}: {exc.details() or ''}"
    return f"{type(exc).__name__}: {exc}"

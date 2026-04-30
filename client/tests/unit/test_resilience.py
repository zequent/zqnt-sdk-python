"""Unit tests for ``GrpcResilience`` (retry + circuit breaker)."""

from __future__ import annotations

import asyncio
from typing import Any

import grpc
import pytest

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.grpc_.resilience import CircuitBreakerOpen, GrpcResilience


class _FakeAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        super().__init__(code, initial_metadata=None, trailing_metadata=None, details="boom")


def _fast_config(**overrides: Any) -> ResilienceConfig:
    base = ResilienceConfig(
        max_retry_attempts=3,
        retry_delay_millis=1,
        circuit_breaker_failure_threshold=3,
        circuit_breaker_wait_duration_millis=20,
        connection_timeout_seconds=1,
        request_timeout_seconds=1,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


@pytest.mark.asyncio
async def test_retries_on_unavailable_and_succeeds() -> None:
    r = GrpcResilience(_fast_config())
    calls = {"n": 0}

    async def op() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeAioRpcError(grpc.StatusCode.UNAVAILABLE)
        return "ok"

    result = await r.execute(op)
    assert result == "ok"
    assert calls["n"] == 3
    assert r.failure_count == 0


@pytest.mark.asyncio
async def test_no_retry_on_invalid_argument() -> None:
    r = GrpcResilience(_fast_config())
    calls = {"n": 0}

    async def op() -> None:
        calls["n"] += 1
        raise _FakeAioRpcError(grpc.StatusCode.INVALID_ARGUMENT)

    with pytest.raises(grpc.aio.AioRpcError):
        await r.execute(op)
    assert calls["n"] == 1
    assert r.failure_count == 1


@pytest.mark.asyncio
async def test_no_retry_on_validation_value_error() -> None:
    r = GrpcResilience(_fast_config())
    calls = {"n": 0}

    async def op() -> None:
        calls["n"] += 1
        raise ValueError("bad input")

    with pytest.raises(ValueError):
        await r.execute(op)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold_and_recovers_after_wait() -> None:
    r = GrpcResilience(_fast_config())

    async def fail() -> None:
        raise _FakeAioRpcError(grpc.StatusCode.INVALID_ARGUMENT)

    # 3 hard failures → circuit open
    for _ in range(3):
        with pytest.raises(grpc.aio.AioRpcError):
            await r.execute(fail)

    assert r.is_circuit_open is True

    # Next call rejected immediately
    with pytest.raises(CircuitBreakerOpen):
        await r.execute(fail)

    # Wait for circuit timeout, then a successful call should close it
    await asyncio.sleep(0.05)

    async def ok() -> str:
        return "ok"

    assert await r.execute(ok) == "ok"
    assert r.is_circuit_open is False
    assert r.failure_count == 0

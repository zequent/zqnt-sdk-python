"""Tests for the B1+B2 wiring: unary RPCs go through GrpcResilience and
exhausted-retry failures surface as ``ZequentRetryExhaustedError``.
"""

from __future__ import annotations

from typing import Any

import grpc
import pytest

from client_sdk import ZequentClientError, ZequentRetryExhaustedError
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.generated import remote_control_pb2
from client_sdk.grpc_.resilience import GrpcResilience
from client_sdk.models import TakeoffRequest
from client_sdk.remote_control.client import RemoteControlClient


class _FakeAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        super().__init__(code, initial_metadata=None, trailing_metadata=None, details="boom")


class _FlakyStub:
    """Stub whose TakeOff fails N times then succeeds."""

    def __init__(self, fail_count: int, code: grpc.StatusCode) -> None:
        self._remaining = fail_count
        self._code = code
        self.calls = 0

    def TakeOff(self, request, timeout=None):  # noqa: N802 - gRPC convention
        self.calls += 1

        async def _coro():
            if self._remaining > 0:
                self._remaining -= 1
                raise _FakeAioRpcError(self._code)
            from google.protobuf import empty_pb2

            return remote_control_pb2.RemoteControlResponse(
                hasErrors=False,
                tid="tid-1",
                sn="DOCK-1",
                responseMessage="ok",
                empty=empty_pb2.Empty(),
            )

        return _coro()


def _build_client(stub: Any, max_retries: int = 3) -> RemoteControlClient:
    c = RemoteControlClient.__new__(RemoteControlClient)
    c._channel = None
    c._resilience = ResilienceConfig(
        max_retry_attempts=max_retries,
        retry_delay_millis=1,
        circuit_breaker_failure_threshold=99,
    )
    c._resilience_helper = GrpcResilience(c._resilience)
    c._stub = stub
    return c


def _takeoff() -> TakeoffRequest:
    return TakeoffRequest(sn="DOCK-1", latitude=1.0, longitude=2.0, altitude=10.0)


@pytest.mark.asyncio
async def test_unary_retries_on_unavailable_then_succeeds() -> None:
    stub = _FlakyStub(fail_count=2, code=grpc.StatusCode.UNAVAILABLE)
    client = _build_client(stub)

    resp = await client.takeoff(_takeoff())

    assert resp is not None
    assert stub.calls == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_unary_retries_exhausted_raises_typed_error() -> None:
    stub = _FlakyStub(fail_count=99, code=grpc.StatusCode.UNAVAILABLE)
    client = _build_client(stub, max_retries=2)

    with pytest.raises(ZequentRetryExhaustedError) as excinfo:
        await client.takeoff(_takeoff())

    assert excinfo.value.attempts == 3  # initial + 2 retries
    # Original error preserved.
    assert isinstance(excinfo.value.__cause__, grpc.aio.AioRpcError)
    # Inherits SDK base.
    assert isinstance(excinfo.value, ZequentClientError)


@pytest.mark.asyncio
async def test_unary_non_retryable_propagates_as_grpc_error() -> None:
    stub = _FlakyStub(fail_count=99, code=grpc.StatusCode.INVALID_ARGUMENT)
    client = _build_client(stub)

    # Non-retryable: raw gRPC error.
    with pytest.raises(grpc.aio.AioRpcError):
        await client.takeoff(_takeoff())

    assert stub.calls == 1  # no retries

"""Unary RPCs go through GrpcResilience and exhausted-retry failures surface as
``ZequentRetryExhaustedError``.
"""

from __future__ import annotations

from typing import Any

import grpc
import pytest
from zqnt_api.generated.zqnt import common_pb2

from client_sdk import ZequentClientError, ZequentRetryExhaustedError
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.connector.client import ConnectorClient
from client_sdk.grpc_.resilience import GrpcResilience


class _FakeAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, code: grpc.StatusCode) -> None:
        super().__init__(code, initial_metadata=None, trailing_metadata=None, details="boom")


class _FlakyStub:
    """Stub whose DeregisterAsset fails N times then succeeds."""

    def __init__(self, fail_count: int, code: grpc.StatusCode) -> None:
        self._remaining = fail_count
        self._code = code
        self.calls = 0

    def DeregisterAsset(self, request, timeout=None):  # noqa: N802 - gRPC convention
        self.calls += 1

        async def _coro():
            if self._remaining > 0:
                self._remaining -= 1
                raise _FakeAioRpcError(self._code)
            return common_pb2.CommandResponse(has_errors=False)

        return _coro()


def _build_client(stub: Any, max_retries: int = 3) -> ConnectorClient:
    c = ConnectorClient.__new__(ConnectorClient)
    c._channel = None
    c._resilience = ResilienceConfig(
        max_retry_attempts=max_retries,
        retry_delay_millis=1,
        circuit_breaker_failure_threshold=99,
    )
    c._resilience_helper = GrpcResilience(c._resilience)
    c._stub = stub
    return c


@pytest.mark.asyncio
async def test_unary_retries_on_unavailable_then_succeeds() -> None:
    stub = _FlakyStub(fail_count=2, code=grpc.StatusCode.UNAVAILABLE)
    client = _build_client(stub)

    await client.deregister_asset("DOCK-1")

    assert stub.calls == 3


@pytest.mark.asyncio
async def test_unary_retries_exhausted_raises_typed_error() -> None:
    stub = _FlakyStub(fail_count=99, code=grpc.StatusCode.UNAVAILABLE)
    client = _build_client(stub, max_retries=2)

    with pytest.raises(ZequentRetryExhaustedError) as excinfo:
        await client.deregister_asset("DOCK-1")

    assert excinfo.value.attempts == 3
    assert isinstance(excinfo.value.__cause__, grpc.aio.AioRpcError)
    assert isinstance(excinfo.value, ZequentClientError)


@pytest.mark.asyncio
async def test_unary_non_retryable_propagates_as_grpc_error() -> None:
    stub = _FlakyStub(fail_count=99, code=grpc.StatusCode.INVALID_ARGUMENT)
    client = _build_client(stub)

    with pytest.raises(grpc.aio.AioRpcError):
        await client.deregister_asset("DOCK-1")

    assert stub.calls == 1

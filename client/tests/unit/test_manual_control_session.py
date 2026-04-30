"""Unit tests for ``ManualControlInputSession``."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.protobuf import empty_pb2

from client_sdk.generated import remote_control_pb2
from client_sdk.models.remote_control_input import ManualControlInput
from client_sdk.remote_control.manual_control_session import (
    ManualControlInputSession,
)


def _ok() -> remote_control_pb2.RemoteControlResponse:
    return remote_control_pb2.RemoteControlResponse(
        hasErrors=False,
        tid="tid-mc",
        sn="DOCK-1",
        responseMessage="ok",
        empty=empty_pb2.Empty(),
    )


class _FakeCall:
    """Awaitable stand-in for a gRPC client-streaming call.

    Drains the request iterator into ``self.received`` and resolves to the
    configured response on ``await``.
    """

    def __init__(self, request_iter, response) -> None:
        self._request_iter = request_iter
        self._response = response
        self.received: list[Any] = []
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def __await__(self):
        async def _drain():
            try:
                async for item in self._request_iter:
                    if self._cancelled:
                        break
                    self.received.append(item)
            except asyncio.CancelledError:
                pass
            if self._cancelled:
                raise asyncio.CancelledError()
            return self._response

        return _drain().__await__()


class _FakeStub:
    def __init__(self, response) -> None:
        self.last_call: _FakeCall | None = None
        self._response = response

    def ManualControlInput(self, request_iter, timeout=None):  # noqa: N802
        call = _FakeCall(request_iter, self._response)
        self.last_call = call
        return call


@pytest.mark.asyncio
async def test_send_input_then_complete_returns_response() -> None:
    stub = _FakeStub(_ok())
    session = ManualControlInputSession(sn="DOCK-1", stub=stub, timeout=5.0)

    async with session:
        await session.send_input(ManualControlInput(roll=0.1, pitch=0.2))
        await session.send_input(ManualControlInput(yaw=0.3, throttle=0.4))
        resp = await session.complete()

    assert resp.success is True
    assert stub.last_call is not None
    assert len(stub.last_call.received) == 2
    first = stub.last_call.received[0]
    assert first.base.sn == "DOCK-1"
    assert first.request.roll == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_complete_twice_raises() -> None:
    stub = _FakeStub(_ok())
    session = ManualControlInputSession(sn="DOCK-1", stub=stub, timeout=5.0)
    await session.complete()
    with pytest.raises(RuntimeError):
        await session.complete()


@pytest.mark.asyncio
async def test_send_after_close_raises() -> None:
    stub = _FakeStub(_ok())
    session = ManualControlInputSession(sn="DOCK-1", stub=stub, timeout=5.0)
    await session.close()
    with pytest.raises(RuntimeError):
        await session.send_input(ManualControlInput(roll=0.1))


@pytest.mark.asyncio
async def test_complete_with_error_cancels() -> None:
    stub = _FakeStub(_ok())
    session = ManualControlInputSession(sn="DOCK-1", stub=stub, timeout=5.0)
    await session.send_input(ManualControlInput(roll=0.1))
    await session.complete_with_error(RuntimeError("bad"))
    assert stub.last_call is not None
    assert stub.last_call._cancelled is True


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    stub = _FakeStub(_ok())
    session = ManualControlInputSession(sn="DOCK-1", stub=stub, timeout=5.0)
    await session.close()
    await session.close()  # must not raise

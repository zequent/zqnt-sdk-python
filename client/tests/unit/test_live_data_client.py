"""Unit tests for ``LiveDataClient`` (unary + streaming)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.protobuf import empty_pb2

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.generated import common_pb2, live_data_pb2
from client_sdk.live_data.client import LiveDataClient
from client_sdk.models.live_data import (
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    StreamTelemetryRequest,
)


def _ok_unary(message: str = "ok") -> live_data_pb2.LiveDataResponse:
    return live_data_pb2.LiveDataResponse(
        hasErrors=False,
        tid="tid-1",
        sn="DOCK-1",
        responseMessage=message,
        empty=empty_pb2.Empty(),
    )


def _stream_started(video_id: str = "vid-1") -> live_data_pb2.LiveDataResponse:
    return live_data_pb2.LiveDataResponse(
        hasErrors=False,
        tid="tid-2",
        sn="DOCK-1",
        liveStreamStartResponse=common_pb2.LiveStreamStartResponse(
            streamUrl="rtmp://example/live",
            videoId=video_id,
        ),
    )


class _FakeUnaryStub:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001
            self.calls[name] = (request, timeout)
            return self._response

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


def _build_client(stub: Any) -> LiveDataClient:
    c = LiveDataClient.__new__(LiveDataClient)
    c._channel = None
    c._resilience = ResilienceConfig(retry_delay_millis=1, max_retry_attempts=1)
    from client_sdk.grpc_.resilience import GrpcResilience
    c._resilience_helper = GrpcResilience(c._resilience)
    c._stub = stub
    return c


# ---------------------------------------------------------------------------
# Unary RPCs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_live_stream_decodes_response() -> None:
    stub = _FakeUnaryStub(_stream_started("VID-9"))
    client = _build_client(stub)

    resp = await client.start_live_stream(
        LiveDataStartLiveStreamRequest(
            sn="DOCK-1",
            video_id="VID-9",
            stream_server="rtmp://srv",
        )
    )

    assert resp.success is True
    assert resp.live_stream_start is not None
    assert resp.live_stream_start.video_id == "VID-9"
    assert resp.live_stream_start.stream_url == "rtmp://example/live"
    sent_request = stub.calls["StartLiveStream"][0]
    assert sent_request.base.sn == "DOCK-1"
    assert sent_request.request.videoId == "VID-9"


@pytest.mark.asyncio
async def test_stop_live_stream_validates_inputs() -> None:
    client = _build_client(_FakeUnaryStub(_ok_unary()))
    with pytest.raises(ValueError):
        await client.stop_live_stream(
            LiveDataStopLiveStreamRequest(sn="", video_id="x")
        )
    with pytest.raises(ValueError):
        await client.stop_live_stream(
            LiveDataStopLiveStreamRequest(sn="DOCK-1", video_id="")
        )


@pytest.mark.asyncio
async def test_change_lens_sends_proto() -> None:
    stub = _FakeUnaryStub(_ok_unary())
    client = _build_client(stub)

    resp = await client.change_lens(ChangeLensRequest(sn="DOCK-1", lens="WIDE"))
    assert resp.success is True
    sent = stub.calls["ChangeLens"][0]
    assert sent.base.sn == "DOCK-1"
    assert sent.request.lens == "WIDE"


@pytest.mark.asyncio
async def test_change_zoom_rejects_non_positive() -> None:
    client = _build_client(_FakeUnaryStub(_ok_unary()))
    with pytest.raises(ValueError, match="zoom"):
        await client.change_zoom(ChangeZoomRequest(sn="DOCK-1", zoom=0))


@pytest.mark.asyncio
async def test_change_zoom_with_lens() -> None:
    stub = _FakeUnaryStub(_ok_unary())
    client = _build_client(stub)
    await client.change_zoom(ChangeZoomRequest(sn="DOCK-1", zoom=4, lens="ZOOM"))
    sent = stub.calls["ChangeZoom"][0]
    assert sent.request.zoom == 4
    assert sent.request.lens == "ZOOM"


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def _telemetry_frame(asset_id: str = "AST-1") -> live_data_pb2.LiveDataTelemetryResponse:
    return live_data_pb2.LiveDataTelemetryResponse(
        tid="tid-stream",
        sn="DOCK-1",
        hasErrors=False,
        assetId=asset_id,
        assetTelemetry=live_data_pb2.AssetTelemetry(
            id="AST-1",
            latitude=12.34,
            longitude=56.78,
            heading=180.0,
        ),
    )


class _AsyncIterStream:
    """Wraps a list of frames as an async iterator (simulates server stream)."""

    def __init__(self, frames: list[Any]) -> None:
        self._frames = list(frames)

    def __aiter__(self) -> "_AsyncIterStream":
        return self

    async def __anext__(self):
        if not self._frames:
            raise StopAsyncIteration
        return self._frames.pop(0)


class _StreamStub:
    def __init__(self, frames: list[Any]) -> None:
        self._frames = frames
        self.last_request = None
        self.call_count = 0

    def StreamTelemetry(self, request):  # noqa: N802 - gRPC name
        self.last_request = request
        self.call_count += 1
        # Only the first invocation yields frames; subsequent reconnects get
        # an empty stream so the test can stop the handle deterministically.
        frames = self._frames if self.call_count == 1 else []
        return _AsyncIterStream(frames)


@pytest.mark.asyncio
async def test_stream_telemetry_pumps_frames_into_callback() -> None:
    stub = _StreamStub([_telemetry_frame("AST-1"), _telemetry_frame("AST-2")])
    client = _build_client(stub)

    received: list[Any] = []

    async def on_data(frame):
        received.append(frame)

    handle = client.stream_telemetry(
        StreamTelemetryRequest(sn="DOCK-1", frequency_ms=200, duration_seconds=0),
        on_data,
    )

    # Wait for stream to drain naturally; the loop will then attempt a reconnect
    # backoff – we stop before that completes.
    await asyncio.sleep(0.05)
    await handle.stop()

    assert len(received) == 2
    assert received[0].asset_id == "AST-1"
    assert received[0].asset_telemetry is not None
    assert received[0].asset_telemetry.latitude == pytest.approx(12.34)
    assert handle.is_stopped is True


@pytest.mark.asyncio
async def test_stream_handle_stop_is_idempotent() -> None:
    stub = _StreamStub([])
    client = _build_client(stub)
    handle = client.stream_telemetry(
        StreamTelemetryRequest(sn="DOCK-1"),
        lambda _f: None,
    )
    await handle.stop()
    await handle.stop()  # must not raise
    assert handle.is_stopped is True

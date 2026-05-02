"""LiveData sub-client – unary RPCs + server-streaming telemetry subscription.

Mirrors :java:`com.zqnt.sdk.client.livedata.application.LiveData` adapted for
``asyncio`` + ``grpc.aio``. The streaming subscription transparently
reconnects on transient gRPC errors using exponential backoff.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import grpc
import grpc.aio

from ..config.resilience import ResilienceConfig
from ..grpc_.resilience import GrpcResilience
from ..models._validation import validate_non_blank, validate_sn
from ..models.live_data import (
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataResponse,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    StreamTelemetryRequest,
    StreamTelemetryResponse,
)
from ._converters import (
    change_lens_to_proto,
    change_zoom_to_proto,
    proto_to_live_data_response,
    proto_to_stream_telemetry_response,
    start_live_stream_to_proto,
    stop_live_stream_to_proto,
    stream_telemetry_request_to_proto,
)
from .stream_handle import StreamHandle

logger = logging.getLogger(__name__)

OnTelemetry = Callable[[StreamTelemetryResponse], Awaitable[None] | None]
OnError = Callable[[BaseException], Awaitable[None] | None]


# Cap for exponential backoff between reconnect attempts.
_MAX_BACKOFF_SECONDS = 30.0

# gRPC status codes treated as transient (mirrors Java GrpcResilience).
_RETRYABLE_CODES = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.UNKNOWN,
        grpc.StatusCode.INTERNAL,
    }
)


class LiveDataClient:
    """Async client for the ``LiveDataService`` gRPC API."""

    def __init__(
        self,
        channel: grpc.aio.Channel,
        resilience: ResilienceConfig,
    ) -> None:
        try:
            from ..generated import live_data_pb2_grpc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - generation step
            raise ImportError("Protobuf stubs not found. Run scripts/generate_protos.sh first.") from exc

        self._channel = channel
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)
        self._stub = live_data_pb2_grpc.LiveDataServiceStub(channel)

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    # ------------------------------------------------------------------
    # Unary RPCs
    # ------------------------------------------------------------------

    async def start_live_stream(self, request: LiveDataStartLiveStreamRequest) -> LiveDataResponse:
        validate_sn(request.sn)
        validate_non_blank("videoId", request.video_id)
        validate_non_blank("streamServer", request.stream_server)
        logger.info("StartLiveStream: sn=%s, videoId=%s", request.sn, request.video_id)

        proto = await self._resilience_helper.execute(
            lambda: self._stub.StartLiveStream(start_live_stream_to_proto(request), timeout=self._timeout)
        )
        return proto_to_live_data_response(proto)

    async def stop_live_stream(self, request: LiveDataStopLiveStreamRequest) -> LiveDataResponse:
        validate_sn(request.sn)
        validate_non_blank("videoId", request.video_id)
        logger.info("StopLiveStream: sn=%s, videoId=%s", request.sn, request.video_id)

        proto = await self._resilience_helper.execute(
            lambda: self._stub.StopLiveStream(stop_live_stream_to_proto(request), timeout=self._timeout)
        )
        return proto_to_live_data_response(proto)

    async def change_lens(self, request: ChangeLensRequest) -> LiveDataResponse:
        validate_sn(request.sn)
        validate_non_blank("lens", request.lens)
        logger.info("ChangeLens: sn=%s, lens=%s", request.sn, request.lens)

        proto = await self._resilience_helper.execute(
            lambda: self._stub.ChangeLens(change_lens_to_proto(request), timeout=self._timeout)
        )
        return proto_to_live_data_response(proto)

    async def change_zoom(self, request: ChangeZoomRequest) -> LiveDataResponse:
        validate_sn(request.sn)
        if request.zoom <= 0:
            raise ValueError(f"zoom must be positive, got: {request.zoom}")
        logger.info("ChangeZoom: sn=%s, zoom=%s", request.sn, request.zoom)

        proto = await self._resilience_helper.execute(
            lambda: self._stub.ChangeZoom(change_zoom_to_proto(request), timeout=self._timeout)
        )
        return proto_to_live_data_response(proto)

    # ------------------------------------------------------------------
    # Server-streaming subscription
    # ------------------------------------------------------------------

    def stream_telemetry(
        self,
        request: StreamTelemetryRequest,
        on_telemetry: OnTelemetry,
        on_error: OnError | None = None,
    ) -> StreamHandle:
        """Subscribe to the telemetry stream.

        Returns a :class:`StreamHandle` that owns a background task pumping
        frames into ``on_telemetry``. The task auto-reconnects on transient
        gRPC errors with exponential backoff (capped at 30s); the attempt
        counter resets each time a frame is received. Call
        :meth:`StreamHandle.stop` to terminate.

        ``on_telemetry`` and ``on_error`` may be sync or async callables.
        """
        validate_sn(request.sn)

        handle = StreamHandle()
        task = asyncio.create_task(
            self._stream_loop(request, on_telemetry, on_error, handle),
            name=f"livedata-stream-{request.sn}",
        )
        handle._bind(task)
        return handle

    async def _stream_loop(
        self,
        request: StreamTelemetryRequest,
        on_telemetry: OnTelemetry,
        on_error: OnError | None,
        handle: StreamHandle,
    ) -> None:
        attempt = 0
        max_attempts = self._resilience.max_retry_attempts
        base_delay = self._resilience.retry_delay_millis / 1000.0

        while not handle.is_stopped:
            data_received = False
            try:
                proto_request = stream_telemetry_request_to_proto(request)
                logger.info("StreamTelemetry connect: sn=%s", request.sn)
                stream = self._stub.StreamTelemetry(proto_request)
                async for frame in stream:
                    if handle.is_stopped:
                        break
                    data_received = True
                    attempt = 0  # reset on successful frame
                    try:
                        result = on_telemetry(proto_to_stream_telemetry_response(frame))
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:  # noqa: BLE001 - user callback shouldn't kill stream
                        logger.exception("on_telemetry callback raised")
                # Stream ended cleanly (server-side close)
                if handle.is_stopped:
                    return
                logger.info("StreamTelemetry ended cleanly; reconnecting")
            except asyncio.CancelledError:
                logger.info("StreamTelemetry cancelled")
                return
            except grpc.aio.AioRpcError as exc:
                if handle.is_stopped:
                    return
                code = exc.code()
                logger.warning(
                    "StreamTelemetry gRPC error: %s (%s)",
                    code.name if code else "?",
                    exc.details(),
                )
                if code not in _RETRYABLE_CODES:
                    await _maybe_call(on_error, exc)
                    return
            except Exception as exc:  # noqa: BLE001
                if handle.is_stopped:
                    return
                logger.exception("StreamTelemetry unexpected error")
                await _maybe_call(on_error, exc)
                return

            if data_received:
                attempt = 0
            attempt += 1
            if attempt > max_attempts:
                logger.error(
                    "StreamTelemetry: exceeded %d reconnect attempts; giving up",
                    max_attempts,
                )
                await _maybe_call(
                    on_error,
                    RuntimeError(f"stream_telemetry exceeded {max_attempts} reconnect attempts"),
                )
                return
            delay = min(base_delay * attempt, _MAX_BACKOFF_SECONDS)
            logger.info("StreamTelemetry reconnect attempt %d in %.2fs", attempt, delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return


async def _maybe_call(cb: Any, exc: BaseException) -> None:
    if cb is None:
        return
    try:
        result = cb(exc)
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001
        logger.exception("on_error callback raised")

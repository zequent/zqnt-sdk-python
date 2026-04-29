"""
TelemetryPublisher – sends asset / sub-asset telemetry to the ZQNT
LiveDataService using the ``ProduceTelemetry`` client-streaming RPC.

The publisher keeps a long-lived gRPC stream open and feeds it from an
internal bounded queue.  If the connection drops it reconnects automatically
with exponential backoff (1 s → 2 s → 4 s … up to 60 s).  Frames produced
while the stream is down are buffered up to QUEUE_MAX_SIZE; older frames are
silently dropped when the buffer is full::

    publisher = TelemetryPublisher(host="platform.example.com", port=50052, sn="DOCK001")
    await publisher.connect()

    # from your telemetry loop:
    await publisher.publish_asset_telemetry(
        AssetTelemetry(id="DOCK001", latitude=47.5, longitude=9.7)
    )
    await publisher.publish_subasset_telemetry(
        SubAssetTelemetry(id="DRONE001", horizontal_speed=5.0)
    )

    # on shutdown:
    await publisher.close()
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from ..models.telemetry import AssetTelemetry, SubAssetTelemetry

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals the generator to stop cleanly


class TelemetryPublisher:
    """
    Wraps the LiveDataService ``ProduceTelemetry`` streaming RPC.

    Reconnects automatically on connection loss using exponential backoff.
    Frames published while disconnected are buffered; when the buffer is full
    the oldest (newest?) frame is dropped silently.

    Args:
        host:           LiveDataService host.
        port:           LiveDataService port (default 50052).
        sn:             Serial number of the asset producing the telemetry.
        queue_max_size: Max buffered frames while disconnected (default 1000).
    """

    _BACKOFF_INITIAL = 1.0
    _BACKOFF_MAX = 60.0

    def __init__(
        self,
        host: str,
        port: int = 50052,
        sn: str = "",
        queue_max_size: int = 1000,
    ) -> None:
        self._host = host
        self._port = port
        self._sn = sn
        self._queue_max_size = queue_max_size

        self._closed = False
        self._stop_event: asyncio.Event | None = None
        self._queue: asyncio.Queue | None = None
        self._stream_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the channel and start the background streaming / reconnect task."""
        try:
            import grpc.aio  # noqa: F401 – verify availability
            from ..generated import live_data_pb2_grpc  # type: ignore[import]  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Protobuf stubs not found. Run  scripts/generate_protos.sh  first."
            ) from exc

        self._closed = False
        self._stop_event = asyncio.Event()
        self._queue = asyncio.Queue(maxsize=self._queue_max_size)
        self._stream_task = asyncio.create_task(
            self._run_stream(), name="telemetry-producer"
        )
        logger.info("TelemetryPublisher started for %s:%d", self._host, self._port)

    async def close(self) -> None:
        """Drain the queue, stop the reconnect loop, and release resources."""
        self._closed = True
        if self._stop_event:
            self._stop_event.set()
        if self._queue:
            # Wake up the generator so it can exit cleanly.
            try:
                self._queue.put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                pass
        if self._stream_task:
            try:
                await asyncio.wait_for(self._stream_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    pass
        logger.info("TelemetryPublisher closed")

    # ------------------------------------------------------------------
    # Public publish methods
    # ------------------------------------------------------------------

    async def publish_asset_telemetry(self, telemetry: AssetTelemetry) -> None:
        """Enqueue an asset-telemetry frame. Drops the frame if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_asset_request(telemetry)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Telemetry queue full, dropping asset frame")

    async def publish_subasset_telemetry(self, telemetry: SubAssetTelemetry) -> None:
        """Enqueue a sub-asset-telemetry frame. Drops the frame if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_subasset_request(telemetry)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Telemetry queue full, dropping sub-asset frame")

    # ------------------------------------------------------------------
    # Internal – reconnect loop
    # ------------------------------------------------------------------

    async def _run_stream(self) -> None:
        """
        Background task: opens the gRPC stream and feeds it from the queue.
        On failure reconnects with exponential backoff.
        """
        import grpc
        import grpc.aio
        try:
            from ..generated import live_data_pb2_grpc  # type: ignore[import]
        except ImportError:
            logger.error("live_data_pb2 not available – telemetry disabled")
            return

        backoff = self._BACKOFF_INITIAL

        while not self._closed:
            # Each attempt gets its own stop signal so stale generators exit promptly.
            gen_stop = asyncio.Event()
            channel = None
            try:
                channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
                stub = live_data_pb2_grpc.LiveDataServiceStub(channel)
                logger.info(
                    "Telemetry stream connecting to %s:%d", self._host, self._port
                )

                response = await stub.ProduceTelemetry(
                    self._stream_generator(gen_stop)
                )

                if self._closed:
                    return

                if response.hasErrors:
                    logger.warning(
                        "ProduceTelemetry stream ended with error: %s",
                        response.responseMessage,
                    )
                else:
                    logger.debug("ProduceTelemetry stream ended cleanly")

                backoff = self._BACKOFF_INITIAL  # reset on success

            except Exception as exc:
                if self._closed:
                    return
                logger.warning(
                    "Telemetry stream error (%s: %s), reconnecting in %.1fs",
                    type(exc).__name__,
                    exc,
                    backoff,
                )
            finally:
                gen_stop.set()
                if channel:
                    await channel.close()

            if not self._closed:
                # Wait for backoff duration; stop immediately if close() is called.
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=backoff  # type: ignore[union-attr]
                    )
                    return  # stop_event was set → close() called
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, self._BACKOFF_MAX)

    async def _stream_generator(self, gen_stop: asyncio.Event):
        """
        Async generator fed into ProduceTelemetry.

        Polls the queue with a 1-second timeout so it can react promptly to
        both gen_stop (current stream ended) and self._closed (shutdown).
        """
        assert self._queue is not None
        while not self._closed and not gen_stop.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            if item is _SENTINEL:
                # Restore SENTINEL so close() can detect it too.
                try:
                    self._queue.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    pass
                return
            yield item

    # ------------------------------------------------------------------
    # Proto builders
    # ------------------------------------------------------------------

    def _base(self):
        from ..generated import common_pb2  # type: ignore[import]
        from google.protobuf import timestamp_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=self._sn, timestamp=ts)

    def _build_asset_request(self, t: AssetTelemetry):
        from ..generated import live_data_pb2  # type: ignore[import]
        from google.protobuf import timestamp_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()

        kwargs: dict = {"id": t.id, "timestamp": ts}
        _set_optional(kwargs, t, {
            "latitude": "latitude",
            "longitude": "longitude",
            "absolute_altitude": "absoluteAltitude",
            "relative_altitude": "relativeAltitude",
            "environment_temp": "environmentTemp",
            "inside_temp": "insideTemp",
            "humidity": "humidity",
            "heading": "heading",
            "wind_speed": "windSpeed",
        })
        if t.mode is not None:
            kwargs["mode"] = int(t.mode)
        if t.rainfall is not None:
            kwargs["rainfall"] = int(t.rainfall)
        if t.cover_state is not None:
            kwargs["coverState"] = int(t.cover_state)
        if t.manual_control_state is not None:
            kwargs["manualControlState"] = int(t.manual_control_state)

        return live_data_pb2.ProduceTelemetryRequest(
            base=self._base(),
            type=0,  # ASSET_TELEMETRY
            assetTelemetry=live_data_pb2.AssetTelemetry(**kwargs),
        )

    def _build_subasset_request(self, t: SubAssetTelemetry):
        from ..generated import live_data_pb2  # type: ignore[import]
        from google.protobuf import timestamp_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()

        kwargs: dict = {"id": t.id, "timestamp": ts}
        _set_optional(kwargs, t, {
            "latitude": "latitude",
            "longitude": "longitude",
            "absolute_altitude": "absoluteAltitude",
            "relative_altitude": "relativeAltitude",
            "horizontal_speed": "horizontalSpeed",
            "vertical_speed": "verticalSpeed",
            "wind_speed": "windSpeed",
            "wind_direction": "windDirection",
            "heading": "heading",
            "gear": "gear",
            "height_limit": "heightLimit",
            "home_distance": "homeDistance",
            "total_movement_distance": "totalMovementDistance",
            "total_movement_time": "totalMovementTime",
            "country": "country",
        })
        if t.mode is not None:
            kwargs["mode"] = int(t.mode)

        return live_data_pb2.ProduceTelemetryRequest(
            base=self._base(),
            type=1,  # SUBASSET_TELEMETRY
            subAssetTelemetry=live_data_pb2.SubAssetTelemetry(**kwargs),
        )


def _set_optional(target: dict, source, field_map: dict[str, str]) -> None:
    """Copy non-None fields from *source* into *target* using the proto field names."""
    for py_field, proto_field in field_map.items():
        value = getattr(source, py_field, None)
        if value is not None:
            target[proto_field] = value

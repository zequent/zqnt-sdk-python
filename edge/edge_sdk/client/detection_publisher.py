"""
DetectionPublisher – sends detection batches to the ZQNT LiveDataService
using the ``ProduceDetection`` client-streaming RPC.

The publisher keeps a long-lived gRPC stream open and feeds it from an
internal bounded queue.  If the connection drops it reconnects automatically
with exponential backoff (1 s → 2 s → 4 s … up to 60 s).  Batches produced
while the stream is down are buffered up to QUEUE_MAX_SIZE; older batches are
silently dropped when the buffer is full::

    publisher = DetectionPublisher(host="platform.example.com", port=50052, sn="DRONE001")
    await publisher.connect()

    await publisher.publish_detection_batch(DetectionBatch(
        detections=[
            DetectionResult(object_id="obj1", object_type="person", confidence=0.95,
                            bounding_box=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4)),
        ],
        stream_url="rtmp://example.com/live/stream1",
    ))

    await publisher.close()
"""

import asyncio
import logging
import uuid

from ..auth import default_edge_token, platform_channel
from ..models.common import DetectionBatch

logger = logging.getLogger(__name__)

_SENTINEL = object()


class DetectionPublisher:
    """
    Wraps the LiveDataService ``ProduceDetection`` streaming RPC.

    Reconnects automatically on connection loss using exponential backoff.
    Batches published while disconnected are buffered; when the buffer is full
    the oldest batch is dropped silently.

    Args:
        host:           LiveDataService host.
        port:           LiveDataService port (default 50052).
        sn:             Serial number of the asset producing the detections.
        queue_max_size: Max buffered batches while disconnected (default 1000).
    """

    _BACKOFF_INITIAL = 1.0
    _BACKOFF_MAX = 60.0

    def __init__(
        self,
        host: str,
        port: int = 50052,
        sn: str = "",
        queue_max_size: int = 1000,
        token: str | None = None,
    ) -> None:
        self._host = host
        self._token = token if token is not None else default_edge_token()
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
        import grpc.aio  # noqa: F401 – verify availability
        from zqnt_utils.generated.zqnt import live_data_pb2_grpc  # noqa: F401

        self._closed = False
        self._stop_event = asyncio.Event()
        self._queue = asyncio.Queue(maxsize=self._queue_max_size)
        self._stream_task = asyncio.create_task(self._run_stream(), name="detection-producer")
        logger.info("DetectionPublisher started for %s:%d (sn=%s)", self._host, self._port, self._sn)

    async def close(self) -> None:
        """Drain the queue, stop the reconnect loop, and release resources."""
        self._closed = True
        if self._stop_event:
            self._stop_event.set()
        if self._queue:
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
        logger.info("DetectionPublisher closed (sn=%s)", self._sn)

    # ------------------------------------------------------------------
    # Public publish methods
    # ------------------------------------------------------------------

    async def publish_detection_batch(self, batch: DetectionBatch) -> None:
        """Enqueue a detection batch. Drops the batch if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_detection_request(batch)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Detection queue full, dropping batch (sn=%s)", self._sn)

    # ------------------------------------------------------------------
    # Internal – reconnect loop
    # ------------------------------------------------------------------

    async def _run_stream(self) -> None:
        from zqnt_utils.generated.zqnt import live_data_pb2_grpc

        backoff = self._BACKOFF_INITIAL

        while not self._closed:
            gen_stop = asyncio.Event()
            channel = None
            try:
                channel = platform_channel(self._host, self._port, self._token)
                stub = live_data_pb2_grpc.LiveDataServiceStub(channel)
                logger.info("Detection stream connecting to %s:%d (sn=%s)", self._host, self._port, self._sn)

                response = await stub.ProduceDetection(self._stream_generator(gen_stop))

                if self._closed:
                    return

                if response.has_errors:
                    logger.warning(
                        "ProduceDetection stream ended with server error (sn=%s): %s",
                        self._sn,
                        response.response_message,
                    )
                else:
                    logger.debug("ProduceDetection stream ended cleanly (sn=%s)", self._sn)
                    backoff = self._BACKOFF_INITIAL

            except Exception as exc:
                if self._closed:
                    return
                logger.warning(
                    "Detection stream error (sn=%s, %s: %s), reconnecting in %.1fs",
                    self._sn,
                    type(exc).__name__,
                    exc,
                    backoff,
                )
            finally:
                gen_stop.set()
                if channel:
                    await channel.close()

            if not self._closed:
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=backoff,  # type: ignore[union-attr]
                    )
                    return
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, self._BACKOFF_MAX)

    async def _stream_generator(self, gen_stop: asyncio.Event):
        assert self._queue is not None
        while not self._closed and not gen_stop.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            if item is _SENTINEL:
                try:
                    self._queue.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    pass
                return
            yield item

    # ------------------------------------------------------------------
    # Proto builder
    # ------------------------------------------------------------------

    def _base(self, sn: str | None = None):
        from google.protobuf import timestamp_pb2
        from zqnt_utils.generated.zqnt import common_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=sn if sn is not None else self._sn, timestamp=ts)

    def _build_detection_request(self, batch: DetectionBatch):
        from zqnt_utils.generated.zqnt import common_pb2

        detections = [_detection_to_proto(common_pb2, d) for d in batch.detections]

        kwargs: dict = {"base": self._base(sn=batch.sn or None), "detections": detections}
        if batch.stream_url is not None:
            kwargs["stream_url"] = batch.stream_url

        return common_pb2.DetectionBatch(**kwargs)


_POSITION_OPTIONALS = ("altitude", "range_m", "bearing_deg", "elevation_deg", "speed_mps", "heading_deg")


def _detection_to_proto(common_pb2, d):
    """One SDK DetectionResult as the wire message; box and position only when present."""
    result = common_pb2.DetectionResult(object_id=d.object_id, object_type=d.object_type, confidence=d.confidence)
    if d.bounding_box is not None:
        result.bounding_box.CopyFrom(
            common_pb2.BoundingBox(
                x=d.bounding_box.x, y=d.bounding_box.y, width=d.bounding_box.width, height=d.bounding_box.height
            )
        )
    if d.position is not None:
        position = common_pb2.DetectionPosition(latitude=d.position.latitude, longitude=d.position.longitude)
        for name in _POSITION_OPTIONALS:
            value = getattr(d.position, name)
            if value is not None:
                setattr(position, name, value)
        result.position.CopyFrom(position)
    return result

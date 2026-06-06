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
        import grpc
        import grpc.aio
        from zqnt_utils.generated.zqnt import live_data_pb2_grpc

        backoff = self._BACKOFF_INITIAL

        while not self._closed:
            gen_stop = asyncio.Event()
            channel = None
            try:
                channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
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

    def _base(self):
        from google.protobuf import timestamp_pb2
        from zqnt_utils.generated.zqnt import common_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=self._sn, timestamp=ts)

    def _build_detection_request(self, batch: DetectionBatch):
        from zqnt_utils.generated.zqnt import common_pb2

        detections = [
            common_pb2.DetectionResult(
                object_id=d.object_id,
                object_type=d.object_type,
                confidence=d.confidence,
                bounding_box=common_pb2.BoundingBox(
                    x=d.bounding_box.x,
                    y=d.bounding_box.y,
                    width=d.bounding_box.width,
                    height=d.bounding_box.height,
                ),
            )
            for d in batch.detections
        ]

        kwargs: dict = {"base": self._base(), "detections": detections}
        if batch.stream_url is not None:
            kwargs["stream_url"] = batch.stream_url

        return common_pb2.DetectionBatch(**kwargs)

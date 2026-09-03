"""
NotificationPublisher – sends asset-status, mission, and task notifications to the ZQNT
LiveDataService using the ``ProduceNotification`` client-streaming RPC.

This branch tracks the 1.3.0 wire contract: ``TaskEvent`` (retired on main/2.0.0 in favor of
the vendor-neutral ``CommandExecutionEvent``, which doesn't exist in events.proto until after
the 1.3.0 tag).

The publisher keeps a long-lived gRPC stream open and feeds it from an
internal bounded queue.  If the connection drops it reconnects automatically
with exponential backoff (1 s → 2 s → 4 s … up to 60 s).  Events produced
while the stream is down are buffered up to QUEUE_MAX_SIZE; older events are
silently dropped when the buffer is full::

    publisher = NotificationPublisher(host="platform.example.com", port=50052, sn="DOCK001")
    await publisher.connect()

    await publisher.publish_asset_status(AssetStatusEvent(sn="DOCK001", online=True))
    await publisher.publish_mission_event(MissionEvent(mission_id="m1", mission_type=MissionType.STANDARD, status=MissionStatus.ACTIVE))
    await publisher.publish_task_event(
        TaskEvent(task_id="t1", task_type=TaskType.WAYPOINT, status=TaskStatus.RUNNING)
    )

    await publisher.close()
"""

import asyncio
import logging
import uuid

from ..models.notification import AssetStatusEvent, MissionEvent, TaskEvent

logger = logging.getLogger(__name__)

_SENTINEL = object()


class NotificationPublisher:
    """
    Wraps the LiveDataService ``ProduceNotification`` streaming RPC.

    Reconnects automatically on connection loss using exponential backoff.
    Events published while disconnected are buffered; when the buffer is full
    the oldest event is dropped silently.

    Args:
        host:           LiveDataService host.
        port:           LiveDataService port (default 50052).
        sn:             Serial number of the asset producing the notifications.
        queue_max_size: Max buffered events while disconnected (default 1000).
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
        self._stream_task = asyncio.create_task(self._run_stream(), name="notification-producer")
        logger.info("NotificationPublisher started for %s:%d (sn=%s)", self._host, self._port, self._sn)

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
        logger.info("NotificationPublisher closed (sn=%s)", self._sn)

    # ------------------------------------------------------------------
    # Public publish methods
    # ------------------------------------------------------------------

    async def publish_asset_status(self, event: AssetStatusEvent) -> None:
        """Enqueue an asset-status event. Drops the event if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_asset_status_request(event)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Notification queue full, dropping asset-status event (sn=%s)", self._sn)

    async def publish_mission_event(self, event: MissionEvent) -> None:
        """Enqueue a mission event. Drops the event if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_mission_event_request(event)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Notification queue full, dropping mission event (sn=%s)", self._sn)

    async def publish_task_event(self, event: TaskEvent) -> None:
        """Enqueue a task event. Drops the event if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_task_event_request(event)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Notification queue full, dropping task event (sn=%s)", self._sn)

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
                logger.info("Notification stream connecting to %s:%d (sn=%s)", self._host, self._port, self._sn)

                response = await stub.ProduceNotification(self._stream_generator(gen_stop))

                if self._closed:
                    return

                if response.has_errors:
                    logger.warning(
                        "ProduceNotification stream ended with server error (sn=%s): %s",
                        self._sn,
                        response.response_message,
                    )
                else:
                    logger.debug("ProduceNotification stream ended cleanly (sn=%s)", self._sn)
                    backoff = self._BACKOFF_INITIAL

            except Exception as exc:
                if self._closed:
                    return
                logger.warning(
                    "Notification stream error (sn=%s, %s: %s), reconnecting in %.1fs",
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
    # Proto builders
    # ------------------------------------------------------------------

    def _base(self, sn: str | None = None):
        from google.protobuf import timestamp_pb2
        from zqnt_utils.generated.zqnt import common_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=sn if sn is not None else self._sn, timestamp=ts)

    def _build_asset_status_request(self, event: AssetStatusEvent):
        from zqnt_utils.generated.zqnt import events_pb2

        kwargs: dict = {"sn": event.sn, "online": event.online}
        if event.asset_id is not None:
            kwargs["asset_id"] = event.asset_id
        if event.message is not None:
            kwargs["message"] = event.message

        return events_pb2.ProduceNotificationRequest(
            base=self._base(sn=event.sn),
            event=events_pb2.NotificationEvent(asset_status=events_pb2.AssetStatusEvent(**kwargs)),
            severity=events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_INFO,
            event_type=events_pb2.NotificationEventType.NOTIFICATION_EVENT_ASSET_STATUS,
        )

    def _build_mission_event_request(self, event: MissionEvent):
        from zqnt_utils.generated.zqnt import events_pb2

        kwargs: dict = {
            "mission_id": event.mission_id,
            "mission_type": int(event.mission_type),
            "status": int(event.status),
        }
        if event.message is not None:
            kwargs["message"] = event.message

        return events_pb2.ProduceNotificationRequest(
            base=self._base(sn=event.sn or None),
            event=events_pb2.NotificationEvent(mission=events_pb2.MissionEvent(**kwargs)),
            severity=events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_INFO,
            event_type=events_pb2.NotificationEventType.NOTIFICATION_EVENT_MISSION,
        )

    def _build_task_event_request(self, event: TaskEvent):
        from zqnt_utils.generated.zqnt import events_pb2

        kwargs: dict = {
            "task_id": event.task_id,
            "task_type": int(event.task_type),
            "status": int(event.status),
        }
        if event.progress is not None:
            kwargs["progress"] = event.progress
        if event.message is not None:
            kwargs["message"] = event.message
        if event.external_task_type is not None:
            kwargs["external_task_type"] = event.external_task_type

        severity = (
            events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_CRITICAL
            if event.status == 4  # TaskStatus.ERROR
            else events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_INFO
        )
        return events_pb2.ProduceNotificationRequest(
            base=self._base(sn=event.sn or None),
            event=events_pb2.NotificationEvent(task=events_pb2.TaskEvent(**kwargs)),
            severity=severity,
            event_type=events_pb2.NotificationEventType.NOTIFICATION_EVENT_TASK,
        )

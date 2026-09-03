"""
LiveDataService – unified facade over telemetry, detection, and notification publishing.

Mirrors :java:`com.zqnt.sdk.edge.livedata.application.LiveDataService`'s single-interface
ergonomics: one object, one ``connect()``/``close()`` lifecycle, instead of managing
:class:`~edge_sdk.client.telemetry_publisher.TelemetryPublisher`,
:class:`~edge_sdk.client.detection_publisher.DetectionPublisher`, and
:class:`~edge_sdk.client.notification_publisher.NotificationPublisher` as three separate
long-lived gRPC streams by hand. Each stream still reconnects independently (a detection-stream
hiccup doesn't interrupt telemetry) — this only unifies lifecycle and gives POJO-style
``produce_*`` methods one place to live::

    live_data = LiveDataService(host="platform.example.com", port=50052, sn="DOCK001")
    await live_data.connect()

    await live_data.produce_telemetry(AssetTelemetry(id="DOCK001", latitude=47.5, longitude=9.7))
    await live_data.produce_detection(DetectionBatch(detections=[...]))
    await live_data.produce_notification(AssetStatusEvent(sn="DOCK001", online=True))

    await live_data.close()
"""

import logging

from ..models.notification import AssetStatusEvent, MissionEvent, TaskEvent
from ..models.telemetry import AssetTelemetry, SubAssetTelemetry
from .detection_publisher import DetectionPublisher
from .notification_publisher import NotificationPublisher
from .telemetry_publisher import TelemetryPublisher

logger = logging.getLogger(__name__)


class LiveDataService:
    """
    Composes :class:`TelemetryPublisher`, :class:`DetectionPublisher`, and
    :class:`NotificationPublisher` behind one connect/close lifecycle.

    Args:
        host:           LiveDataService host.
        port:           LiveDataService port (default 50052).
        sn:             Serial number of the asset producing the data.
        queue_max_size: Max buffered frames/batches/events per stream while disconnected.
    """

    def __init__(
        self,
        host: str,
        port: int = 50052,
        sn: str = "",
        queue_max_size: int = 1000,
    ) -> None:
        self._sn = sn
        self.telemetry = TelemetryPublisher(host=host, port=port, sn=sn, queue_max_size=queue_max_size)
        self.detection = DetectionPublisher(host=host, port=port, sn=sn, queue_max_size=queue_max_size)
        self.notification = NotificationPublisher(host=host, port=port, sn=sn, queue_max_size=queue_max_size)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open all three streams."""
        await self.telemetry.connect()
        await self.detection.connect()
        await self.notification.connect()
        logger.info("LiveDataService connected (sn=%s)", self._sn)

    async def close(self) -> None:
        """Close all three streams. Safe to call even if some streams failed to open."""
        await self.telemetry.close()
        await self.detection.close()
        await self.notification.close()
        logger.info("LiveDataService closed (sn=%s)", self._sn)

    async def __aenter__(self) -> "LiveDataService":
        await self.connect()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    async def produce_telemetry(self, telemetry: AssetTelemetry | SubAssetTelemetry) -> None:
        if isinstance(telemetry, SubAssetTelemetry):
            await self.telemetry.publish_subasset_telemetry(telemetry)
        else:
            await self.telemetry.publish_asset_telemetry(telemetry)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def produce_detection(self, batch) -> None:
        await self.detection.publish_detection_batch(batch)

    # ------------------------------------------------------------------
    # Notification
    # ------------------------------------------------------------------

    async def produce_notification(self, event: AssetStatusEvent | MissionEvent | TaskEvent) -> None:
        if isinstance(event, AssetStatusEvent):
            await self.notification.publish_asset_status(event)
        elif isinstance(event, MissionEvent):
            await self.notification.publish_mission_event(event)
        elif isinstance(event, TaskEvent):
            await self.notification.publish_task_event(event)
        else:
            raise TypeError(f"Unknown notification event type: {type(event).__name__}")

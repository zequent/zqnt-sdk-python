"""
TelemetryIngestPublisher -- v3 live data (``zqnt.telemetry.v3.TelemetryIngestService`` on live-data).

Three long-lived client streams (telemetry, detections, alerts), each opened on first publish,
buffered while down and reconnected with backoff (1 s doubling to 60 s)::

    ingest = TelemetryIngestPublisher(host="live-data", port=8003)
    await ingest.publish_sample(TelemetrySample(sn="DRONE-1", latitude=47.5, longitude=9.7,
                                                battery_percent=81, details={"drone.gear": 1}))
    await ingest.publish_alert(Alert(sn="DOCK-1", code="dock.rain", severity=AlertSeverity.WARNING))
    await ingest.close()

An older core answers UNIMPLEMENTED; the stream then uses v2 ``ProduceTelemetry``/
``ProduceDetection`` for :attr:`V3Fallback.WINDOW_SECONDS` before trying v3 again. In v2 a sample is
mapped by ``zqnt_utils.telemetry``: keys of the platform's catalog in ``details`` land in their v2
fields, other keys are dropped; a moving sample or one with aircraft keys is sub-asset (aircraft)
telemetry, otherwise asset telemetry. Alerts have no v2 counterpart and are dropped while v2 is in
use.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from collections.abc import Callable
from datetime import datetime

from google.protobuf import struct_pb2, timestamp_pb2

from ..auth import default_edge_token, platform_channel
from ..models.common import DetectionBatch
from ..models.live import Alert, TelemetrySample
from .edge_gateway import V3Fallback, is_unimplemented

logger = logging.getLogger(__name__)

_SENTINEL = object()


def _timestamp(value: datetime | None) -> timestamp_pb2.Timestamp:
    ts = timestamp_pb2.Timestamp()
    if value is not None:
        ts.FromDatetime(value)
    else:
        ts.GetCurrentTime()
    return ts


def _given(value: float | None) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def _asset_ref(sn: str, asset_id: str | None):
    from zqnt_utils.generated.zqnt.common.v3 import common_pb2

    return common_pb2.AssetRef(sn=sn, id=asset_id or "")


def _struct(values: dict) -> struct_pb2.Struct:
    s = struct_pb2.Struct()
    s.update(values)
    return s


def sample_to_v3(sample: TelemetrySample):
    from zqnt_utils.generated.zqnt.common.v3 import common_pb2
    from zqnt_utils.generated.zqnt.telemetry.v3 import telemetry_pb2

    proto = telemetry_pb2.TelemetrySample(
        asset=_asset_ref(sample.sn, sample.asset_id), observed_at=_timestamp(sample.observed_at)
    )
    if _given(sample.latitude) and _given(sample.longitude):
        point = common_pb2.GeoPoint(latitude=sample.latitude, longitude=sample.longitude)
        if _given(sample.altitude):
            point.altitude = sample.altitude
        proto.position.CopyFrom(point)
    for name in ("relative_altitude", "heading_degrees", "horizontal_speed", "vertical_speed", "battery_percent"):
        value = getattr(sample, name)
        if _given(value):
            setattr(proto, name, value)
    if sample.details:
        proto.details.CopyFrom(_struct(sample.details))
    return telemetry_pb2.PublishTelemetryRequest(sample=proto)


def sample_to_v2(sample: TelemetrySample):
    from zqnt_utils.telemetry import to_request

    return to_request(sample_to_v3(sample).sample)


def detection_to_v3(d):
    from zqnt_utils.generated.zqnt.common.v3 import common_pb2
    from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

    detection = edge_v3.Detection(
        object_id=d.object_id or "", object_type=d.object_type or "", confidence=d.confidence or 0.0
    )
    if d.bounding_box is not None:
        detection.bounding_box.CopyFrom(
            edge_v3.BoundingBox(
                x=d.bounding_box.x, y=d.bounding_box.y, width=d.bounding_box.width, height=d.bounding_box.height
            )
        )
    if d.position is not None and _given(d.position.latitude) and _given(d.position.longitude):
        point = common_pb2.GeoPoint(latitude=d.position.latitude, longitude=d.position.longitude)
        if _given(d.position.altitude):
            point.altitude = d.position.altitude
        detection.position.CopyFrom(point)
    return detection


def detections_to_v3(batch: DetectionBatch):
    from zqnt_utils.generated.zqnt.telemetry.v3 import telemetry_pb2

    return telemetry_pb2.PublishDetectionsRequest(
        batch=telemetry_pb2.DetectionBatch(
            asset=_asset_ref(batch.sn, None),
            observed_at=_timestamp(batch.observed_at),
            stream_url=batch.stream_url or "",
            detections=[detection_to_v3(d) for d in batch.detections],
        )
    )


def detections_to_v2(batch: DetectionBatch):
    from .detection_publisher import DetectionPublisher

    return DetectionPublisher(host="", sn=batch.sn, token="")._build_detection_request(batch)


def alert_to_v3(alert: Alert):
    from zqnt_utils.generated.zqnt.telemetry.v3 import telemetry_pb2

    proto = telemetry_pb2.Alert(
        asset=_asset_ref(alert.sn, alert.asset_id),
        occurred_at=_timestamp(alert.occurred_at),
        severity=int(alert.severity),
        code=alert.code,
        message=alert.message,
    )
    if alert.details:
        proto.details.CopyFrom(_struct(alert.details))
    return telemetry_pb2.PublishAlertsRequest(alert=proto)


class _IngestStream:
    """One client stream with a bounded buffer, reconnect, and the v3→v2 fallback."""

    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 60.0
    # Items a v3 stream sent before the server answered UNIMPLEMENTED are sent again over v2.
    _REPLAY_LIMIT = 256

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        token: str | None,
        queue_max_size: int,
        v3_call: Callable,
        to_v3: Callable,
        v2_call: Callable | None,
        to_v2: Callable | None,
    ) -> None:
        self._name = name
        self._host = host
        self._port = port
        self._token = token
        self._v3_call = v3_call
        self._to_v3 = to_v3
        self._v2_call = v2_call
        self._to_v2 = to_v2
        self._fallback = V3Fallback(f"{host}:{port}/TelemetryIngestService.{name}")
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_max_size)
        self._replay: deque = deque()
        self._closed = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.accepted = 0
        self.rejected = 0

    def put(self, item) -> None:
        if self._closed:
            raise RuntimeError(f"{self._name} stream is closed")
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"ingest-{self._name}")
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.debug("%s buffer full, dropping one item", self._name)

    async def close(self) -> None:
        self._closed = True
        self._stop.set()
        try:
            self._queue.put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            pass
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

    async def _run(self) -> None:
        backoff = self.BACKOFF_INITIAL
        while not self._closed:
            v3 = self._fallback.available()
            gen_stop = asyncio.Event()
            sent: list = []
            channel = platform_channel(self._host, self._port, self._token)
            try:
                if v3:
                    response = await self._v3_call(channel)(self._items(gen_stop, self._to_v3, sent, v2=False))
                    self.accepted += response.accepted
                    self.rejected += response.rejected
                    if response.rejected:
                        logger.warning("%s: platform rejected %d item(s)", self._name, response.rejected)
                elif self._v2_call is None:
                    await self._drop_while_v2(gen_stop)
                else:
                    response = await self._v2_call(channel)(self._items(gen_stop, self._to_v2, sent, v2=True))
                    if response.has_errors:
                        logger.warning("%s v2 stream ended with error: %s", self._name, response.response_message)
                backoff = self.BACKOFF_INITIAL
                continue
            except Exception as exc:
                if self._closed:
                    return
                if v3 and is_unimplemented(exc):
                    self._fallback.mark_unavailable()
                    self._replay.extendleft(reversed(sent))
                    continue
                logger.warning(
                    "%s stream error (%s: %s), reconnecting in %.1fs", self._name, type(exc).__name__, exc, backoff
                )
            finally:
                gen_stop.set()
                await channel.close()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                return
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, self.BACKOFF_MAX)

    async def _next(self, gen_stop: asyncio.Event):
        if self._replay:
            return self._replay.popleft()
        while not self._closed and not gen_stop.is_set():
            try:
                return await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                return None
        return _SENTINEL

    async def _items(self, gen_stop: asyncio.Event, convert: Callable, sent: list, *, v2: bool):
        while not gen_stop.is_set():
            if v2 and self._fallback.available():
                return
            item = await self._next(gen_stop)
            if item is _SENTINEL:
                return
            if item is None:
                continue
            if gen_stop.is_set():
                self._replay.appendleft(item)
                return
            if not v2 and len(sent) < self._REPLAY_LIMIT:
                sent.append(item)
            yield convert(item)

    async def _drop_while_v2(self, gen_stop: asyncio.Event) -> None:
        dropped = 0
        while not self._closed and not self._fallback.available():
            item = await self._next(gen_stop)
            if item is _SENTINEL:
                return
            if item is not None:
                dropped += 1
        if dropped:
            logger.warning("%s: %d item(s) dropped, the platform has no v2 counterpart", self._name, dropped)


class TelemetryIngestPublisher:
    """Publishes v3 telemetry samples, detection batches and alerts to live-data."""

    def __init__(
        self,
        host: str,
        port: int = 50052,
        token: str | None = None,
        queue_max_size: int = 1000,
    ) -> None:
        token = token if token is not None else default_edge_token()

        def ingest(method: str):
            def call(channel):
                from zqnt_utils.generated.zqnt.telemetry.v3 import telemetry_pb2_grpc

                return getattr(telemetry_pb2_grpc.TelemetryIngestServiceStub(channel), method)

            return call

        def live_data(method: str):
            def call(channel):
                from zqnt_utils.generated.zqnt import live_data_pb2_grpc

                return getattr(live_data_pb2_grpc.LiveDataServiceStub(channel), method)

            return call

        args = (host, port, token, queue_max_size)
        self.telemetry = _IngestStream(
            "PublishTelemetry",
            *args,
            ingest("PublishTelemetry"),
            sample_to_v3,
            live_data("ProduceTelemetry"),
            sample_to_v2,
        )
        self.detections = _IngestStream(
            "PublishDetections",
            *args,
            ingest("PublishDetections"),
            detections_to_v3,
            live_data("ProduceDetection"),
            detections_to_v2,
        )
        self.alerts = _IngestStream("PublishAlerts", *args, ingest("PublishAlerts"), alert_to_v3, None, None)

    async def publish_sample(self, sample: TelemetrySample) -> None:
        self.telemetry.put(sample)

    async def publish_detections(self, batch: DetectionBatch) -> None:
        self.detections.put(batch)

    async def publish_alert(self, alert: Alert) -> None:
        self.alerts.put(alert)

    async def close(self) -> None:
        await self.telemetry.close()
        await self.detections.close()
        await self.alerts.close()

    async def __aenter__(self) -> "TelemetryIngestPublisher":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

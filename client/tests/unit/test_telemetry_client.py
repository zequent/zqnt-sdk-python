"""``TelemetryClient`` against an in-process fake ``zqnt.telemetry.v3.TelemetryService``."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import grpc
import grpc.aio
import pytest
from google.protobuf import timestamp_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.telemetry.v3 import telemetry_pb2, telemetry_pb2_grpc

from client_sdk import CommandError, TelemetryClient, ZequentClient
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


class FakeTelemetryV3(telemetry_pb2_grpc.TelemetryServiceServicer):
    def __init__(self) -> None:
        self.request: telemetry_pb2.WatchTelemetryRequest | None = None
        self.refuse_with: tuple[grpc.StatusCode, str] | None = None
        self.responses: list = []
        self.cancelled = asyncio.Event()

    async def WatchTelemetry(self, request, context):  # noqa: N802
        async for response in self._serve(request, context):
            yield response

    async def WatchDetections(self, request, context):  # noqa: N802
        async for response in self._serve(request, context):
            yield response

    async def WatchAlerts(self, request, context):  # noqa: N802
        async for response in self._serve(request, context):
            yield response

    async def _serve(self, request, context):
        self.request = request
        if self.refuse_with is not None:
            await context.abort(*self.refuse_with)
        context.add_done_callback(lambda _ctx: self.cancelled.set())
        for response in self.responses:
            yield response
        await asyncio.Event().wait()


@pytest.fixture
async def fake():
    servicer = FakeTelemetryV3()
    server = grpc.aio.server()
    telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    servicer.port = port
    yield servicer
    await server.stop(None)


@pytest.fixture
async def client(fake):
    config = ServiceConfig("live-data", host="127.0.0.1", port=fake.port)
    async with ZequentClient(
        connector_config=config,
        remote_control_config=config,
        mission_autonomy_config=config,
        live_data_config=config,
        resilience=ResilienceConfig(max_retry_attempts=0, request_timeout_seconds=5),
        client_token="test-token",
    ) as zequent:
        yield zequent.telemetry


async def test_yields_source_status_and_samples_and_skips_heartbeats(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.responses = [
        telemetry_pb2.WatchTelemetryResponse(
            source_status=telemetry_pb2.SourceStatus(
                asset=common_pb2.AssetRef(sn="DRONE-1"), state=telemetry_pb2.SOURCE_STATE_ONLINE
            )
        ),
        telemetry_pb2.WatchTelemetryResponse(heartbeat=timestamp_pb2.Timestamp(seconds=1)),
        telemetry_pb2.WatchTelemetryResponse(
            sample=telemetry_pb2.TelemetrySample(asset=common_pb2.AssetRef(sn="DRONE-1"), battery_percent=87)
        ),
    ]

    items = []
    async with asyncio.timeout(5):
        async for item in client.watch_telemetry(["DOCK-1", "DRONE-1"], min_interval=timedelta(milliseconds=500)):
            items.append(item)
            if len(items) == 2:
                break

    assert [a.sn for a in fake.request.assets] == ["DOCK-1", "DRONE-1"]
    assert fake.request.min_interval.nanos == 500_000_000
    assert fake.request.context.request_id
    status, sample = items
    assert isinstance(status, telemetry_pb2.SourceStatus)
    assert status.state == telemetry_pb2.SOURCE_STATE_ONLINE
    assert isinstance(sample, telemetry_pb2.TelemetrySample)
    assert sample.battery_percent == 87
    await asyncio.wait_for(fake.cancelled.wait(), timeout=5)


async def test_no_asset_watches_the_whole_organization(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.responses = [
        telemetry_pb2.WatchTelemetryResponse(sample=telemetry_pb2.TelemetrySample(asset=common_pb2.AssetRef(sn="X")))
    ]

    async with asyncio.timeout(5):
        async for _ in client.watch_telemetry():
            break

    assert len(fake.request.assets) == 0
    assert not fake.request.HasField("min_interval")


async def test_a_refused_watch_raises_its_category(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.refuse_with = (grpc.StatusCode.PERMISSION_DENIED, "live data is not licensed")

    with pytest.raises(CommandError) as raised:
        async for _ in client.watch_telemetry(["DRONE-1"]):
            pass

    assert raised.value.category == common_pb2.ERROR_CATEGORY_PERMISSION_DENIED


async def test_a_silent_stream_raises_after_the_heartbeat_timeout(client: TelemetryClient, fake: FakeTelemetryV3):
    with pytest.raises(CommandError) as raised:
        async with asyncio.timeout(5):
            async for _ in client.watch_telemetry(["DRONE-1"], heartbeat_timeout=0.3):
                pass

    assert raised.value.category == common_pb2.ERROR_CATEGORY_SERVICE
    assert raised.value.retryable
    await asyncio.wait_for(fake.cancelled.wait(), timeout=5)


async def test_a_blank_serial_is_refused(client: TelemetryClient):
    with pytest.raises(ValueError):
        async for _ in client.watch_telemetry(["DRONE-1", " "]):
            pass


async def test_watches_detection_batches_and_skips_heartbeats(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.responses = [
        telemetry_pb2.WatchDetectionsResponse(heartbeat=timestamp_pb2.Timestamp(seconds=1)),
        telemetry_pb2.WatchDetectionsResponse(
            batch=telemetry_pb2.DetectionBatch(asset=common_pb2.AssetRef(sn="DRONE-1"), stream_url="rtsp://s")
        ),
    ]

    async with asyncio.timeout(5):
        async for batch in client.watch_detections(["DRONE-1"]):
            break

    assert [a.sn for a in fake.request.assets] == ["DRONE-1"]
    assert isinstance(batch, telemetry_pb2.DetectionBatch)
    assert batch.stream_url == "rtsp://s"
    await asyncio.wait_for(fake.cancelled.wait(), timeout=5)


async def test_watches_alerts_from_a_minimum_severity(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.responses = [
        telemetry_pb2.WatchAlertsResponse(heartbeat=timestamp_pb2.Timestamp(seconds=1)),
        telemetry_pb2.WatchAlertsResponse(
            alert=telemetry_pb2.Alert(
                asset=common_pb2.AssetRef(sn="DOCK-1"), severity=telemetry_pb2.ALERT_SEVERITY_CRITICAL, code="dock.rain"
            )
        ),
    ]

    async with asyncio.timeout(5):
        async for alert in client.watch_alerts(min_severity=telemetry_pb2.ALERT_SEVERITY_WARNING):
            break

    assert len(fake.request.assets) == 0
    assert fake.request.min_severity == telemetry_pb2.ALERT_SEVERITY_WARNING
    assert fake.request.context.request_id
    assert alert.code == "dock.rain"


async def test_a_refused_alert_watch_raises_its_category(client: TelemetryClient, fake: FakeTelemetryV3):
    fake.refuse_with = (grpc.StatusCode.PERMISSION_DENIED, "live data is not licensed")

    with pytest.raises(CommandError) as raised:
        async for _ in client.watch_alerts(["DOCK-1"]):
            pass

    assert raised.value.category == common_pb2.ERROR_CATEGORY_PERMISSION_DENIED


async def test_a_silent_detection_watch_raises_after_the_heartbeat_timeout(client: TelemetryClient):
    with pytest.raises(CommandError) as raised:
        async with asyncio.timeout(5):
            async for _ in client.watch_detections(heartbeat_timeout=0.3):
                pass

    assert raised.value.retryable

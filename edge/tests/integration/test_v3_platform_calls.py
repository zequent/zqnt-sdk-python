"""
The adapter's v3 calls into the platform, against a real grpc.aio server: command events and
capability reports (EdgeGatewayService), live data (TelemetryIngestService), and the v2 path an
older core -- one that answers UNIMPLEMENTED -- gets instead.
"""

import asyncio
import socket

import grpc
import grpc.aio
import pytest_asyncio
from zqnt_utils.generated.zqnt import (
    asset_pb2,
    device_control_contracts_pb2,
    live_data_pb2_grpc,
    live_data_types_pb2,
    remote_control_pb2_grpc,
)
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc
from zqnt_utils.generated.zqnt.telemetry.v3 import telemetry_pb2, telemetry_pb2_grpc

from edge_sdk import (
    Alert,
    AlertSeverity,
    AssetType,
    EdgeAdapter,
    EdgeGatewayClient,
    TelemetryIngestPublisher,
    TelemetrySample,
    TelemetryValueType,
)
from edge_sdk.client.edge_gateway import V3Fallback
from edge_sdk.client.notification_publisher import NotificationPublisher
from edge_sdk.models.common import (
    CommandExecutionStatus,
    CustomCommandResponse,
    DetectionBatch,
    DetectionPosition,
    DetectionResult,
)
from edge_sdk.models.notification import CommandExecutionEvent
from edge_sdk.server.capability_reporter import CapabilityReporter


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


async def _until(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.02)


class _Platform:
    """Records everything an adapter sends; v3 services only when asked to serve them."""

    def __init__(self) -> None:
        self.command_events: list = []
        self.capability_sets: list = []
        self.asset_runtimes: list = []
        self.samples: list = []
        self.detection_batches: list = []
        self.alerts: list = []
        self.v2_telemetry: list = []
        self.v2_detections: list = []
        self.v2_notifications: list = []


class _Gateway(edge_v3_grpc.EdgeGatewayServiceServicer):
    def __init__(self, platform: _Platform) -> None:
        self._p = platform

    async def PublishCommandEvent(self, request, context):
        self._p.command_events.append(request.event)
        return edge_v3.PublishCommandEventResponse()

    async def ReportCapabilities(self, request, context):
        self._p.capability_sets.append(request.capabilities)
        return edge_v3.ReportCapabilitiesResponse(accepted_revision=f"r{len(self._p.capability_sets)}")


class _Ingest(telemetry_pb2_grpc.TelemetryIngestServiceServicer):
    def __init__(self, platform: _Platform) -> None:
        self._p = platform

    async def PublishTelemetry(self, request_iterator, context):
        async for request in request_iterator:
            self._p.samples.append(request.sample)
        return telemetry_pb2.PublishTelemetryResponse(accepted=len(self._p.samples))

    async def PublishDetections(self, request_iterator, context):
        async for request in request_iterator:
            self._p.detection_batches.append(request.batch)
        return telemetry_pb2.PublishDetectionsResponse()

    async def PublishAlerts(self, request_iterator, context):
        async for request in request_iterator:
            self._p.alerts.append(request.alert)
        return telemetry_pb2.PublishAlertsResponse()


class _LiveDataV2(live_data_pb2_grpc.LiveDataServiceServicer):
    def __init__(self, platform: _Platform) -> None:
        self._p = platform

    async def ProduceTelemetry(self, request_iterator, context):
        async for request in request_iterator:
            self._p.v2_telemetry.append(request)
        return live_data_types_pb2.LiveDataResponse()

    async def ProduceDetection(self, request_iterator, context):
        async for request in request_iterator:
            self._p.v2_detections.append(request)
        return live_data_types_pb2.LiveDataResponse()

    async def ProduceNotification(self, request_iterator, context):
        async for request in request_iterator:
            self._p.v2_notifications.append(request)
        return live_data_types_pb2.LiveDataResponse()


class _RemoteControlV2(remote_control_pb2_grpc.RemoteControlServiceServicer):
    def __init__(self, platform: _Platform) -> None:
        self._p = platform

    async def ReportAssetRuntime(self, request, context):
        self._p.asset_runtimes.append(request)
        return device_control_contracts_pb2.ReportAssetRuntimeResponse(accepted_revision="v2-r1")


async def _serve(v3: bool):
    platform = _Platform()
    server = grpc.aio.server()
    if v3:
        edge_v3_grpc.add_EdgeGatewayServiceServicer_to_server(_Gateway(platform), server)
        telemetry_pb2_grpc.add_TelemetryIngestServiceServicer_to_server(_Ingest(platform), server)
    live_data_pb2_grpc.add_LiveDataServiceServicer_to_server(_LiveDataV2(platform), server)
    remote_control_pb2_grpc.add_RemoteControlServiceServicer_to_server(_RemoteControlV2(platform), server)
    port = _free_port()
    server.add_insecure_port(f"localhost:{port}")
    await server.start()
    return server, port, platform


@pytest_asyncio.fixture
async def v3_core():
    server, port, platform = await _serve(v3=True)
    yield port, platform
    await server.stop(0)


@pytest_asyncio.fixture
async def older_core():
    server, port, platform = await _serve(v3=False)
    yield port, platform
    await server.stop(0)


class _Adapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    def reported_asset_sns(self):
        return ["DOCK-1"]


async def _ok(ctx, params):
    return CustomCommandResponse.ok(ctx.tid, ctx.sn, "ok")


# ---------------------------------------------------------------------------
# Command events
# ---------------------------------------------------------------------------


async def test_a_command_event_goes_to_the_gateway_with_occurred_at(v3_core):
    port, platform = v3_core
    gateway = EdgeGatewayClient("localhost", port, token="t")
    notifier = NotificationPublisher("localhost", port, sn="DOCK-1", token="t", gateway=gateway)
    await notifier.connect()
    try:
        await notifier.publish_command_execution_event(
            CommandExecutionEvent(
                external_execution_id="vendor-1",
                command_execution_id="capexec:e1:n1",
                status=CommandExecutionStatus.SUCCEEDED,
                sn="DOCK-1",
                output={"photos": 2},
            )
        )
    finally:
        await notifier.close()
        await gateway.close()

    [event] = platform.command_events
    assert event.command_execution_id == "capexec:e1:n1"
    assert event.HasField("occurred_at")
    assert event.result["photos"] == 2
    assert platform.v2_notifications == []


async def test_an_older_core_gets_the_event_over_v2_and_v3_is_not_retried(older_core):
    port, platform = older_core
    gateway = EdgeGatewayClient("localhost", port, token="t")
    notifier = NotificationPublisher("localhost", port, sn="DOCK-1", token="t", gateway=gateway)
    await notifier.connect()
    try:
        for i in range(2):
            await notifier.publish_command_execution_event(
                CommandExecutionEvent(
                    external_execution_id=f"vendor-{i}", status=CommandExecutionStatus.SUCCEEDED, sn="DOCK-1"
                )
            )
        await _until(lambda: len(platform.v2_notifications) == 2)
        assert not gateway._events_v3.available()
    finally:
        await notifier.close()
        await gateway.close()

    events = [n.event.command_execution for n in platform.v2_notifications]
    assert [e.external_execution_id for e in events] == ["vendor-0", "vendor-1"]
    assert all(e.HasField("occurred_at") for e in events)


async def test_events_use_v2_when_no_gateway_is_configured(older_core, monkeypatch):
    port, platform = older_core
    monkeypatch.delenv("REMOTE_CONTROL_HOST", raising=False)
    notifier = NotificationPublisher("localhost", port, sn="DOCK-1", token="t")
    await notifier.connect()
    try:
        await notifier.publish_command_execution_event(
            CommandExecutionEvent(external_execution_id="v", status=CommandExecutionStatus.RUNNING, sn="DOCK-1")
        )
        await _until(lambda: len(platform.v2_notifications) == 1)
    finally:
        await notifier.close()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


async def test_capabilities_and_telemetry_fields_are_reported_over_v3(v3_core):
    port, platform = v3_core
    adapter = _Adapter()
    adapter.register_command("dock.open_cover", _ok)
    adapter.declare_telemetry_field("dock.cover_state", TelemetryValueType.STRING, allowed_values=["OPEN", "CLOSED"])
    gateway = EdgeGatewayClient("localhost", port, token="t")

    revision = await gateway.report_capabilities(await adapter.get_capabilities("DOCK-1", None))
    await gateway.close()

    assert revision == "r1"
    [reported] = platform.capability_sets
    assert reported.asset_sn == "DOCK-1"
    assert [f.key for f in reported.telemetry_fields] == ["dock.cover_state"]
    assert list(reported.telemetry_fields[0].allowed_values) == ["OPEN", "CLOSED"]
    assert "dock.open_cover" in {c.command_id for c in reported.capabilities}


async def test_an_older_core_gets_capabilities_as_asset_runtime(older_core):
    port, platform = older_core
    adapter = _Adapter()
    adapter.register_command("dock.open_cover", _ok)
    gateway = EdgeGatewayClient("localhost", port, token="t")

    revision = await gateway.report_capabilities(await adapter.get_capabilities("DOCK-1", None))
    await gateway.close()

    assert revision == "v2-r1"
    [runtime] = platform.asset_runtimes
    assert runtime.asset_sn == "DOCK-1"
    assert runtime.HasField("observed_at")
    assert "dock.open_cover" in {c.command_id for c in runtime.capabilities}


async def test_capabilities_are_reported_on_start_and_again_when_the_registry_changes(v3_core):
    port, platform = v3_core
    adapter = _Adapter()
    gateway = EdgeGatewayClient("localhost", port, token="t")
    reporter = CapabilityReporter(adapter, gateway)
    reporter.DEBOUNCE_SECONDS = 0.01
    try:
        await reporter.start()
        await _until(lambda: len(platform.capability_sets) == 1)

        adapter.register_command("vendor.acme.spray", _ok)
        await _until(lambda: len(platform.capability_sets) == 2)
    finally:
        await reporter.stop()
        await gateway.close()

    spray = {c.command_id: c for c in platform.capability_sets[1].capabilities}["vendor.acme.spray"]
    assert spray.state == 1


# ---------------------------------------------------------------------------
# Live data
# ---------------------------------------------------------------------------


async def test_samples_detections_and_alerts_go_out_over_v3(v3_core):
    port, platform = v3_core
    ingest = TelemetryIngestPublisher("localhost", port, token="t")
    try:
        await ingest.publish_sample(
            TelemetrySample(
                sn="DRONE-1",
                latitude=47.5,
                longitude=9.7,
                altitude=float("nan"),
                battery_percent=81.0,
                details={"drone.gear": 1},
            )
        )
        await ingest.publish_detections(
            DetectionBatch(
                sn="RADAR-1",
                detections=[
                    DetectionResult("t1", "drone", 0.9, position=DetectionPosition(latitude=1.0, longitude=2.0))
                ],
            )
        )
        await ingest.publish_alert(Alert(sn="DOCK-1", code="dock.rain", severity=AlertSeverity.WARNING))
        await _until(lambda: platform.samples and platform.detection_batches and platform.alerts)
    finally:
        await ingest.close()

    [sample] = platform.samples
    assert sample.asset.sn == "DRONE-1"
    assert sample.HasField("observed_at")
    assert sample.position.latitude == 47.5
    assert not sample.position.HasField("altitude")
    assert sample.battery_percent == 81.0
    assert not sample.HasField("heading_degrees")
    assert sample.details["drone.gear"] == 1
    [batch] = platform.detection_batches
    assert batch.asset.sn == "RADAR-1" and batch.HasField("observed_at")
    assert batch.detections[0].position.longitude == 2.0
    [alert] = platform.alerts
    assert (alert.code, alert.severity) == ("dock.rain", telemetry_pb2.ALERT_SEVERITY_WARNING)


async def test_an_older_core_gets_samples_and_detections_over_v2(older_core):
    port, platform = older_core
    ingest = TelemetryIngestPublisher("localhost", port, token="t")
    try:
        await ingest.publish_sample(
            TelemetrySample(
                sn="DRONE-1",
                latitude=47.5,
                longitude=9.7,
                horizontal_speed=4.0,
                battery_percent=81.0,
                details={"drone.gear": 1, "x": 1},
            )
        )
        await ingest.publish_sample(
            TelemetrySample(
                sn="DOCK-1", latitude=1.0, longitude=2.0, battery_percent=64.0, details={"dock.mode": "IDLE"}
            )
        )
        await ingest.publish_detections(DetectionBatch(sn="RADAR-1", detections=[DetectionResult("t", "drone", 0.5)]))
        await ingest.publish_alert(Alert(sn="DOCK-1", code="dock.rain"))
        await _until(lambda: len(platform.v2_telemetry) == 2 and len(platform.v2_detections) == 1)
    finally:
        await ingest.close()

    aircraft, dock = platform.v2_telemetry
    assert aircraft.data.HasField("sub_asset")
    assert aircraft.data.sub_asset.battery_information.percentage == "81"
    assert aircraft.data.sub_asset.gear == 1
    assert aircraft.data.latitude == 47.5
    assert dock.data.HasField("asset")
    assert dock.data.asset.sub_asset_percentage == 64
    assert dock.data.asset.mode == asset_pb2.ASSET_MODE_IDLE
    assert platform.v2_detections[0].base.sn == "RADAR-1"
    assert platform.alerts == []


async def test_v3_is_tried_again_after_the_window(older_core, monkeypatch):
    port, platform = older_core
    monkeypatch.setattr(V3Fallback, "WINDOW_SECONDS", 0.3)
    v3_refusals = []
    mark = V3Fallback.mark_unavailable
    monkeypatch.setattr(V3Fallback, "mark_unavailable", lambda self: (v3_refusals.append(1), mark(self)))
    ingest = TelemetryIngestPublisher("localhost", port, token="t")
    try:
        await ingest.publish_sample(TelemetrySample(sn="DOCK-1", latitude=1.0, longitude=2.0))
        await _until(lambda: len(platform.v2_telemetry) == 1)
        await asyncio.sleep(1.5)
        await ingest.publish_sample(TelemetrySample(sn="DOCK-1", latitude=1.0, longitude=2.0))
        await _until(lambda: len(platform.v2_telemetry) == 2)
    finally:
        await ingest.close()

    assert len(v3_refusals) >= 2

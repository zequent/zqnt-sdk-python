"""Unit tests for ``LiveDataClient`` (unary + streaming)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.protobuf import empty_pb2
from google.protobuf import timestamp_pb2

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.generated import common_pb2, live_data_pb2
from client_sdk.live_data.client import LiveDataClient
from client_sdk.models.live_data import (
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    NotificationEventType,
    StreamNotificationRequest,
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
        await client.stop_live_stream(LiveDataStopLiveStreamRequest(sn="", video_id="x"))
    with pytest.raises(ValueError):
        await client.stop_live_stream(LiveDataStopLiveStreamRequest(sn="DOCK-1", video_id=""))


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


def _extended_telemetry_frame() -> live_data_pb2.LiveDataTelemetryResponse:
    return live_data_pb2.LiveDataTelemetryResponse(
        tid="tid-stream",
        sn="DOCK-1",
        hasErrors=False,
        assetId="AST-9",
        assetTelemetry=live_data_pb2.AssetTelemetry(
            id="AST-9",
            latitude=12.34,
            longitude=56.78,
            absoluteAltitude=123.4,
            relativeAltitude=23.4,
            environmentTemp=18.5,
            insideTemp=21.0,
            humidity=65.0,
            mode=common_pb2.AssetMode.ASSET_MODE_WORKING,
            rainfall=common_pb2.RainfallEnum.RAINFALL_LIGHT,
            subAssetInformation=live_data_pb2.AssetTelemetry.AssetSubAssetInformation(
                sn="SUB-1",
                model="M-1",
                paired=True,
                online=False,
            ),
            subAssetAtHome=True,
            subAssetCharging=False,
            subAssetPercentage=77.5,
            heading=182.5,
            debugModeOpen=True,
            hasActiveManualControlSession=True,
            coverState=common_pb2.AssetCoverStateEnum.COVER_STATE_OPENED,
            workingVoltage=24,
            workingCurrent=3,
            supplyVoltage=12,
            windSpeed=6.2,
            positionValid=True,
            networkInformation=live_data_pb2.AssetTelemetry.AssetNetworkInformation(
                type=common_pb2.NetworkTypeEnum.NETWORK_TYPE_4_G,
                rate=42.5,
                quality=common_pb2.NetworkStateQualityEnum.NETWORK_STATE_QUALITY_GOOD,
            ),
            airConditioner=live_data_pb2.AssetTelemetry.AssetAirConditioner(
                state=common_pb2.AssetAirConditionerStateEnum.AIR_CONDITIONER_COOL,
                switchTime=15,
            ),
            manualControlState=common_pb2.ManualControlStateEnum.MANUAL_CONTROL_STATE_CONNECTED,
            positionState=live_data_pb2.AssetTelemetry.PositionState(
                gpsNumber=9,
                rtkNumber=5,
                quality=3,
            ),
        ),
    )


class _FakeProto:
    def __init__(self, _which_oneofs: dict[str, str] | None = None, **fields: Any) -> None:
        self._fields = set(fields)
        self._which_oneofs = _which_oneofs or {}
        for key, value in fields.items():
            setattr(self, key, value)

    def HasField(self, name: str) -> bool:  # noqa: N802 - protobuf API
        return name in self._fields and getattr(self, name) is not None

    def WhichOneof(self, name: str) -> str | None:  # noqa: N802 - protobuf API
        return self._which_oneofs.get(name)


def _fake_extended_telemetry_frame() -> Any:
    asset = _FakeProto(
        id="AST-9",
        timestamp=timestamp_pb2.Timestamp(),
        sn="SN-9",
        latitude=12.34,
        longitude=56.78,
        absoluteAltitude=123.4,
        relativeAltitude=23.4,
        environmentTemp=18.5,
        insideTemp=21.0,
        humidity=65.0,
        mode=common_pb2.AssetMode.ASSET_MODE_WORKING,
        rainfall=common_pb2.RainfallEnum.RAINFALL_LIGHT,
        subAssetInformation=_FakeProto(
            sn="SUB-1",
            model="M-1",
            paired=True,
            online=False,
        ),
        subAssetAtHome=True,
        subAssetCharging=False,
        subAssetPercentage=77.5,
        heading=182.5,
        debugModeOpen=True,
        hasActiveManualControlSession=True,
        coverState=common_pb2.AssetCoverStateEnum.COVER_STATE_OPENED,
        workingVoltage=24,
        workingCurrent=3,
        supplyVoltage=12,
        windSpeed=6.2,
        positionValid=True,
        networkInformation=_FakeProto(
            type=common_pb2.NetworkTypeEnum.NETWORK_TYPE_4_G,
            rate=42.5,
            quality=common_pb2.NetworkStateQualityEnum.NETWORK_STATE_QUALITY_GOOD,
        ),
        airConditioner=_FakeProto(
            state=common_pb2.AssetAirConditionerStateEnum.AIR_CONDITIONER_COOL,
            switchTime=15,
        ),
        manualControlState=common_pb2.ManualControlStateEnum.MANUAL_CONTROL_STATE_CONNECTED,
        positionState=_FakeProto(
            gpsNumber=9,
            rtkNumber=5,
            quality=3,
        ),
        wirelessLink=_FakeProto(
            fourthGenerationFreqBand=2.4,
            fourthGenerationGndQuality=88,
            fourthGenerationLinkState=True,
            fourthGenerationQuality=77,
            fourthGenerationUavQuality=66,
            dongleNumber=2,
            linkWorkmode="AUTO",
            sdrFreqBand=5.8,
            sdrLinkState=False,
            sdrQuality=44,
        ),
        sdrState=_FakeProto(
            downQuality=91,
            upQuality=73,
            frequencyBand=5.2,
        ),
    )
    return _FakeProto(
        _which_oneofs={"telemetry": "assetTelemetry"},
        tid="tid-stream",
        sn="DOCK-1",
        timestamp=timestamp_pb2.Timestamp(),
        hasErrors=False,
        assetId="AST-9",
        assetTelemetry=asset,
    )


def _notification_asset_status_frame() -> live_data_pb2.LiveDataNotificationResponse:
    return live_data_pb2.LiveDataNotificationResponse(
        tid="tid-notify",
        sn="DOCK-1",
        hasErrors=False,
        assetId="AST-1",
        assetStatus=live_data_pb2.AssetStatusEvent(
            sn="DOCK-1",
            assetId="AST-1",
            online=True,
            message="online",
        ),
    )


def _notification_task_frame() -> live_data_pb2.LiveDataNotificationResponse:
    return live_data_pb2.LiveDataNotificationResponse(
        tid="tid-notify",
        sn="DOCK-1",
        hasErrors=False,
        taskEvent=live_data_pb2.TaskEvent(
            taskId="task-1",
            taskType=common_pb2.TaskTypeProto.TASK_TYPE_WAYPOINT,
            status=common_pb2.TaskStatus.TASK_RUNNING,
            progress=0.5,
            message="running",
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

    def StreamNotifications(self, request):  # noqa: N802 - gRPC name
        self.last_request = request
        self.call_count += 1
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
async def test_stream_telemetry_decodes_extended_asset_fields() -> None:
    stub = _StreamStub([_fake_extended_telemetry_frame()])
    client = _build_client(stub)

    received: list[Any] = []

    def on_data(frame):
        received.append(frame)

    handle = client.stream_telemetry(
        StreamTelemetryRequest(sn="DOCK-1"),
        on_data,
    )

    await asyncio.sleep(0.05)
    await handle.stop()

    assert len(received) == 1
    asset = received[0].asset_telemetry
    assert asset is not None
    assert asset.id == "AST-9"
    assert asset.latitude == pytest.approx(12.34)
    assert asset.longitude == pytest.approx(56.78)
    assert asset.absolute_altitude == pytest.approx(123.4)
    assert asset.relative_altitude == pytest.approx(23.4)
    assert asset.environment_temp == pytest.approx(18.5)
    assert asset.inside_temp == pytest.approx(21.0)
    assert asset.humidity == pytest.approx(65.0)
    assert asset.mode == "ASSET_MODE_WORKING"
    assert asset.rainfall == "RAINFALL_LIGHT"
    assert asset.sub_asset_information is not None
    assert asset.sub_asset_information.sn == "SUB-1"
    assert asset.sub_asset_information.model == "M-1"
    assert asset.sub_asset_information.paired is True
    assert asset.sub_asset_information.online is False
    assert asset.sub_asset_at_home is True
    assert asset.sub_asset_charging is False
    assert asset.sub_asset_percentage == pytest.approx(77.5)
    assert asset.heading == pytest.approx(182.5)
    assert asset.debug_mode_open is True
    assert asset.has_active_manual_control_session is True
    assert asset.cover_state == "COVER_STATE_OPENED"
    assert asset.working_voltage == 24
    assert asset.working_current == 3
    assert asset.supply_voltage == 12
    assert asset.wind_speed == pytest.approx(6.2)
    assert asset.position_valid is True
    assert asset.network_information is not None
    assert asset.network_information.type == "NETWORK_TYPE_4_G"
    assert asset.network_information.rate == pytest.approx(42.5)
    assert asset.network_information.quality == "NETWORK_STATE_QUALITY_GOOD"
    assert asset.air_conditioner is not None
    assert asset.air_conditioner.state == "AIR_CONDITIONER_COOL"
    assert asset.air_conditioner.switch_time == 15
    assert asset.manual_control_state == "MANUAL_CONTROL_STATE_CONNECTED"
    assert asset.position_state is not None
    assert asset.position_state.gps_number == 9
    assert asset.position_state.rtk_number == 5
    assert asset.position_state.quality == 3
    assert asset.sn == "SN-9"
    assert asset.wireless_link is not None
    assert asset.wireless_link.fourth_generation_freq_band == pytest.approx(2.4)
    assert asset.wireless_link.fourth_generation_gnd_quality == 88
    assert asset.wireless_link.fourth_generation_link_state is True
    assert asset.wireless_link.fourth_generation_quality == 77
    assert asset.wireless_link.fourth_generation_uav_quality == 66
    assert asset.wireless_link.dongle_number == 2
    assert asset.wireless_link.link_workmode == "AUTO"
    assert asset.wireless_link.sdr_freq_band == pytest.approx(5.8)
    assert asset.wireless_link.sdr_link_state is False
    assert asset.wireless_link.sdr_quality == 44
    assert asset.sdr_state is not None
    assert asset.sdr_state.down_quality == 91
    assert asset.sdr_state.up_quality == 73
    assert asset.sdr_state.frequency_band == pytest.approx(5.2)
    assert handle.is_stopped is True


@pytest.mark.asyncio
async def test_stream_notifications_pumps_frames_into_callback() -> None:
    stub = _StreamStub([_notification_asset_status_frame(), _notification_task_frame()])
    client = _build_client(stub)

    received: list[Any] = []

    def on_data(frame):
        received.append(frame)

    handle = client.stream_notifications(
        StreamNotificationRequest(
            sn="DOCK-1",
            event_types=[NotificationEventType.ASSET_STATUS, NotificationEventType.TASK],
        ),
        on_data,
    )

    await asyncio.sleep(0.05)
    await handle.stop()

    assert len(received) == 2
    assert received[0].event_type == "NOTIFICATION_EVENT_ASSET_STATUS"
    assert received[0].asset_status is not None
    assert received[0].asset_status.online is True
    assert received[1].event_type == "NOTIFICATION_EVENT_TASK"
    assert received[1].task_event is not None
    assert received[1].task_event.status == "TASK_RUNNING"
    sent_request = stub.last_request
    assert sent_request.eventTypes == [NotificationEventType.ASSET_STATUS, NotificationEventType.TASK]
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

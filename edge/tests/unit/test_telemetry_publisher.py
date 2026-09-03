"""
Unit tests for TelemetryPublisher – no live gRPC connection required.

Tests the queue lifecycle, publish guards, drop-on-full behaviour, and the
stream generator stop conditions without starting a real gRPC stream.
"""

import asyncio
from unittest.mock import patch

import pytest

from edge_sdk.client.telemetry_publisher import _SENTINEL, TelemetryPublisher
from edge_sdk.models.telemetry import (
    AssetAirConditioner,
    AssetNetworkInfo,
    AssetPositionState,
    AssetSubAssetInfo,
    AssetTelemetry,
    PayloadTelemetry,
    SubAssetBatteryInfo,
    SubAssetTelemetry,
)


class _FakePublisher(TelemetryPublisher):
    """TelemetryPublisher with the queue pre-initialised; stream task bypassed."""

    def __init__(self, queue_max_size: int = 100):
        super().__init__(host="localhost", sn="TEST-001", queue_max_size=queue_max_size)
        self._queue = asyncio.Queue(maxsize=queue_max_size)
        self._closed = False


# ---------------------------------------------------------------------------
# Guard: publish before connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_asset_before_connect_raises():
    pub = TelemetryPublisher(host="localhost", sn="TEST")
    with pytest.raises(RuntimeError, match="connect"):
        await pub.publish_asset_telemetry(AssetTelemetry(id="TEST"))


@pytest.mark.asyncio
async def test_publish_subasset_before_connect_raises():
    pub = TelemetryPublisher(host="localhost", sn="TEST")
    with pytest.raises(RuntimeError, match="connect"):
        await pub.publish_subasset_telemetry(SubAssetTelemetry(id="SUB"))


# ---------------------------------------------------------------------------
# Queue mechanics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_asset_enqueues_frame():
    pub = _FakePublisher()
    with patch.object(pub, "_build_asset_request", return_value="frame"):
        await pub.publish_asset_telemetry(AssetTelemetry(id="DOCK001"))
    assert pub._queue.qsize() == 1


@pytest.mark.asyncio
async def test_publish_subasset_enqueues_frame():
    pub = _FakePublisher()
    with patch.object(pub, "_build_subasset_request", return_value="frame"):
        await pub.publish_subasset_telemetry(SubAssetTelemetry(id="DRONE001"))
    assert pub._queue.qsize() == 1


@pytest.mark.asyncio
async def test_publish_multiple_frames_are_all_queued():
    pub = _FakePublisher(queue_max_size=10)
    with patch.object(pub, "_build_asset_request", return_value="frame"):
        for _ in range(5):
            await pub.publish_asset_telemetry(AssetTelemetry(id="DOCK001"))
    assert pub._queue.qsize() == 5


@pytest.mark.asyncio
async def test_queue_full_drops_asset_frame_silently():
    pub = _FakePublisher(queue_max_size=1)
    pub._queue.put_nowait("pre-existing")  # fill it up
    with patch.object(pub, "_build_asset_request", return_value="frame"):
        # Must not raise – drop silently
        await pub.publish_asset_telemetry(AssetTelemetry(id="DOCK001"))
    assert pub._queue.qsize() == 1  # still 1 – dropped


@pytest.mark.asyncio
async def test_queue_full_drops_subasset_frame_silently():
    pub = _FakePublisher(queue_max_size=1)
    pub._queue.put_nowait("pre-existing")
    with patch.object(pub, "_build_subasset_request", return_value="frame"):
        await pub.publish_subasset_telemetry(SubAssetTelemetry(id="DRONE001"))
    assert pub._queue.qsize() == 1


# ---------------------------------------------------------------------------
# close() before connect() is safe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_before_connect_does_not_raise():
    pub = TelemetryPublisher(host="localhost", sn="TEST")
    await pub.close()  # must not raise


# ---------------------------------------------------------------------------
# _stream_generator stop conditions (pure async logic, no gRPC)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_generator_yields_queued_frames():
    pub = _FakePublisher()
    gen_stop = asyncio.Event()
    pub._queue.put_nowait("frame1")
    pub._queue.put_nowait("frame2")
    pub._queue.put_nowait(_SENTINEL)

    frames = []
    async for item in pub._stream_generator(gen_stop):
        frames.append(item)

    assert frames == ["frame1", "frame2"]


@pytest.mark.asyncio
async def test_stream_generator_stops_on_sentinel():
    pub = _FakePublisher()
    gen_stop = asyncio.Event()
    pub._queue.put_nowait("frame1")
    pub._queue.put_nowait(_SENTINEL)
    pub._queue.put_nowait("frame2")  # should never be yielded

    frames = []
    async for item in pub._stream_generator(gen_stop):
        frames.append(item)

    assert frames == ["frame1"]


@pytest.mark.asyncio
async def test_stream_generator_stops_when_already_closed():
    pub = _FakePublisher()
    pub._closed = True  # closed before generator is entered
    gen_stop = asyncio.Event()
    pub._queue.put_nowait("frame1")

    frames = []
    async for item in pub._stream_generator(gen_stop):
        frames.append(item)

    assert frames == []


@pytest.mark.asyncio
async def test_stream_generator_stops_when_gen_stop_set():
    pub = _FakePublisher()
    gen_stop = asyncio.Event()
    gen_stop.set()  # already stopped before generator is entered
    pub._queue.put_nowait("frame1")

    frames = []
    async for item in pub._stream_generator(gen_stop):
        frames.append(item)

    assert frames == []


@pytest.mark.asyncio
async def test_stream_generator_restores_sentinel_to_queue():
    """After consuming SENTINEL the generator must put it back so close() can detect it."""
    pub = _FakePublisher()
    gen_stop = asyncio.Event()
    pub._queue.put_nowait(_SENTINEL)

    async for _ in pub._stream_generator(gen_stop):
        pass

    # Sentinel must have been restored
    item = pub._queue.get_nowait()
    assert item is _SENTINEL


# ---------------------------------------------------------------------------
# Real proto construction -- every other test in this file mocks
# _build_asset_request/_build_subasset_request out entirely, which is exactly how a wrong
# message/module reference in them (AssetTelemetry vs. AssetTelemetryDetails, live_data_pb2 vs.
# live_data_types_pb2 -- both real bugs, only ever caught live against a running platform, never
# by this suite) went unnoticed. These call the real builders and inspect the resulting proto.
# ---------------------------------------------------------------------------


def test_build_asset_request_flat_fields():
    pub = TelemetryPublisher(host="localhost", sn="TEST-001")
    req = pub._build_asset_request(
        AssetTelemetry(id="DOCK001", latitude=47.5, longitude=9.7, environment_temp=21.5)
    )
    assert req.base.sn == "DOCK001"
    # latitude/longitude live on the Telemetry envelope, not on AssetTelemetryDetails.
    assert req.data.id == "DOCK001"
    assert req.data.latitude == pytest.approx(47.5)
    assert req.data.longitude == pytest.approx(9.7)
    assert req.data.HasField("asset")
    assert req.data.asset.environment_temp == pytest.approx(21.5)


def test_build_asset_request_nested_fields():
    pub = TelemetryPublisher(host="localhost", sn="TEST-001")
    req = pub._build_asset_request(
        AssetTelemetry(
            id="DOCK001",
            sub_asset_info=AssetSubAssetInfo(sn="DRONE001", model="M30", paired=True, online=True),
            network_info=AssetNetworkInfo(rate=12.5),
            air_conditioner=AssetAirConditioner(switch_time=30),
            position_state=AssetPositionState(gps_number=9, rtk_number=2, quality=1),
        )
    )
    details = req.data.asset
    assert details.sub_asset_information.sn == "DRONE001"
    assert details.sub_asset_information.paired is True
    assert details.network_information.rate == pytest.approx(12.5)
    assert details.air_conditioner.switch_time == 30
    assert details.position_state.gps_number == 9


def test_build_subasset_request_flat_and_battery():
    pub = TelemetryPublisher(host="localhost", sn="TEST-001")
    req = pub._build_subasset_request(
        SubAssetTelemetry(
            id="DRONE001",
            latitude=47.5,
            horizontal_speed=5.0,
            battery=SubAssetBatteryInfo(percentage=88.5, remaining_time=1200),
        )
    )
    assert req.base.sn == "DRONE001"
    assert req.data.id == "DRONE001"
    assert req.data.latitude == pytest.approx(47.5)
    assert req.data.HasField("sub_asset")
    details = req.data.sub_asset
    assert details.horizontal_speed == pytest.approx(5.0)
    # SubAssetBatteryInformation.percentage is a proto `string`, not a number.
    assert details.battery_information.percentage == "88.5"
    assert details.battery_information.remaining_time == 1200


def test_build_subasset_request_payload():
    pub = TelemetryPublisher(host="localhost", sn="TEST-001")
    req = pub._build_subasset_request(
        SubAssetTelemetry(id="DRONE001", payload=PayloadTelemetry(id="CAM1", name="Zenmuse H20"))
    )
    payload = req.data.sub_asset.payload_telemetry
    assert payload.id == "CAM1"
    assert payload.name == "Zenmuse H20"

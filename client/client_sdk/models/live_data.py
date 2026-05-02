"""Domain models for the LiveData sub-client.

Mirrors ``com.zqnt.sdk.client.livedata.domains`` from the Java client SDK.
The ``StreamTelemetryResponse`` payload (asset / sub-asset telemetry) is
expressed as plain dataclasses so SDK consumers never see protobuf types.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .enums import AssetType, LiveStreamType

# ---------------------------------------------------------------------------
# Request dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StreamTelemetryRequest:
    """Subscription request for the ``StreamTelemetry`` server-streaming RPC."""

    sn: str
    frequency_ms: int = 0
    duration_seconds: int = 0
    asset_id: str | None = None
    tid: str | None = None


@dataclass(slots=True)
class LiveDataStartLiveStreamRequest:
    sn: str
    video_id: str
    stream_server: str
    stream_type: LiveStreamType = LiveStreamType.RTMP
    asset_type: AssetType = AssetType.AIRCRAFT
    asset_id: str | None = None
    tid: str | None = None


@dataclass(slots=True)
class LiveDataStopLiveStreamRequest:
    sn: str
    video_id: str
    asset_id: str | None = None
    tid: str | None = None


@dataclass(slots=True)
class ChangeLensRequest:
    sn: str
    lens: str
    asset_id: str | None = None
    tid: str | None = None


@dataclass(slots=True)
class ChangeZoomRequest:
    sn: str
    zoom: int
    lens: str | None = None
    asset_id: str | None = None
    tid: str | None = None


# ---------------------------------------------------------------------------
# Response dataclasses (unary)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LiveStreamStartResult:
    """Detail returned by ``startLiveStream``."""

    stream_url: str
    video_id: str


@dataclass(slots=True)
class LiveDataResponse:
    """Unary response for ``start/stopLiveStream``, ``changeLens``, ``changeZoom``."""

    success: bool
    tid: str
    sn: str
    asset_id: str | None = None
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    timestamp: datetime | None = None
    live_stream_start: LiveStreamStartResult | None = None


# ---------------------------------------------------------------------------
# Telemetry payloads — flat dataclasses returned by the streaming RPC.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CameraData:
    current_lens: str | None = None
    gimbal_pitch: float | None = None
    gimbal_yaw: float | None = None
    gimbal_roll: float | None = None
    zoom_factor: float | None = None


@dataclass(slots=True)
class RangeFinderData:
    target_latitude: float | None = None
    target_longitude: float | None = None
    target_distance: float | None = None
    target_altitude: float | None = None


@dataclass(slots=True)
class SensorData:
    target_temperature: float | None = None


@dataclass(slots=True)
class PayloadTelemetry:
    id: str
    name: str = ""
    timestamp: datetime | None = None
    camera: CameraData | None = None
    range_finder: RangeFinderData | None = None
    sensor: SensorData | None = None


@dataclass(slots=True)
class SubAssetBatteryInfo:
    percentage: str | None = None
    remaining_time: int | None = None
    return_to_home_power: str | None = None


@dataclass(slots=True)
class AssetSubAssetInformation:
    sn: str | None = None
    model: str | None = None
    paired: bool | None = None
    online: bool | None = None


@dataclass(slots=True)
class AssetNetworkInfo:
    type: str | None = None
    rate: float | None = None
    quality: str | None = None


@dataclass(slots=True)
class AssetAirConditioner:
    state: str | None = None
    switch_time: int | None = None


@dataclass(slots=True)
class AssetPositionState:
    gps_number: int | None = None
    rtk_number: int | None = None
    quality: int | None = None


@dataclass(slots=True)
class AssetTelemetry:
    id: str
    timestamp: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    absolute_altitude: float | None = None
    relative_altitude: float | None = None
    environment_temp: float | None = None
    inside_temp: float | None = None
    humidity: float | None = None
    mode: str | None = None
    rainfall: str | None = None
    sub_asset_information: AssetSubAssetInformation | None = None
    sub_asset_at_home: bool | None = None
    sub_asset_charging: bool | None = None
    sub_asset_percentage: float | None = None
    heading: float | None = None
    debug_mode_open: bool | None = None
    has_active_manual_control_session: bool | None = None
    cover_state: str | None = None
    working_voltage: int | None = None
    working_current: int | None = None
    supply_voltage: int | None = None
    wind_speed: float | None = None
    position_valid: bool | None = None
    network_information: AssetNetworkInfo | None = None
    air_conditioner: AssetAirConditioner | None = None
    manual_control_state: str | None = None
    position_state: AssetPositionState | None = None


@dataclass(slots=True)
class SubAssetTelemetry:
    id: str
    timestamp: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    absolute_altitude: float | None = None
    relative_altitude: float | None = None
    horizontal_speed: float | None = None
    vertical_speed: float | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    heading: float | None = None
    gear: int | None = None
    payload: PayloadTelemetry | None = None
    battery: SubAssetBatteryInfo | None = None
    height_limit: int | None = None
    home_distance: float | None = None
    total_movement_distance: float | None = None
    total_movement_time: float | None = None
    mode: str | None = None
    country: str | None = None


@dataclass(slots=True)
class StreamTelemetryError:
    error_code: str
    error_message: str
    timestamp: datetime | None = None


@dataclass(slots=True)
class StreamTelemetryResponse:
    """Single frame of the ``StreamTelemetry`` server-streaming RPC.

    Exactly one of ``asset_telemetry``, ``sub_asset_telemetry`` or ``error``
    is populated per frame. ``has_errors`` indicates whether ``error`` is set.
    """

    tid: str
    sn: str
    timestamp: datetime | None = None
    has_errors: bool = False
    asset_id: str | None = None
    asset_telemetry: AssetTelemetry | None = None
    sub_asset_telemetry: SubAssetTelemetry | None = None
    error: StreamTelemetryError | None = None

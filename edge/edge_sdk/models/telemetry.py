"""
Plain-Python telemetry models mirroring live-data.proto.
"""

from dataclasses import dataclass
from datetime import datetime

from .common import (
    AssetMode,
    AssetCoverState,
    AssetAirConditionerState,
    ManualControlState,
    NetworkType,
    NetworkStateQuality,
    Rainfall,
    SubAssetMode,
)


# ---------------------------------------------------------------------------
# Payload / camera
# ---------------------------------------------------------------------------

@dataclass
class CameraData:
    current_lens: str | None = None
    gimbal_pitch: float | None = None
    gimbal_yaw: float | None = None
    zoom_factor: float | None = None
    gimbal_roll: float | None = None


@dataclass
class RangeFinderData:
    target_latitude: float | None = None
    target_longitude: float | None = None
    target_distance: float | None = None
    target_altitude: float | None = None


@dataclass
class SensorData:
    target_temperature: float | None = None


@dataclass
class PayloadTelemetry:
    id: str
    name: str
    timestamp: datetime | None = None
    camera: CameraData | None = None
    range_finder: RangeFinderData | None = None
    sensor: SensorData | None = None


# ---------------------------------------------------------------------------
# Sub-asset (drone) telemetry
# ---------------------------------------------------------------------------

@dataclass
class SubAssetBatteryInfo:
    percentage: str | None = None
    remaining_time: int | None = None
    return_to_home_power: str | None = None


@dataclass
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
    mode: SubAssetMode | None = None
    country: str | None = None


# ---------------------------------------------------------------------------
# Asset (dock / station) telemetry
# ---------------------------------------------------------------------------

@dataclass
class AssetNetworkInfo:
    type: NetworkType | None = None
    rate: float | None = None
    quality: NetworkStateQuality | None = None


@dataclass
class AssetAirConditioner:
    state: AssetAirConditionerState | None = None
    switch_time: int | None = None


@dataclass
class AssetSubAssetInfo:
    """Summary of the sub-asset paired with this dock."""
    sn: str | None = None
    model: str | None = None
    paired: bool | None = None
    online: bool | None = None


@dataclass
class AssetPositionState:
    gps_number: int | None = None
    rtk_number: int | None = None
    quality: int | None = None


@dataclass
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
    mode: AssetMode | None = None
    rainfall: Rainfall | None = None
    sub_asset_info: AssetSubAssetInfo | None = None
    sub_asset_at_home: bool | None = None
    sub_asset_charging: bool | None = None
    sub_asset_percentage: float | None = None
    heading: float | None = None
    debug_mode_open: bool | None = None
    has_active_manual_control_session: bool | None = None
    cover_state: AssetCoverState | None = None
    working_voltage: int | None = None
    working_current: int | None = None
    supply_voltage: int | None = None
    wind_speed: float | None = None
    position_valid: bool | None = None
    network_info: AssetNetworkInfo | None = None
    air_conditioner: AssetAirConditioner | None = None
    manual_control_state: ManualControlState | None = None
    position_state: AssetPositionState | None = None

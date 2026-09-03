"""
Plain-Python models that mirror the common.proto definitions.
No protobuf types are exposed here.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Type, TypeVar

_E = TypeVar("_E", bound=IntEnum)


def proto_enum_lookup(enum_cls: Type[_E], name: str) -> _E:
    """
    Resolve a proto-style full enum name to the Python IntEnum value.

    The prefix is derived from the class name (CamelCase → SCREAMING_SNAKE_CASE):
    ``AssetType`` → ``ASSET_TYPE_``, ``AssetVendor`` → ``ASSET_VENDOR_``.

    Examples::

        proto_enum_lookup(AssetType, "ASSET_TYPE_AIRCRAFT")    # → AssetType.AIRCRAFT
        proto_enum_lookup(AssetVendor, "ASSET_VENDOR_MAVLINK") # → AssetVendor.MAVLINK
    """
    prefix = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", enum_cls.__name__).upper() + "_"
    if not name.upper().startswith(prefix):
        raise KeyError(
            f"{name!r} is not a valid {enum_cls.__name__} proto name — "
            f"expected prefix {prefix!r} (e.g. {prefix}AIRCRAFT)"
        )
    return enum_cls[name.upper()[len(prefix) :]]


def proto_enum_name(value: IntEnum) -> str:
    """
    Convert a Python IntEnum value to its proto-style full name.

    The prefix is derived from the class name (CamelCase → SCREAMING_SNAKE_CASE).

    Examples::

        proto_enum_name(AssetType.AIRCRAFT)    # → "ASSET_TYPE_AIRCRAFT"
        proto_enum_name(AssetVendor.MAVLINK)   # → "ASSET_VENDOR_MAVLINK"
    """
    prefix = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", type(value).__name__).upper() + "_"
    return prefix + value.name


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssetType(IntEnum):
    UNKNOWN = 0
    AIRCRAFT = 1
    DOCK = 2
    SENSOR = 3
    CAMERA = 4
    OTHER = 5
    JAMMER = 6
    CYBER_ATTACK = 7
    SAPIENT = 8
    RNS = 9


class AssetVendor(IntEnum):
    DJI = 0
    AUTEL = 1
    ROS = 2
    MAVLINK = 3
    RTMP_RTSP = 4
    SAPIENT = 5
    BETAFLIGHT = 6
    RNS = 7
    # No ZQNT member on this branch -- ASSET_VENDOR_ZQNT was added to asset.proto after the 1.3.0
    # tag (see zqnt-protos' README Versioning section); this branch tracks 1.3.0 exactly, so this
    # enum mirrors the 1.3.0 proto's AssetVendor one-to-one, not main's.


class AssetConnection(IntEnum):
    MQTT = 0
    TCP = 1
    SERIAL = 2


class LiveStreamType(IntEnum):
    UNKNOWN = 0
    RTMP = 1
    RTSP = 2
    WEBRTC = 3


class AssetMode(IntEnum):
    IDLE = 0
    DEBUGGING = 1
    REMOTE_DEBUGGING = 2
    UPGRADING = 3
    WORKING = 4
    TO_BE_CALIBRATED = 5
    OFFLINE = 6


class SubAssetMode(IntEnum):
    IDLE = 0
    TAKEOFF_PREPARE = 1
    TAKEOFF_FINISHED = 2
    MANUAL = 3
    TAKEOFF_AUTO = 4
    WAYLINE = 5
    PANORAMIC_SHOT = 6
    ACTIVE_TRACK = 7
    ADS_B_AVOIDANCE = 8
    RETURN_AUTO = 9
    LANDING_AUTO = 10
    LANDING_FORCE = 11
    LANDING_THREE_PROPELLER = 12
    UPGRADING = 13
    DISCONNECTED = 14
    APAS = 15
    VIRTUAL_JOYSTICK = 16
    LIVE_FLIGHT_CONTROLS = 17
    AERIAL_RTK_FIXED = 18
    DOCK_SITE_EVALUATION = 19
    POI = 20


class ManualControlState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2


class AssetCoverState(IntEnum):
    CLOSED = 0
    OPENED = 1
    HALF_OPEN = 2
    ABNORMAL = 3


class AssetAirConditionerState(IntEnum):
    IDLE = 0
    COOL = 1
    HEAT = 2
    DEHUMIDIFICATION = 3
    COOLING_EXIT = 4
    HEATING_EXIT = 5
    DEHUMIDIFICATION_EXIT = 6
    COOLING_PREPARATION = 7
    HEATING_PREPARATION = 8
    DEHUMIDIFICATION_PREPARATION = 9
    DISCONNECTED = 10


class TaskType(IntEnum):
    UNSPECIFIED = 0
    DETECT = 1
    AREA_MAPPING = 2
    WAYPOINT = 3
    POI = 4
    FOLLOW = 5
    TRACK = 6
    COUNTER_DRONE = 7


class TaskStatus(IntEnum):
    UNKNOWN = 0
    DRAFT = 1
    SCHEDULED = 2
    RUNNING = 3
    ERROR = 4
    COMPLETED = 5
    PREPARED = 6
    PAUSED = 7


class MissionType(IntEnum):
    STANDARD = 0
    REMOTE_OPS = 1
    DRF = 2
    MISSION = 3


class MissionStatus(IntEnum):
    UNKNOWN = 0
    DRAFT = 1
    ACTIVE = 2
    INACTIVE = 3
    ERROR = 4


class SchedulerType(IntEnum):
    """Mirrors ``mission-autonomy-types.proto`` :proto:`SchedulerType`."""

    MISSION = 0
    TASK = 1
    SYSTEM_JOBS = 2
    ORGANIZATION = 3
    DATABASE = 4
    CONNECTORS = 5


# No CommandExecutionStatus on this branch -- events.proto's CommandExecutionEvent/
# CommandExecutionStatus don't exist at the 1.3.0 contract (added later, replacing the
# TaskEvent-based model TaskStatus above still serves here). See models/notification.py.


class ErrorCode(IntEnum):
    SYSTEM_ERROR = 0
    CLIENT_ERROR = 1
    SDK_ERROR = 2
    SERVICE_ERROR = 3
    ASSET_ERROR = 4


class Rainfall(IntEnum):
    NO = 0
    LIGHT = 1
    MODERATE = 2
    HEAVY = 3


class NetworkType(IntEnum):
    NETWORK_4G = 0
    ETHERNET = 1


class NetworkStateQuality(IntEnum):
    NO_SIGNAL = 0
    BAD = 1
    POOR = 2
    FAIR = 3
    GOOD = 4
    EXCELLENT = 5


class VehicleAction(IntEnum):
    NONE = 0
    TAKEOFF = 1
    LAND = 2


# ---------------------------------------------------------------------------
# Base / shared dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Coordinates:
    latitude: float
    longitude: float
    altitude: float


@dataclass
class RequestContext:
    """
    Extracted from gRPC RequestBase – identifies the incoming request.

    Attributes:
        tid:       Transaction ID (unique per request).
        sn:        Asset serial number the command is addressed to.
        timestamp: Time the request was created on the sender side.
    """

    tid: str
    sn: str
    timestamp: datetime


@dataclass
class ErrorMessage:
    message: str
    code: ErrorCode
    timestamp: datetime | None = None


@dataclass
class CommandProgress:
    progress: float  # 0.0 – 100.0
    state: str
    left_time_seconds: float


@dataclass
class EdgeResponse:
    """
    Return this from every adapter method.

    Use the factory methods :meth:`ok` and :meth:`fail` for convenience.
    """

    tid: str
    sn: str
    success: bool
    asset_id: str | None = None
    message: str | None = None
    error: ErrorMessage | None = None
    progress: CommandProgress | None = None
    # Populated only for StartLiveStream responses
    stream_url: str | None = None
    video_id: str | None = None
    # The id mission-autonomy should track this dispatch by for later correlation — physical
    # cancellation (StopTask with task_id = this value, not a Connector Task id — that model is
    # retired) and async CommandExecutionEvent completion binding both key off it. Prefer your own
    # vendor execution id when you have one (e.g. a DJI flightId); otherwise leave unset and the
    # platform falls back to its own internally-generated correlation id, which still works for
    # cancellation but only if your adapter's own completion/cancel handling doesn't need to
    # distinguish between concurrent executions on the same asset.
    external_execution_id: str | None = None

    @classmethod
    def ok(
        cls,
        tid: str,
        sn: str,
        message: str | None = None,
        *,
        asset_id: str | None = None,
        stream_url: str | None = None,
        video_id: str | None = None,
        progress: CommandProgress | None = None,
        external_execution_id: str | None = None,
    ) -> "EdgeResponse":
        return cls(
            tid=tid,
            sn=sn,
            success=True,
            message=message,
            asset_id=asset_id,
            stream_url=stream_url,
            video_id=video_id,
            progress=progress,
            external_execution_id=external_execution_id,
        )

    @classmethod
    def fail(
        cls,
        tid: str,
        sn: str,
        error: ErrorMessage,
        asset_id: str | None = None,
    ) -> "EdgeResponse":
        return cls(
            tid=tid,
            sn=sn,
            success=False,
            error=error,
            asset_id=asset_id,
        )

    @classmethod
    def not_supported(cls, tid: str = "", sn: str = "") -> "EdgeResponse":
        """Return this from default adapter methods that are not implemented."""
        return cls(
            tid=tid,
            sn=sn,
            success=False,
            error=ErrorMessage(
                message="This operation is not supported by this adapter",
                code=ErrorCode.SDK_ERROR,
            ),
        )


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


@dataclass
class Capability:
    command: str
    description: str
    available: bool
    unavailable_reason: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class Capabilities:
    asset_sn: str
    asset_type: AssetType
    capabilities: list[Capability] = field(default_factory=list)
    timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Control requests
# ---------------------------------------------------------------------------


@dataclass
class ReturnToHomeRequest:
    altitude: float | None = None


@dataclass
class ManualControlRequest:
    client_id: str
    user_id: str
    session_id: str
    reason: str | None = None


@dataclass
class ManualControlInput:
    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    throttle: float | None = None
    gimbal_pitch: float | None = None


# ---------------------------------------------------------------------------
# Live stream
# ---------------------------------------------------------------------------


@dataclass
class LiveStreamStartRequest:
    video_id: str
    stream_server: str
    stream_type: LiveStreamType
    asset_type: AssetType


@dataclass
class LiveStreamStopRequest:
    video_id: str


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------


@dataclass
class ChangeCameraLensRequest:
    lens: str | None = None


@dataclass
class ChangeCameraZoomRequest:
    lens: str | None = None
    zoom: int | None = None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass
class DetectionResult:
    object_id: str
    object_type: str
    confidence: float
    bounding_box: BoundingBox


@dataclass
class DetectionResponse:
    detections: list[DetectionResult] = field(default_factory=list)


@dataclass
class DetectionBatch:
    """Batch of detection results to publish via DetectionPublisher."""

    sn: str = ""  # asset serial number – required for multi-asset adapters
    detections: list[DetectionResult] = field(default_factory=list)
    stream_url: str | None = None


# ---------------------------------------------------------------------------
# Custom command
# ---------------------------------------------------------------------------


@dataclass
class CustomCommandRequest:
    command_type: str
    params: dict = field(default_factory=dict)


@dataclass
class CustomCommandResponse:
    """
    Return this from :meth:`~edge_sdk.EdgeAdapter.send_custom_command`.

    Use the factory methods :meth:`ok` and :meth:`fail` for convenience.
    """

    tid: str
    sn: str
    success: bool
    command_type: str
    result: dict | None = None
    message: str | None = None
    error: ErrorMessage | None = None
    # Same purpose as EdgeResponse.external_execution_id — set this when the command you just
    # accepted keeps running asynchronously (e.g. a waypoint mission) so mission-autonomy can
    # later cancel it (StopTask) and correlate CommandExecutionEvent notifications back to this
    # execution. Leave unset for commands that are already fully done by the time you return.
    external_execution_id: str | None = None

    @classmethod
    def ok(
        cls,
        tid: str,
        sn: str,
        command_type: str,
        result: dict | None = None,
        message: str | None = None,
        *,
        external_execution_id: str | None = None,
    ) -> "CustomCommandResponse":
        return cls(
            tid=tid,
            sn=sn,
            success=True,
            command_type=command_type,
            result=result,
            message=message,
            external_execution_id=external_execution_id,
        )

    @classmethod
    def fail(
        cls,
        tid: str,
        sn: str,
        command_type: str,
        error: ErrorMessage,
    ) -> "CustomCommandResponse":
        return cls(tid=tid, sn=sn, success=False, command_type=command_type, error=error)

    @classmethod
    def not_supported(cls, tid: str = "", sn: str = "", command_type: str = "") -> "CustomCommandResponse":
        return cls(
            tid=tid,
            sn=sn,
            success=False,
            command_type=command_type,
            error=ErrorMessage(
                message="This operation is not supported by this adapter",
                code=ErrorCode.SDK_ERROR,
            ),
        )

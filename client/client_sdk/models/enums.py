"""IntEnum mirrors of the proto enums.

Kept separate from :mod:`client_sdk.models.common` so the enum file stays small
and importable without dragging in dataclass machinery.
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    """Mirrors ``common.proto`` :proto:`ErrorCode`."""

    SYSTEM_ERROR = 0
    CLIENT_ERROR = 1
    SDK_ERROR = 2
    SERVICE_ERROR = 3
    ASSET_ERROR = 4


class AssetType(IntEnum):
    """Mirrors ``common.proto`` :proto:`AssetTypeEnum`."""

    UNKNOWN = 0
    AIRCRAFT = 1
    DOCK = 2
    SENSOR = 3
    CAMERA = 4
    OTHER = 5


class LiveStreamType(IntEnum):
    """Mirrors ``common.proto`` :proto:`LiveStreamTypeEnum`."""

    UNKNOWN = 0
    RTMP = 1
    RTSP = 2
    WEBRTC = 3


class LiveDataServiceCommand(IntEnum):
    """Mirrors ``common.proto`` :proto:`LiveDataServiceCommand`."""

    START_TELEMETRY_STREAM = 0
    GET_TELEMETRY_DATA = 1
    STOP_TELEMETRY_STREAM = 2
    START_LIVE_STREAM = 3
    STOP_LIVE_STREAM = 4


class NotificationEventType(IntEnum):
    """Mirrors ``live-data.proto`` :proto:`NotificationEventType`."""

    UNSPECIFIED = 0
    ASSET_STATUS = 1
    TASK = 2
    OPERATION = 3


class NotificationSeverity(IntEnum):
    """Mirrors ``live-data.proto`` :proto:`NotificationSeverity`."""

    INFO = 0
    WARN = 1
    CRITICAL = 2


class TaskType(IntEnum):
    """Mirrors ``common.proto`` :proto:`TaskTypeProto`."""

    UNSPECIFIED = 0
    DETECT = 1
    AREA_MAPPING = 2
    WAYPOINT = 3
    POI = 4
    FOLLOW = 5
    TRACK = 6
    COUNTER_DRONE = 7


class TaskStatus(IntEnum):
    """Mirrors ``common.proto`` :proto:`TaskStatus`."""

    UNKNOWN = 0
    DRAFT = 1
    SCHEDULED = 2
    RUNNING = 3
    ERROR = 4
    COMPLETED = 5
    PREPARED = 6
    PAUSED = 7


class MissionType(IntEnum):
    """Mirrors ``common.proto`` :proto:`MissionType`."""

    STANDARD = 0
    REMOTE_OPS = 1
    DRF = 2
    MISSION = 3


class MissionStatus(IntEnum):
    """Mirrors ``common.proto`` :proto:`MissionStatus`."""

    UNKNOWN = 0
    DRAFT = 1
    ACTIVE = 2
    INACTIVE = 3
    ERROR = 4


class SchedulerType(IntEnum):
    """Mirrors ``common.proto`` :proto:`SchedulerType`."""

    OPERATION = 0
    TASK = 1
    SYSTEM_JOBS = 2
    ORGANIZATION = 3
    DATABASE = 4
    CONNECTORS = 5

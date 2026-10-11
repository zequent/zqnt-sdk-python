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
    """Mirrors ``mission-autonomy-types.proto`` :proto:`SchedulerType`."""

    MISSION = 0
    TASK = 1
    SYSTEM_JOBS = 2
    ORGANIZATION = 3
    DATABASE = 4
    CONNECTORS = 5

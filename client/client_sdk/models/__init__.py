"""Hand-written dataclasses exposed to SDK consumers.

Generated proto types are kept internal – converters in this package
translate proto <-> dataclass so the public API never leaks protobuf.
"""

from .common import ErrorInfo, ProgressInfo
from .enums import (
    ErrorCode,
    MissionStatus,
    MissionType,
    SchedulerType,
    TaskStatus,
    TaskType,
)
from .mission_autonomy import (
    MissionDTO,
    MissionResponse,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
    WaypointDTO,
)
from .task_config import (
    AreaMappingTaskConfig,
    AreaVertex,
    DetectionParameter,
    DetectTaskConfig,
    FollowTaskConfig,
    PoiTaskConfig,
    TaskConfig,
    TrackTaskConfig,
    WaypointTaskConfig,
)

__all__ = [
    "ErrorInfo",
    "ProgressInfo",
    "ErrorCode",
    "MissionStatus",
    "MissionType",
    "SchedulerType",
    "TaskStatus",
    "TaskType",
    "MissionDTO",
    "MissionResponse",
    "SchedulerDTO",
    "SchedulerResponse",
    "TaskDTO",
    "TaskResponse",
    "WaypointDTO",
    "TaskConfig",
    "AreaMappingTaskConfig",
    "AreaVertex",
    "DetectionParameter",
    "DetectTaskConfig",
    "FollowTaskConfig",
    "PoiTaskConfig",
    "TrackTaskConfig",
    "WaypointTaskConfig",
]

"""Hand-written dataclasses exposed to SDK consumers.

Generated proto types are kept internal - converters in this package
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
    WaypointDTO,
    WaypointTaskConfig,
)

__all__ = [
    "AreaMappingTaskConfig",
    "AreaVertex",
    "DetectTaskConfig",
    "DetectionParameter",
    "ErrorCode",
    "ErrorInfo",
    "FollowTaskConfig",
    "MissionDTO",
    "MissionResponse",
    "MissionStatus",
    "MissionType",
    "PoiTaskConfig",
    "ProgressInfo",
    "SchedulerDTO",
    "SchedulerResponse",
    "SchedulerType",
    "TaskConfig",
    "TaskDTO",
    "TaskResponse",
    "TaskStatus",
    "TaskType",
    "TrackTaskConfig",
    "WaypointDTO",
    "WaypointTaskConfig",
]

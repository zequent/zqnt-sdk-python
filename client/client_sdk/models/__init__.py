"""Hand-written dataclasses exposed to SDK consumers.

Generated proto types are kept internal – converters in this package
translate proto <-> dataclass so the public API never leaks protobuf.
"""

from .common import ErrorInfo, ProgressInfo, RemoteControlResponse, TakeoffResponse
from .enums import (
    AssetType,
    ErrorCode,
    LiveDataServiceCommand,
    LiveStreamType,
    MissionStatus,
    MissionType,
    SchedulerType,
    TaskStatus,
    TaskType,
)
from .live_data import (
    AssetAirConditioner,
    AssetNetworkInfo,
    AssetPositionState,
    AssetSubAssetInformation,
    AssetTelemetry,
    CameraData,
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataResponse,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    LiveStreamStartResult,
    PayloadTelemetry,
    RangeFinderData,
    SensorData,
    StreamTelemetryError,
    StreamTelemetryRequest,
    StreamTelemetryResponse,
    SubAssetBatteryInfo,
    SubAssetTelemetry,
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
from .remote_control import (
    DockOperationRequest,
    GoToRequest,
    LookAtRequest,
    ManualControlRequest,
    ReturnToHomeRequest,
    TakeoffRequest,
)
from .remote_control_input import ManualControlInput
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
    # core responses & error/progress
    "ErrorInfo",
    "ProgressInfo",
    "RemoteControlResponse",
    "TakeoffResponse",
    # enums
    "AssetType",
    "ErrorCode",
    "LiveDataServiceCommand",
    "LiveStreamType",
    "MissionStatus",
    "MissionType",
    "SchedulerType",
    "TaskStatus",
    "TaskType",
    # remote-control requests
    "DockOperationRequest",
    "GoToRequest",
    "LookAtRequest",
    "ManualControlInput",
    "ManualControlRequest",
    "ReturnToHomeRequest",
    "TakeoffRequest",
    # live-data requests + responses + telemetry payloads
    "ChangeLensRequest",
    "ChangeZoomRequest",
    "LiveDataResponse",
    "LiveDataStartLiveStreamRequest",
    "LiveDataStopLiveStreamRequest",
    "LiveStreamStartResult",
    "StreamTelemetryError",
    "StreamTelemetryRequest",
    "StreamTelemetryResponse",
    "AssetAirConditioner",
    "AssetNetworkInfo",
    "AssetPositionState",
    "AssetSubAssetInformation",
    "AssetTelemetry",
    "CameraData",
    "PayloadTelemetry",
    "RangeFinderData",
    "SensorData",
    "SubAssetBatteryInfo",
    "SubAssetTelemetry",
    # mission-autonomy DTOs + responses
    "MissionDTO",
    "MissionResponse",
    "SchedulerDTO",
    "SchedulerResponse",
    "TaskDTO",
    "TaskResponse",
    "WaypointDTO",
    # task config variants
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

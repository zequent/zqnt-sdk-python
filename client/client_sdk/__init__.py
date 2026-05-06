"""
ZQNT Python Client SDK
======================

Python client for the Zequent Framework. Connects to:

  * RemoteControlService     (flight ops, manual control, dock & asset ops)
  * MissionAutonomyService   (mission / task / scheduler CRUD + start/stop)
  * LiveDataService          (telemetry streaming, live stream, camera control)

Quick-start
-----------

1. Generate the gRPC stubs once (requires grpcio-tools)::

       pip install -e ".[dev]"
       bash scripts/generate_protos.sh

2. Use the client::

       from client_sdk import ZequentClient

       async with ZequentClient.from_env() as client:
           resp = await client.remote_control.takeoff(...)
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from .exceptions import ZequentClientError, ZequentRetryExhaustedError
from .live_data.stream_handle import StreamHandle

try:
    __version__ = _pkg_version("zqnt-client-sdk")
except PackageNotFoundError:
    __version__ = "1.0.1"

from .models import (
    AssetTelemetry,
    ChangeLensRequest,
    ChangeZoomRequest,
    DockOperationRequest,
    ErrorInfo,
    GoToRequest,
    LiveDataResponse,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    LookAtRequest,
    ManualControlInput,
    ManualControlRequest,
    MissionDTO,
    MissionResponse,
    MissionStatus,
    MissionType,
    ProgressInfo,
    RemoteControlResponse,
    ReturnToHomeRequest,
    SchedulerDTO,
    SchedulerResponse,
    StreamTelemetryRequest,
    StreamTelemetryResponse,
    SubAssetTelemetry,
    TakeoffRequest,
    TakeoffResponse,
    TaskDTO,
    TaskResponse,
    TaskStatus,
    TaskType,
    WaypointDTO,
    WaypointTaskConfig,
)
from .remote_control.manual_control_session import ManualControlInputSession
from .zequent_client import ZequentClient

__all__ = [
    "__version__",
    "ZequentClient",
    "StreamHandle",
    "ManualControlInputSession",
    # core responses
    "ErrorInfo",
    "ProgressInfo",
    "RemoteControlResponse",
    "TakeoffResponse",
    "LiveDataResponse",
    "MissionResponse",
    "TaskResponse",
    "SchedulerResponse",
    # remote-control
    "TakeoffRequest",
    "GoToRequest",
    "ReturnToHomeRequest",
    "LookAtRequest",
    "ManualControlRequest",
    "ManualControlInput",
    "DockOperationRequest",
    # live-data
    "StreamTelemetryRequest",
    "StreamTelemetryResponse",
    "AssetTelemetry",
    "SubAssetTelemetry",
    "LiveDataStartLiveStreamRequest",
    "LiveDataStopLiveStreamRequest",
    "ChangeLensRequest",
    "ChangeZoomRequest",
    # mission-autonomy
    "MissionDTO",
    "TaskDTO",
    "SchedulerDTO",
    "WaypointDTO",
    "WaypointTaskConfig",
    "MissionStatus",
    "MissionType",
    "TaskStatus",
    "TaskType",
    # exceptions
    "ZequentClientError",
    "ZequentRetryExhaustedError",
]

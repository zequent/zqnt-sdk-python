"""
ZQNT Python Client SDK
======================

Python client for the Zequent Framework. Connects to:

  * zqnt.control.v3.RemoteControlService (any command by id: list_capabilities, execute_command)
  * RemoteControlService     (2.x typed flight, dock & asset ops; deprecated on 3.0)
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
           result = await client.commands.execute_command("DRONE-1", "flight.takeoff", {"altitude": 40})
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from .commands import CommandError, CommandsClient
from .exceptions import ZequentClientError, ZequentRetryExhaustedError
from .live_data.stream_handle import StreamHandle

try:
    __version__ = _pkg_version("zqnt-client-sdk")
except PackageNotFoundError:
    __version__ = "1.0.1"

from .models import (
    AssetSdrState,
    AssetTelemetry,
    AssetWirelessLinkInfo,
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
    "CommandsClient",
    "CommandError",
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
    "AssetWirelessLinkInfo",
    "AssetSdrState",
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

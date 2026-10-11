"""
ZQNT Python Client SDK
======================

Python client for the Zequent Framework. Connects to:

  * zqnt.control.v3.RemoteControlService (any command by id: list_capabilities, execute_command,
    stream_manual_control)
  * zqnt.telemetry.v3.TelemetryService (watch_telemetry, watch_detections, watch_alerts)
  * ConnectorService         (assets, organizations, skill registry, schedulers)
  * MissionAutonomyService   (Applications, Skill executions, schedulers)

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

from .commands import CommandError, CommandsClient, ManualControlStream
from .exceptions import ZequentClientError, ZequentRetryExhaustedError
from .stream_handle import StreamHandle
from .telemetry import TelemetryClient

try:
    __version__ = _pkg_version("zqnt-client-sdk")
except PackageNotFoundError:
    __version__ = "3.0.0"

from .models import (
    ErrorInfo,
    MissionDTO,
    MissionResponse,
    MissionStatus,
    MissionType,
    ProgressInfo,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
    TaskStatus,
    TaskType,
    WaypointDTO,
    WaypointTaskConfig,
)
from .zequent_client import ZequentClient

__all__ = [
    "__version__",
    "ZequentClient",
    "CommandsClient",
    "CommandError",
    "ManualControlStream",
    "TelemetryClient",
    "StreamHandle",
    "ErrorInfo",
    "ProgressInfo",
    "MissionResponse",
    "TaskResponse",
    "SchedulerResponse",
    "MissionDTO",
    "TaskDTO",
    "SchedulerDTO",
    "WaypointDTO",
    "WaypointTaskConfig",
    "MissionStatus",
    "MissionType",
    "TaskStatus",
    "TaskType",
    "ZequentClientError",
    "ZequentRetryExhaustedError",
]

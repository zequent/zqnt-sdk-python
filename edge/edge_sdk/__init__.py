"""
ZQNT Edge Python SDK
====================

Lets you implement a ZQNT Edge Adapter in plain Python – no protobuf
knowledge required.

Quick-start
-----------

1. Generate the gRPC stubs once (requires grpcio-tools)::

       pip install -e ".[dev]"
       bash scripts/generate_protos.sh

2. Subclass :class:`EdgeAdapter`, implement all abstract methods.

3. Start the server::

       server = EdgeServer(adapter=MyAdapter(), port=50051)
       asyncio.run(server.serve())

4. Optionally push telemetry to the platform::

       pub = TelemetryPublisher(host="platform", port=50052, sn="DOCK001")
       await pub.connect()
       await pub.publish_asset_telemetry(AssetTelemetry(id="DOCK001", ...))
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("edge-python-sdk")
except PackageNotFoundError:
    __version__ = "3.0.0"

from .adapter.base import EdgeAdapter
from .adapter.commands import CATALOG as COMMAND_CATALOG
from .adapter.commands import CommandSpec, RegisteredCommand, schema
from .auth import EdgeAuthConfig, PlatformTokenVerifier, TokenVerificationError, UnknownSigningKeyError
from .client.connector_client import ConnectorClient
from .client.edge_gateway import EdgeGatewayClient
from .client.live_data_service import LiveDataService
from .client.mission_autonomy_client import MissionAutonomyClient
from .client.telemetry_ingest import TelemetryIngestPublisher
from .client.telemetry_publisher import TelemetryPublisher
from .config import EdgeAdapterConfig, EdgeAdapterRuntime
from .internal_tls import InternalTls
from .models import (
    # task / mission
    AreaMappingTaskConfig,
    AreaVertex,
    # asset
    Asset,
    # telemetry
    AssetAirConditioner,
    # enums
    AssetAirConditionerState,
    AssetConnection,
    AssetCoverState,
    AssetMode,
    AssetNetworkInfo,
    AssetPositionState,
    # notification
    AssetStatusEvent,
    AssetSubAssetInfo,
    AssetTelemetry,
    AssetType,
    AssetVendor,
    # common dataclasses
    BoundingBox,
    CameraData,
    Capabilities,
    Capability,
    CapabilitySource,
    CapabilityState,
    CapabilityTarget,
    CapabilityTargetType,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    CommandExecutionEvent,
    CommandExecutionStatus,
    CommandProgress,
    CommandRisk,
    CommandSafety,
    CompletionMode,
    Coordinates,
    DetectionAttribute,
    DetectionParameter,
    DetectionPosition,
    DetectionResponse,
    DetectionResult,
    DetectTaskConfig,
    EdgeResponse,
    ErrorCode,
    ErrorMessage,
    FollowTaskConfig,
    LiveStreamStartRequest,
    LiveStreamStopRequest,
    LiveStreamType,
    ManualControlInput,
    ManualControlRequest,
    ManualControlState,
    Mission,
    MissionEvent,
    MissionStatus,
    MissionType,
    NetworkStateQuality,
    NetworkType,
    PayloadTelemetry,
    PoiTaskConfig,
    Rainfall,
    RangeFinderData,
    RequestContext,
    ReturnToHomeRequest,
    SchedulerDTO,
    SchedulerType,
    SensorData,
    SubAsset,
    SubAssetBatteryInfo,
    SubAssetMode,
    SubAssetTelemetry,
    Task,
    TaskStatus,
    TaskType,
    TrackTaskConfig,
    Waypoint,
    WaypointTaskConfig,
)
from .models.common import CustomCommandResponse, DetectionBatch, Payload, TelemetryField, TelemetryValueType
from .models.live import Alert, AlertSeverity, TelemetrySample
from .node import EdgeNodeConfig, LaneStats, NodeQueueClient, QueueStats
from .platform_keys import PlatformKeySet
from .server.edge_server import EdgeServer, RegistrationConfig

__all__ = [
    "EdgeGatewayClient",
    "TelemetryIngestPublisher",
    "Payload",
    "TelemetryField",
    "DetectionAttribute",
    "DetectionBatch",
    "CustomCommandResponse",
    "TelemetryValueType",
    "TelemetrySample",
    "Alert",
    "AlertSeverity",
    "__version__",
    # core
    "EdgeAdapter",
    "EdgeAdapterConfig",
    "EdgeAdapterRuntime",
    # local Edge Node attach (edge_sdk.node)
    "EdgeNodeConfig",
    "NodeQueueClient",
    "QueueStats",
    "LaneStats",
    # authentication (edge_sdk.auth)
    "EdgeAuthConfig",
    "PlatformTokenVerifier",
    "TokenVerificationError",
    "UnknownSigningKeyError",
    "PlatformKeySet",
    # internal TLS to the platform (edge_sdk.internal_tls)
    "InternalTls",
    "EdgeServer",
    "RegistrationConfig",
    "TelemetryPublisher",
    "ConnectorClient",
    "MissionAutonomyClient",
    "LiveDataService",
    # enums
    "AssetType",
    "AssetVendor",
    "AssetConnection",
    "LiveStreamType",
    "AssetMode",
    "SubAssetMode",
    "ManualControlState",
    "AssetCoverState",
    "AssetAirConditionerState",
    "TaskType",
    "TaskStatus",
    "MissionType",
    "MissionStatus",
    "ErrorCode",
    "CommandExecutionStatus",
    "SchedulerType",
    "Rainfall",
    "NetworkType",
    "NetworkStateQuality",
    # common
    "Coordinates",
    "RequestContext",
    "EdgeResponse",
    "ErrorMessage",
    "CommandProgress",
    "Capabilities",
    "COMMAND_CATALOG",
    "CommandSpec",
    "RegisteredCommand",
    "schema",
    "Capability",
    "CapabilitySource",
    "CommandRisk",
    "CommandSafety",
    "CompletionMode",
    "CapabilityState",
    "CapabilityTarget",
    "CapabilityTargetType",
    "ReturnToHomeRequest",
    "ManualControlRequest",
    "ManualControlInput",
    "LiveStreamStartRequest",
    "LiveStreamStopRequest",
    "ChangeCameraLensRequest",
    "ChangeCameraZoomRequest",
    "BoundingBox",
    "DetectionPosition",
    "DetectionResult",
    "DetectionResponse",
    # asset
    "Asset",
    "SubAsset",
    # notification
    "AssetStatusEvent",
    "MissionEvent",
    "CommandExecutionEvent",
    # scheduler
    "SchedulerDTO",
    # task
    "Task",
    "Mission",
    "Waypoint",
    "WaypointTaskConfig",
    "DetectTaskConfig",
    "DetectionParameter",
    "AreaMappingTaskConfig",
    "AreaVertex",
    "PoiTaskConfig",
    "FollowTaskConfig",
    "TrackTaskConfig",
    # telemetry
    "AssetTelemetry",
    "SubAssetTelemetry",
    "PayloadTelemetry",
    "CameraData",
    "RangeFinderData",
    "SensorData",
    "SubAssetBatteryInfo",
    "AssetNetworkInfo",
    "AssetAirConditioner",
    "AssetSubAssetInfo",
    "AssetPositionState",
]

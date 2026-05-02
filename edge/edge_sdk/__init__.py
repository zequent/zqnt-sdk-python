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
    __version__ = "1.0.0"

from .adapter.base import EdgeAdapter
from .client.connector_client import ConnectorClient
from .client.telemetry_publisher import TelemetryPublisher
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
    AssetSubAssetInfo,
    AssetTelemetry,
    AssetType,
    AssetVendor,
    # common dataclasses
    BoundingBox,
    CameraData,
    Capabilities,
    Capability,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    CommandProgress,
    Coordinates,
    DetectionParameter,
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
from .server.edge_server import EdgeServer, RegistrationConfig

__all__ = [
    "__version__",
    # core
    "EdgeAdapter",
    "EdgeServer",
    "RegistrationConfig",
    "TelemetryPublisher",
    "ConnectorClient",
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
    "Capability",
    "ReturnToHomeRequest",
    "ManualControlRequest",
    "ManualControlInput",
    "LiveStreamStartRequest",
    "LiveStreamStopRequest",
    "ChangeCameraLensRequest",
    "ChangeCameraZoomRequest",
    "BoundingBox",
    "DetectionResult",
    "DetectionResponse",
    # asset
    "Asset",
    "SubAsset",
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

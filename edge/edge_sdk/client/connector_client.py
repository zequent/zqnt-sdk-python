"""
ConnectorClient – thin wrapper around the ConnectorService gRPC stub.

Provides plain-Python methods so adapter code can query assets, missions,
and tasks without touching protobuf directly::

    client = ConnectorClient(host="platform.example.com", port=50053, sn="DOCK001")
    await client.connect()

    task = await client.get_task("task-uuid-here")
    mission = await client.get_mission("mission-uuid-here")

    await client.close()
"""

import logging
import uuid
from datetime import datetime, timezone

from ..models.asset import Asset
from ..models.task import Mission, Task

logger = logging.getLogger(__name__)


class ConnectorClient:
    """
    Client for the ZQNT ConnectorService.

    Args:
        host:  ConnectorService host.
        port:  ConnectorService port (default 50053).
        sn:    Serial number used as the base for requests.
    """

    def __init__(self, host: str, port: int = 50053, sn: str = "") -> None:
        self._host = host
        self._port = port
        self._sn = sn
        self._channel = None
        self._stub = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            import grpc.aio
            from ..generated import connector_pb2_grpc  # type: ignore[import]
        except ImportError as exc:
            raise ImportError("Protobuf stubs not found. Run  scripts/generate_protos.sh  first.") from exc

        self._channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
        self._stub = connector_pb2_grpc.ConnectorServiceStub(self._channel)
        logger.info("ConnectorClient connected to %s:%d", self._host, self._port)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()

    # ------------------------------------------------------------------
    # Asset
    # ------------------------------------------------------------------

    async def get_asset_by_sn(self) -> Asset | None:
        """Fetch the asset registered under this client's serial number."""
        from ..generated import connector_pb2  # type: ignore[import]
        from ..server._converters import proto_to_asset

        resp = await self._stub.GetAssetBySn(
            connector_pb2.ConnectorGetAssetBySnRequest(base=self._base()),
            wait_for_ready=True,
        )
        if resp.HasField("assetDTO"):
            return proto_to_asset(resp.assetDTO)
        return None

    async def register_asset(self, asset: Asset) -> str | None:
        """Register an asset on the platform. Returns the asset id."""
        from ..generated import connector_pb2, common_pb2  # type: ignore[import]
        from ..server._converters import asset_to_proto

        resp = await self._stub.RegisterAsset(
            connector_pb2.ConnectorRegisterAssetRequest(
                base=self._base(),
                assetDTO=asset_to_proto(asset, common_pb2),
            ),
            wait_for_ready=True,
        )
        return resp.id if resp.id else None

    # ------------------------------------------------------------------
    # Mission
    # ------------------------------------------------------------------

    async def get_mission(self, mission_id: str) -> Mission | None:
        """Fetch a mission by ID."""
        from ..generated import connector_pb2  # type: ignore[import]
        from ..server._converters import proto_to_mission

        resp = await self._stub.GetMission(
            connector_pb2.ConnectorGetMissionRequest(base=self._base(), missionId=mission_id),
            wait_for_ready=True,
        )
        if resp.HasField("missionDTO"):
            return proto_to_mission(resp.missionDTO)
        return None

    # ------------------------------------------------------------------
    # Task
    # ------------------------------------------------------------------

    async def get_task(self, task_id: str) -> Task | None:
        """Fetch a task by ID."""
        from ..generated import connector_pb2  # type: ignore[import]
        from ..server._converters import proto_to_task

        resp = await self._stub.GetTask(
            connector_pb2.ConnectorGetTaskRequest(base=self._base(), taskId=task_id),
            wait_for_ready=True,
        )
        if resp.HasField("taskDTO"):
            return proto_to_task(resp.taskDTO)
        return None

    async def get_task_by_flight_id(self, flight_id: str) -> Task | None:
        """Fetch a task by its flight ID (waypoint config flightId)."""
        from ..generated import connector_pb2  # type: ignore[import]
        from ..server._converters import proto_to_task

        resp = await self._stub.GetTaskByFlightId(
            connector_pb2.ConnectorGetTaskRequest(base=self._base(), taskId=flight_id),
            wait_for_ready=True,
        )
        if resp.HasField("taskDTO"):
            return proto_to_task(resp.taskDTO)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base(self):
        from ..generated import common_pb2  # type: ignore[import]
        from google.protobuf import timestamp_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=self._sn, timestamp=ts)

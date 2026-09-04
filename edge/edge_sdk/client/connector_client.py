"""
ConnectorClient – thin wrapper around the ConnectorService gRPC stub.

Provides plain-Python methods so adapter code can query assets, missions,
and tasks without touching protobuf directly::

    client = ConnectorClient(host="platform.example.com", port=50053)
    await client.connect()

    asset = await client.get_asset_by_sn("DOCK001")
    task  = await client.get_task("task-uuid-here", sn="DOCK001")

    await client.close()

Each method accepts the caller's ``sn`` explicitly so the same client
instance can serve multiple devices without any shared state.

All calls carry a per-call timeout (default 30 s) and retry automatically
on transient errors (UNAVAILABLE / DEADLINE_EXCEEDED) with exponential
backoff up to *max_retries* attempts.  Each request logs its transaction ID
(tid) so failures can be correlated in distributed traces.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable

from ..models.asset import Asset
from ..models.task import Mission, Task

logger = logging.getLogger(__name__)


class ConnectorClient:
    """
    Client for the ZQNT ConnectorService.

    A single instance can be shared across multiple adapter handler calls
    because the serial number is passed per-call rather than stored.

    Args:
        host:         ConnectorService host.
        port:         ConnectorService port (default 50053).
        call_timeout: Per-call deadline in seconds (default 30.0).
        max_retries:  Max retry attempts on transient gRPC errors (default 3).
    """

    _BACKOFF_INITIAL = 0.5
    _BACKOFF_MAX = 10.0

    def __init__(
        self,
        host: str,
        port: int = 50053,
        call_timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._host = host
        self._port = port
        self._call_timeout = call_timeout
        self._max_retries = max_retries
        self._channel = None
        self._stub = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the gRPC channel and initialise the stub."""
        import grpc.aio
        from zqnt_utils.generated.zqnt import connector_pb2_grpc

        self._channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
        self._stub = connector_pb2_grpc.ConnectorServiceStub(self._channel)
        logger.info("ConnectorClient connected to %s:%d", self._host, self._port)

    async def close(self) -> None:
        """Close the channel and release resources."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("ConnectorClient closed")

    # ------------------------------------------------------------------
    # Asset
    # ------------------------------------------------------------------

    async def get_asset_by_sn(self, sn: str) -> Asset | None:
        """Fetch the asset registered under *sn*."""
        from ..server._converters import proto_to_asset

        tid = str(uuid.uuid4())
        resp = await self._call(
            "GetAssetBySn",
            tid,
            sn,
            lambda: self._stub.GetAssetBySn(
                self._base(tid, sn),
                timeout=self._call_timeout,
            ),
        )
        if resp.WhichOneof("response") == "asset":
            return proto_to_asset(resp.asset)
        return None

    async def watch_assets(self) -> AsyncIterator[list[Asset]]:
        """
        Subscribe to the ConnectorService ``AssetMonitoring`` stream.

        Yields a list of :class:`Asset` objects on every snapshot the server
        pushes.  The stream runs until cancelled or the server closes it.
        Callers should run this inside a retry loop if they want reconnection.
        """
        from ..server._converters import proto_to_asset

        tid = str(uuid.uuid4())
        stream = self._stub.AssetMonitoring(self._base(tid))
        async for response in stream:
            if response.HasField("assets"):
                yield [proto_to_asset(a) for a in response.assets.assets]

    async def register_asset(self, asset: Asset) -> str | None:
        """Register an asset on the platform. Returns the asset id, or None on failure."""
        from zqnt_utils.generated.zqnt import common_pb2, connector_pb2

        from ..server._converters import asset_to_proto

        tid = str(uuid.uuid4())
        resp = await self._call(
            "RegisterAsset",
            tid,
            asset.sn,
            lambda: self._stub.RegisterAsset(
                connector_pb2.ConnectorRegisterAssetRequest(
                    base=self._base(tid, asset.sn),
                    asset=asset_to_proto(asset, common_pb2),
                ),
                timeout=self._call_timeout,
            ),
        )
        if resp.has_errors:
            logger.error(
                "RegisterAsset failed [tid=%s sn=%s]: %s",
                tid,
                asset.sn,
                resp.response_message,
            )
            return None
        return resp.id if resp.id else None

    # Mission/Task CRUD was retired from ConnectorService in favor of the capability-execution
    # model (Application/SkillExecution) — the underlying gRPC methods (GetMission, GetTask,
    # GetTaskByFlightId, ...) no longer exist, matching edge-java-sdk's MissionAutonomyService,
    # which dropped the equivalent methods outright rather than keeping stubs.

    # ------------------------------------------------------------------
    # Mission / Task — retired on main/2.0.0 in favor of the capability-execution model
    # (Application/SkillExecution), but still real RPCs at the 1.3.0 contract this branch
    # tracks; MissionProtoDTO/TaskProtoDTO themselves are unchanged between 1.3.0 and 2.0.0
    # (byte-identical), so the existing Mission/Task models and proto_to_mission/proto_to_task
    # converters in models/task.py + server/_converters.py are reused as-is here -- only the
    # request/response message names differ from what a naive "just re-add the old wrapper
    # calls" pass would guess (GetMissionRequest/MissionResponse, not a ConnectorXxx-prefixed
    # pair -- verified directly against zqnt-protos' own 1.3.0 tag, not assumed).
    # ------------------------------------------------------------------

    async def get_mission(self, mission_id: str, sn: str = "") -> Mission | None:
        """Fetch a mission by ID."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2

        from ..server._converters import proto_to_mission

        tid = str(uuid.uuid4())
        resp = await self._call(
            "GetMission",
            tid,
            sn,
            lambda: self._stub.GetMission(
                mission_autonomy_contracts_pb2.GetMissionRequest(base=self._base(tid, sn), mission_id=mission_id),
                timeout=self._call_timeout,
            ),
        )
        if resp.WhichOneof("response") == "mission":
            return proto_to_mission(resp.mission)
        return None

    async def get_task(self, task_id: str, sn: str = "") -> Task | None:
        """Fetch a task by ID."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2

        from ..server._converters import proto_to_task

        tid = str(uuid.uuid4())
        resp = await self._call(
            "GetTask",
            tid,
            sn,
            lambda: self._stub.GetTask(
                mission_autonomy_contracts_pb2.GetTaskRequest(base=self._base(tid, sn), task_id=task_id),
                timeout=self._call_timeout,
            ),
        )
        if resp.WhichOneof("response") == "task":
            return proto_to_task(resp.task)
        return None

    async def get_task_by_flight_id(self, flight_id: str, sn: str = "") -> Task | None:
        """Fetch a task by its flight ID (waypoint config flightId)."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2

        from ..server._converters import proto_to_task

        tid = str(uuid.uuid4())
        resp = await self._call(
            "GetTaskByFlightId",
            tid,
            sn,
            lambda: self._stub.GetTaskByFlightId(
                mission_autonomy_contracts_pb2.GetTaskByFlightIdRequest(base=self._base(tid, sn), flight_id=flight_id),
                timeout=self._call_timeout,
            ),
        )
        if resp.WhichOneof("response") == "task":
            return proto_to_task(resp.task)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if self._stub is None:
            raise RuntimeError("ConnectorClient not connected. Call connect() first.")

    async def _call(self, operation: str, tid: str, sn: str, fn: Callable) -> Any:
        """
        Execute a gRPC call with retry on transient errors.

        *fn* is a zero-argument callable that creates a new awaitable gRPC
        call on each invocation (typically a lambda wrapping the stub method).
        UNAVAILABLE and DEADLINE_EXCEEDED are retried with exponential backoff.
        All other errors propagate immediately.
        """
        import grpc
        import grpc.aio

        self._ensure_connected()
        backoff = self._BACKOFF_INITIAL
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.debug("%s [tid=%s sn=%s]", operation, tid, sn)
                result = await fn()
                return result
            except grpc.aio.AioRpcError as exc:
                retryable = exc.code() in (
                    grpc.StatusCode.UNAVAILABLE,
                    grpc.StatusCode.DEADLINE_EXCEEDED,
                )
                if retryable and attempt < self._max_retries:
                    logger.warning(
                        "%s transient error [tid=%s code=%s], retry %d/%d in %.1fs",
                        operation,
                        tid,
                        exc.code().name,
                        attempt,
                        self._max_retries - 1,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self._BACKOFF_MAX)
                else:
                    logger.error(
                        "%s failed [tid=%s sn=%s code=%s]: %s",
                        operation,
                        tid,
                        sn,
                        exc.code().name,
                        exc.details(),
                    )
                    raise

    def _base(self, tid: str | None = None, sn: str = ""):
        from google.protobuf import timestamp_pb2
        from zqnt_utils.generated.zqnt import common_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(
            tid=tid if tid is not None else str(uuid.uuid4()),
            sn=sn,
            timestamp=ts,
        )

"""
MissionAutonomyClient – thin wrapper around the MissionAutonomyService gRPC stub.

This branch tracks the 1.3.0 wire contract, where MissionAutonomyService's edge-facing surface
is just Scheduler lookup (Mission/Task CRUD, retired on main/2.0.0 in favor of the
capability-execution model, still exist as real RPCs on ConnectorService at 1.3.0 -- see
:class:`~edge_sdk.client.connector_client.ConnectorClient`'s get_mission/get_task methods for
those, unchanged from main's tiny-surface precedent for *this* service specifically::

    client = MissionAutonomyClient(host="platform.example.com", port=50054)
    await client.connect()

    scheduler = await client.get_scheduler("scheduler-uuid-here", sn="DOCK001")

    await client.close()

All calls carry a per-call timeout (default 30 s) and retry automatically on transient errors
(UNAVAILABLE / DEADLINE_EXCEEDED) with exponential backoff, same policy as
:class:`~edge_sdk.client.connector_client.ConnectorClient`.
"""

import asyncio
import logging
import uuid
from typing import Any, Callable

from ..models.scheduler import SchedulerDTO

logger = logging.getLogger(__name__)


class MissionAutonomyClient:
    """
    Client for the ZQNT MissionAutonomyService.

    Args:
        host:         MissionAutonomyService host.
        port:         MissionAutonomyService port (default 50054).
        call_timeout: Per-call deadline in seconds (default 30.0).
        max_retries:  Max retry attempts on transient gRPC errors (default 3).
    """

    _BACKOFF_INITIAL = 0.5
    _BACKOFF_MAX = 10.0

    def __init__(
        self,
        host: str,
        port: int = 50054,
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
        from zqnt_utils.generated.zqnt import mission_autonomy_pb2_grpc

        self._channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
        self._stub = mission_autonomy_pb2_grpc.MissionAutonomyServiceStub(self._channel)
        logger.info("MissionAutonomyClient connected to %s:%d", self._host, self._port)

    async def close(self) -> None:
        """Close the channel and release resources."""
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
            logger.info("MissionAutonomyClient closed")

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    async def get_scheduler(self, scheduler_id: str, sn: str = "") -> SchedulerDTO | None:
        """Fetch a scheduler by ID."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2

        tid = str(uuid.uuid4())
        resp = await self._call(
            "GetScheduler",
            tid,
            sn,
            lambda: self._stub.GetScheduler(
                mission_autonomy_contracts_pb2.GetSchedulerRequest(base=self._base(tid, sn), scheduler_id=scheduler_id),
                timeout=self._call_timeout,
            ),
        )
        if resp.WhichOneof("response") == "scheduler":
            return _proto_to_scheduler(resp.scheduler)
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if self._stub is None:
            raise RuntimeError("MissionAutonomyClient not connected. Call connect() first.")

    async def _call(self, operation: str, tid: str, sn: str, fn: Callable) -> Any:
        """Execute a gRPC call with retry on transient errors (UNAVAILABLE / DEADLINE_EXCEEDED)."""
        import grpc
        import grpc.aio

        self._ensure_connected()
        backoff = self._BACKOFF_INITIAL
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.debug("%s [tid=%s sn=%s]", operation, tid, sn)
                return await fn()
            except grpc.aio.AioRpcError as exc:
                retryable = exc.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED)
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
                        "%s failed [tid=%s sn=%s code=%s]: %s", operation, tid, sn, exc.code().name, exc.details()
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


def _proto_to_scheduler(s) -> SchedulerDTO:
    from ..models.common import SchedulerType
    from ..server._converters import _opt_field  # reuse the shared optional-field helper

    return SchedulerDTO(
        id=_opt_field(s, "id"),
        name=s.name,
        cron_expression=s.cron_expression,
        type=SchedulerType(s.type),
        mission_id=_opt_field(s, "mission_id"),
        task_id=_opt_field(s, "task_id"),
        active=_opt_field(s, "active"),
        client_time_zone=_opt_field(s, "client_time_zone"),
    )

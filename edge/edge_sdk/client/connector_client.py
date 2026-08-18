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
    # Skill Registry — the persisted, de-duplicated capability catalog (independent of which
    # devices are currently connected). Methods here work with the raw generated
    # ``SkillContractProtoDTO`` rather than a plain-Python model — the same scope decision
    # ``client-python-sdk``'s ``ConnectorClient`` makes for this RPC group: the contract shape
    # (input/output schema, errors, events, requirements, source) is large and already typed;
    # wrapping it a second time buys little for what is normally a write-once-per-command call.
    # ------------------------------------------------------------------

    async def observe_skill_contract(self, contract):
        """Upsert ``contract`` — new for a never-seen (command_id, schema_version) pair, or
        refreshed content/last-seen for one already known."""
        from zqnt_utils.generated.zqnt import connector_pb2

        tid = str(uuid.uuid4())
        resp = await self._call(
            "ObserveSkillContract",
            tid,
            "",
            lambda: self._stub.ObserveSkillContract(
                connector_pb2.UpsertSkillContractRequest(base=self._base(tid), contract=contract),
                timeout=self._call_timeout,
            ),
        )
        if resp.has_errors:
            logger.error("ObserveSkillContract failed [tid=%s]: %s", tid, resp.error.error_message)
            return None
        return resp.contract

    async def list_skill_contracts(self, status=None, command_id: str | None = None) -> list:
        """List the whole registry, optionally filtered by ``status`` (a ``SkillContractStatus``
        enum value). When ``command_id`` is set, returns that one command's full version history
        instead (``status`` is then ignored, matching the RPC's own semantics)."""
        from zqnt_utils.generated.zqnt import connector_pb2

        kwargs: dict = {"base": self._base()}
        if status is not None:
            kwargs["status"] = status
        if command_id:
            kwargs["command_id"] = command_id

        tid = str(uuid.uuid4())
        resp = await self._call(
            "ListSkillContracts",
            tid,
            "",
            lambda: self._stub.ListSkillContracts(
                connector_pb2.ListSkillContractsRequest(**kwargs),
                timeout=self._call_timeout,
            ),
        )
        if resp.has_errors:
            logger.error("ListSkillContracts failed [tid=%s]: %s", tid, resp.error.error_message)
            return []
        return list(resp.contracts)

    async def set_skill_contract_status(self, contract_id: str, status):
        """Set a skill contract's lifecycle status (a ``SkillContractStatus`` enum value)."""
        from zqnt_utils.generated.zqnt import connector_pb2

        tid = str(uuid.uuid4())
        resp = await self._call(
            "SetSkillContractStatus",
            tid,
            "",
            lambda: self._stub.SetSkillContractStatus(
                connector_pb2.SetSkillContractStatusRequest(base=self._base(tid), id=contract_id, status=status),
                timeout=self._call_timeout,
            ),
        )
        if resp.has_errors:
            logger.error("SetSkillContractStatus failed [tid=%s]: %s", tid, resp.error.error_message)
            return None
        return resp.contract

    async def set_skill_contract_permissions(self, contract_id: str, required_permissions: list[str]):
        """Full replacement, not a merge. Declarative only — nothing currently enforces this."""
        from zqnt_utils.generated.zqnt import connector_pb2

        tid = str(uuid.uuid4())
        resp = await self._call(
            "SetSkillContractPermissions",
            tid,
            "",
            lambda: self._stub.SetSkillContractPermissions(
                connector_pb2.SetSkillContractPermissionsRequest(
                    base=self._base(tid), id=contract_id, required_permissions=list(required_permissions)
                ),
                timeout=self._call_timeout,
            ),
        )
        if resp.has_errors:
            logger.error("SetSkillContractPermissions failed [tid=%s]: %s", tid, resp.error.error_message)
            return None
        return resp.contract

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

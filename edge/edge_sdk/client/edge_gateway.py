"""
The adapter's calls into the platform over v3 ``zqnt.edge.v3.EdgeGatewayService`` (remote-control):
command events and capability reports, each with a v2 fallback for an older core.

An older core answers UNIMPLEMENTED; the client then uses the v2 path and does not try v3 again
for :attr:`V3Fallback.WINDOW_SECONDS` (per process, per service).
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

import grpc
from google.protobuf import struct_pb2, timestamp_pb2

from ..auth import default_edge_token, platform_channel
from ..models.common import Capabilities, CommandExecutionStatus
from ..models.notification import CommandExecutionEvent

logger = logging.getLogger(__name__)


class V3Fallback:
    """Remembers per process that a core service does not serve its v3 API yet."""

    WINDOW_SECONDS = 600.0
    _unavailable_until: dict[str, float] = {}

    def __init__(self, service: str, clock=time.monotonic) -> None:
        self._service = service
        self._clock = clock

    def available(self) -> bool:
        return self._clock() >= V3Fallback._unavailable_until.get(self._service, 0.0)

    def mark_unavailable(self) -> None:
        V3Fallback._unavailable_until[self._service] = self._clock() + self.WINDOW_SECONDS
        logger.info("%s has no v3 API; using v2 for %.0f s", self._service, self.WINDOW_SECONDS)

    @classmethod
    def reset(cls) -> None:
        cls._unavailable_until.clear()


def is_unimplemented(exc: BaseException) -> bool:
    return isinstance(exc, grpc.aio.AioRpcError) and exc.code() == grpc.StatusCode.UNIMPLEMENTED


@dataclass(frozen=True)
class _Run:
    command_execution_id: str
    command_id: str
    sn: str


class CommandRuns:
    """
    The platform's command_execution_id for each external_execution_id an adapter accepted a v3
    command under, so an event the adapter publishes under its own id reaches the waiting node.
    """

    MAX_ENTRIES = 10_000
    _runs: OrderedDict[str, _Run] = OrderedDict()

    @classmethod
    def remember(cls, external_execution_id: str, command_execution_id: str, command_id: str, sn: str) -> None:
        if not external_execution_id or not command_execution_id:
            return
        cls._runs[external_execution_id] = _Run(command_execution_id, command_id, sn)
        cls._runs.move_to_end(external_execution_id)
        while len(cls._runs) > cls.MAX_ENTRIES:
            cls._runs.popitem(last=False)

    @classmethod
    def lookup(cls, external_execution_id: str) -> _Run | None:
        return cls._runs.get(external_execution_id)

    @classmethod
    def clear(cls) -> None:
        cls._runs.clear()


_STATES = {
    CommandExecutionStatus.ACCEPTED: 1,
    CommandExecutionStatus.RUNNING: 2,
    CommandExecutionStatus.SUCCEEDED: 3,
    CommandExecutionStatus.FAILED: 4,
    CommandExecutionStatus.CANCELLED: 6,
}


def command_event(event: CommandExecutionEvent):
    """
    The adapter's event as a v3 CommandEvent. ``occurred_at`` is always set (now() when the adapter
    gave none) -- the platform refuses an event without it.
    """
    from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
    from zqnt_utils.generated.zqnt.common.v3 import common_pb2

    run = CommandRuns.lookup(event.external_execution_id) if not event.command_execution_id else None
    command_execution_id = event.command_execution_id or (run.command_execution_id if run else None)
    proto = command_pb2.CommandEvent(
        command_execution_id=command_execution_id or event.external_execution_id,
        command_id=event.command_id or (run.command_id if run else ""),
        asset=common_pb2.AssetRef(sn=event.sn or (run.sn if run else "")),
        state=_STATES.get(CommandExecutionStatus(int(event.status)), 0),
        message=event.message or "",
    )
    occurred_at = timestamp_pb2.Timestamp()
    if event.occurred_at is not None:
        occurred_at.FromDatetime(event.occurred_at)
    else:
        occurred_at.GetCurrentTime()
    proto.occurred_at.CopyFrom(occurred_at)
    if event.progress is not None and not math.isnan(event.progress):
        proto.progress = event.progress
    if event.output:
        result = struct_pb2.Struct()
        result.update(event.output)
        proto.result.CopyFrom(result)
    if event.status == CommandExecutionStatus.FAILED:
        proto.error.CopyFrom(
            common_pb2.Error(
                category=common_pb2.ERROR_CATEGORY_ASSET,
                message=event.message or "command failed",
                occurred_at=occurred_at,
            )
        )
    return proto


class EdgeGatewayClient:
    """
    Command events and capability reports into the platform (remote-control's gRPC port).

    ``publish_command_event`` returns False instead of sending when v3 is not served, so the caller
    keeps its v2 path (``NotificationPublisher`` does that on its own). ``report_capabilities`` falls
    back to v2 ``RemoteControlService.ReportAssetRuntime`` itself.
    """

    def __init__(
        self,
        host: str,
        port: int = 8002,
        token: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._token = token if token is not None else default_edge_token()
        self._timeout = timeout
        self._channel: grpc.aio.Channel | None = None
        self._events_v3 = V3Fallback(f"{host}:{port}/EdgeGatewayService.PublishCommandEvent")
        self._capabilities_v3 = V3Fallback(f"{host}:{port}/EdgeGatewayService.ReportCapabilities")

    def _open(self) -> grpc.aio.Channel:
        if self._channel is None:
            self._channel = platform_channel(self._host, self._port, self._token)
        return self._channel

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def publish_command_event(self, event: CommandExecutionEvent) -> bool:
        """Send *event* over v3. False when v3 is not served (the caller uses v2); errors propagate."""
        if not self._events_v3.available():
            return False
        from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
        from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc

        stub = edge_v3_grpc.EdgeGatewayServiceStub(self._open())
        try:
            await stub.PublishCommandEvent(
                edge_v3.PublishCommandEventRequest(event=command_event(event)), timeout=self._timeout
            )
        except grpc.aio.AioRpcError as exc:
            if is_unimplemented(exc):
                self._events_v3.mark_unavailable()
                return False
            raise
        return True

    async def report_capabilities(self, caps: Capabilities) -> str:
        """Report *caps* (v3, else v2 ReportAssetRuntime). Returns the revision the platform stored."""
        if self._capabilities_v3.available():
            from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
            from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc

            from ..server.edge_server_v3 import capability_set

            stub = edge_v3_grpc.EdgeGatewayServiceStub(self._open())
            try:
                response = await stub.ReportCapabilities(
                    edge_v3.ReportCapabilitiesRequest(capabilities=capability_set(caps)), timeout=self._timeout
                )
                return response.accepted_revision
            except grpc.aio.AioRpcError as exc:
                if not is_unimplemented(exc):
                    raise
                self._capabilities_v3.mark_unavailable()
        return await self._report_asset_runtime(caps)

    async def _report_asset_runtime(self, caps: Capabilities) -> str:
        from zqnt_utils.generated.zqnt import common_pb2, device_control_contracts_pb2, remote_control_pb2_grpc

        from ..server._converters import capabilities_to_proto

        now = timestamp_pb2.Timestamp()
        now.GetCurrentTime()
        observed_at = timestamp_pb2.Timestamp()
        if caps.timestamp is not None:
            observed_at.FromDatetime(caps.timestamp)
        else:
            observed_at.CopyFrom(now)
        request = device_control_contracts_pb2.ReportAssetRuntimeRequest(
            base=common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=caps.asset_sn, timestamp=now),
            asset_sn=caps.asset_sn,
            observed_at=observed_at,
            capabilities=capabilities_to_proto(caps, common_pb2, timestamp_pb2).capabilities,
        )
        stub = remote_control_pb2_grpc.RemoteControlServiceStub(self._open())
        response = await stub.ReportAssetRuntime(request, timeout=self._timeout)
        if response.has_errors:
            raise RuntimeError(f"ReportAssetRuntime refused: {response.error.error_message}")
        return response.accepted_revision

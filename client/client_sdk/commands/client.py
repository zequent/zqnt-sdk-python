"""Commands any asset by id over ``zqnt.control.v3.RemoteControlService``.

Discover what an asset can do with :meth:`CommandsClient.list_capabilities`, run it with
:meth:`CommandsClient.execute_command`. Command ids are dotted (``flight.takeoff``,
``navigation.go_to``, ``dock.open_cover``) and params are a JSON object matching the capability's
input schema.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta
from typing import Any

import grpc
import grpc.aio
from google.protobuf import duration_pb2, struct_pb2
from google.protobuf.json_format import MessageToDict
from zqnt_utils.generated.zqnt.capability.v3 import capability_pb2, command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.control.v3 import remote_control_service_pb2 as control_pb2
from zqnt_utils.generated.zqnt.control.v3 import remote_control_service_pb2_grpc as control_pb2_grpc

from ..config.resilience import ResilienceConfig
from ..grpc_.resilience import GrpcResilience
from .errors import CommandError

logger = logging.getLogger(__name__)


def to_struct(params: Mapping[str, Any] | None) -> struct_pb2.Struct:
    """``params`` as a Struct; a top-level ``None`` value is left out."""
    struct = struct_pb2.Struct()
    if params:
        struct.update({key: value for key, value in params.items() if value is not None})
    return struct


def to_dict(struct: struct_pb2.Struct) -> dict[str, Any]:
    """A command result or event payload as a plain dict (numbers come back as ``float``)."""
    return MessageToDict(struct)


class CommandsClient:
    """Async client for the v3 command API. Every call raises :class:`CommandError` when the
    platform refuses it or the command is ``REJECTED``. :meth:`execute_command` returns the reply as
    it is, so a command that started and then failed is returned with state ``COMMAND_STATE_FAILED``
    and its error on the result; :meth:`execute_and_wait` returns only a ``SUCCEEDED`` result."""

    def __init__(self, channel: grpc.aio.Channel, resilience: ResilienceConfig) -> None:
        self._stub = control_pb2_grpc.RemoteControlServiceStub(channel)
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    async def list_capabilities(self, asset_sn: str) -> capability_pb2.CapabilitySet:
        """The asset's current capability snapshot: every command id it accepts, with schemas and risk."""
        _require("asset_sn", asset_sn)
        request = control_pb2.GetCapabilitiesRequest(
            context=_context(str(uuid.uuid4())),
            asset=common_pb2.AssetRef(sn=asset_sn),
        )
        response = await self._unary(lambda: self._stub.GetCapabilities(request, timeout=self._timeout))
        return response.capabilities

    async def execute_command(
        self,
        asset_sn: str | None,
        command_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        asset_id: str | None = None,
        target: capability_pb2.Target | None = None,
        timeout: timedelta | float | None = None,
        reason: str | None = None,
        no_fly_zone_override: bool = False,
        idempotency_key: str | None = None,
    ) -> command_pb2.CommandResult:
        """Run ``command_id`` on the asset named by ``asset_sn`` (or ``asset_id``).

        A ``None`` value in ``params`` is left out: leave a parameter out rather than sending 0 for
        "not given". ``timeout`` (seconds or a ``timedelta``) unset is the capability's own default;
        ``reason`` is required for CRITICAL commands; ``idempotency_key`` unset is a fresh key per
        call, kept across the SDK's own retries.
        """
        _require("command_id", command_id)
        if not (asset_sn and asset_sn.strip()) and not (asset_id and asset_id.strip()):
            raise ValueError("asset_sn or asset_id is required")
        command = command_pb2.Command(
            asset=common_pb2.AssetRef(sn=asset_sn or "", id=asset_id or ""),
            command_id=command_id,
            params=to_struct(params),
        )
        if target is not None:
            command.target.CopyFrom(target)
        if timeout is not None:
            command.timeout.CopyFrom(_duration(timeout))
        request = control_pb2.ExecuteCommandRequest(
            context=_context(idempotency_key or str(uuid.uuid4())),
            command=command,
            reason=reason or "",
            no_fly_zone_override=no_fly_zone_override,
        )
        logger.info("ExecuteCommand: asset=%s, command=%s", asset_sn or asset_id, command_id)
        response = await self._unary(lambda: self._stub.ExecuteCommand(request, timeout=self._timeout))
        return _accepted(response.result)

    async def execute_and_wait(
        self,
        asset_sn: str,
        command_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        target: capability_pb2.Target | None = None,
        timeout: timedelta | float | None = None,
        reason: str | None = None,
        no_fly_zone_override: bool = False,
        idempotency_key: str | None = None,
    ) -> command_pb2.CommandResult:
        """Run ``command_id`` on the asset and wait for its outcome.

        The asset's command events are watched before the command is sent, so a run that finishes
        right away is not missed; events of other runs are ignored. Returns the ``SUCCEEDED`` result
        and raises :class:`CommandError` carrying the final result when the run is ``REJECTED``,
        ``FAILED``, ``CANCELLED`` or ``TIMED_OUT``. ``timeout`` is the command's own timeout, as in
        :meth:`execute_command`; bound the wait with ``asyncio.timeout``. Leaving the call early
        (timeout, cancellation) closes the watch and leaves the command running on the platform
        (:meth:`cancel_command` stops it).
        """
        _require("asset_sn", asset_sn)
        _require("command_id", command_id)
        call = self._stub.WatchCommandEvents(
            control_pb2.WatchCommandEventsRequest(asset=common_pb2.AssetRef(sn=asset_sn))
        )
        try:
            try:
                await call.wait_for_connection()
            except grpc.aio.AioRpcError as exc:
                raise CommandError.from_exception(exc) from exc
            result = await self.execute_command(
                asset_sn,
                command_id,
                params,
                target=target,
                timeout=timeout,
                reason=reason,
                no_fly_zone_override=no_fly_zone_override,
                idempotency_key=idempotency_key,
            )
            if result.state not in _FINAL_STATES:
                result = await _final_result(call, result.command_execution_id, command_id)
            if result.state != command_pb2.COMMAND_STATE_SUCCEEDED:
                raise CommandError.of(result)
            return result
        finally:
            call.cancel()

    async def cancel_command(self, command_execution_id: str, reason: str | None = None) -> command_pb2.CommandResult:
        _require("command_execution_id", command_execution_id)
        request = control_pb2.CancelCommandRequest(
            context=_context(str(uuid.uuid4())),
            command_execution_id=command_execution_id,
            reason=reason or "",
        )
        response = await self._unary(lambda: self._stub.CancelCommand(request, timeout=self._timeout))
        return _accepted(response.result)

    def watch_command(self, command_execution_id: str) -> AsyncIterator[command_pb2.CommandEvent]:
        """Events of one command run from now on, ending after its terminal event. A run that
        finishes before the watch starts is missed; :meth:`execute_and_wait` waits for a run's
        outcome."""
        _require("command_execution_id", command_execution_id)
        return self._watch(control_pb2.WatchCommandEventsRequest(command_execution_id=command_execution_id))

    def watch_asset(self, asset_sn: str) -> AsyncIterator[command_pb2.CommandEvent]:
        """Events of every command on the asset from now on, until the loop is left."""
        _require("asset_sn", asset_sn)
        return self._watch(control_pb2.WatchCommandEventsRequest(asset=common_pb2.AssetRef(sn=asset_sn)))

    async def _watch(self, request: control_pb2.WatchCommandEventsRequest) -> AsyncIterator[command_pb2.CommandEvent]:
        call = self._stub.WatchCommandEvents(request)
        try:
            async for response in call:
                yield response.event
        except grpc.aio.AioRpcError as exc:
            raise CommandError.from_exception(exc) from exc
        finally:
            call.cancel()

    async def _unary(self, op):
        try:
            return await self._resilience_helper.execute(op)
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError.from_exception(exc) from exc


_FINAL_STATES = frozenset(
    {
        command_pb2.COMMAND_STATE_SUCCEEDED,
        command_pb2.COMMAND_STATE_FAILED,
        command_pb2.COMMAND_STATE_REJECTED,
        command_pb2.COMMAND_STATE_CANCELLED,
        command_pb2.COMMAND_STATE_TIMED_OUT,
    }
)


async def _final_result(call, command_execution_id: str, command_id: str) -> command_pb2.CommandResult:
    try:
        async for response in call:
            event = response.event
            if event.command_execution_id == command_execution_id and event.state in _FINAL_STATES:
                return command_pb2.CommandResult(
                    command_execution_id=event.command_execution_id,
                    command_id=event.command_id or command_id,
                    state=event.state,
                    result=event.result,
                    error=event.error,
                )
    except grpc.aio.AioRpcError as exc:
        raise CommandError.from_exception(exc) from exc
    raise CommandError(
        f"the event watch ended before {command_id} ({command_execution_id}) finished",
        category=common_pb2.ERROR_CATEGORY_SERVICE,
        retryable=True,
    )


def _accepted(result: command_pb2.CommandResult) -> command_pb2.CommandResult:
    if result.state == command_pb2.COMMAND_STATE_REJECTED:
        raise CommandError.rejected(result)
    return result


def _context(idempotency_key: str) -> common_pb2.RequestContext:
    return common_pb2.RequestContext(request_id=str(uuid.uuid4()), idempotency_key=idempotency_key)


def _duration(timeout: timedelta | float) -> duration_pb2.Duration:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(timeout if isinstance(timeout, timedelta) else timedelta(seconds=timeout))
    return duration


def _require(name: str, value: str | None) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")

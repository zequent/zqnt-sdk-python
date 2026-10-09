"""
The v3 edge contract (``zqnt.edge.v3.EdgeAdapterService``), served next to v2 on the same port.

v3 has no per-command RPCs: every command arrives as ``ExecuteCommand`` with a dotted command id
and runs through the same dispatch an adapter already has for ``send_custom_command`` -- handlers
registered with :meth:`EdgeAdapter.register_command` first, then built-in ids routed onto the typed
methods an older adapter overrides. An adapter therefore serves v2 and v3 from one set of
declarations and needs no change to answer v3 calls.

Params are checked against the command's input schema before the handler runs (invalid:
``REJECTED`` with ``command.invalid_params``). The handler sees the platform's id of the run as
``ctx.command_execution_id``.

Long-running commands: when the adapter returns an ``external_execution_id`` the command is
reported ``ACCEPTED`` and that id is handed back in ``result.external_execution_id``. Events the
adapter then publishes under that id go to ``EdgeGatewayService.PublishCommandEvent`` with the
platform's id (see :mod:`edge_sdk.client.edge_gateway`).
"""

import logging
from collections.abc import AsyncIterator

import grpc
from google.protobuf import struct_pb2, timestamp_pb2
from zqnt_utils.generated.zqnt.capability.v3 import capability_pb2, command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc

from ..adapter.base import EdgeAdapter
from ..client.edge_gateway import CommandRuns
from ..client.telemetry_ingest import detection_to_v3
from ..models.common import (
    INVALID_PARAMS_CODE,
    Capabilities,
    CompletionMode,
    CustomCommandRequest,
    CustomCommandResponse,
    ErrorCode,
    ManualControlInput,
    RequestContext,
)

logger = logging.getLogger(__name__)

NOT_SUPPORTED_CODE = "command.not_supported"

# The SDK's error codes, as v3 error categories.
_CATEGORY = {
    ErrorCode.CLIENT_ERROR: common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
    ErrorCode.SDK_ERROR: common_pb2.ERROR_CATEGORY_SERVICE,
    ErrorCode.SERVICE_ERROR: common_pb2.ERROR_CATEGORY_SERVICE,
    ErrorCode.ASSET_ERROR: common_pb2.ERROR_CATEGORY_ASSET,
    ErrorCode.SYSTEM_ERROR: common_pb2.ERROR_CATEGORY_SERVICE,
}


def _now() -> timestamp_pb2.Timestamp:
    ts = timestamp_pb2.Timestamp()
    ts.GetCurrentTime()
    return ts


def _struct(value: dict | None) -> struct_pb2.Struct | None:
    if not value:
        return None
    s = struct_pb2.Struct()
    s.update(value)
    return s


def _context(request_context, asset, command_execution_id: str | None = None) -> RequestContext:
    from datetime import datetime, timezone

    return RequestContext(
        tid=request_context.request_id,
        sn=asset.sn,
        timestamp=datetime.now(tz=timezone.utc),
        command_execution_id=command_execution_id or None,
    )


def _python(value):
    """A Struct value as plain Python, keeping NaN a float (json_format would turn it into "NaN")."""
    if isinstance(value, struct_pb2.Struct):
        return {k: _python(v) for k, v in value.items()}
    if isinstance(value, struct_pb2.ListValue):
        return [_python(v) for v in value]
    return value


def _is_not_supported(response: CustomCommandResponse) -> bool:
    # CustomCommandResponse.not_supported() is the one SDK_ERROR the dispatch itself produces.
    return (
        not response.success
        and response.error is not None
        and response.error.code == ErrorCode.SDK_ERROR
        and "not supported" in (response.error.message or "")
    )


def command_result(
    command_id: str,
    command_execution_id: str,
    response: CustomCommandResponse,
    completion: CompletionMode = CompletionMode.UNSPECIFIED,
):
    """
    The SDK's command response as a v3 CommandResult.

    A success is ACCEPTED -- the outcome follows as a command event -- when the adapter returned
    its own ``external_execution_id`` or when the command's capability declares ``ASYNCHRONOUS``;
    otherwise SUCCEEDED. Without the declaration a take-off that answered a plain success counted as
    done while the aircraft was still climbing.
    """
    if response.success:
        result = dict(response.result or {})
        if response.external_execution_id:
            result["external_execution_id"] = response.external_execution_id
        waits = bool(response.external_execution_id) or completion is CompletionMode.ASYNCHRONOUS
        state = command_pb2.COMMAND_STATE_ACCEPTED if waits else command_pb2.COMMAND_STATE_SUCCEEDED
        return command_pb2.CommandResult(
            command_execution_id=command_execution_id,
            command_id=command_id,
            state=state,
            result=_struct(result),
        )
    if response.error is not None and response.error.reason == INVALID_PARAMS_CODE:
        return command_pb2.CommandResult(
            command_execution_id=command_execution_id,
            command_id=command_id,
            state=command_pb2.COMMAND_STATE_REJECTED,
            error=common_pb2.Error(
                category=common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
                code=INVALID_PARAMS_CODE,
                message=response.error.message,
                occurred_at=_now(),
            ),
        )
    if _is_not_supported(response):
        return command_pb2.CommandResult(
            command_execution_id=command_execution_id,
            command_id=command_id,
            state=command_pb2.COMMAND_STATE_REJECTED,
            error=common_pb2.Error(
                category=common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
                code=NOT_SUPPORTED_CODE,
                message=f"{command_id} is not supported by this adapter",
                occurred_at=_now(),
            ),
        )
    error = response.error
    return command_pb2.CommandResult(
        command_execution_id=command_execution_id,
        command_id=command_id,
        state=command_pb2.COMMAND_STATE_FAILED,
        error=common_pb2.Error(
            category=_CATEGORY.get(error.code, common_pb2.ERROR_CATEGORY_ASSET)
            if error
            else common_pb2.ERROR_CATEGORY_ASSET,
            code=(error.reason if error else None) or "",
            message=(error.message if error else None) or response.message or f"{command_id} failed",
            occurred_at=_now(),
        ),
    )


def capability_set(caps: Capabilities) -> capability_pb2.CapabilitySet:
    """The SDK's capability snapshot as a v3 CapabilitySet."""
    proto = []
    for c in caps.capabilities:
        kwargs: dict = {
            "command_id": c.command_id,
            "display_name": c.display_name or c.command_id,
            "description": c.description,
            "state": int(c.state),
            "unavailable_reason": c.unavailable_reason or "",
            "schema_version": c.schema_version or "",
            "skill_id": c.skill_id or "",
            "source": int(c.source),
            "provider": c.provider or "",
            "metadata": dict(c.metadata),
        }
        for key, value in (("input_schema", c.input_schema), ("output_schema", c.output_schema)):
            s = _struct(value)
            if s is not None:
                kwargs[key] = s
        if c.target is not None:
            kwargs["target"] = capability_pb2.Target(type=int(c.target.type), ref=c.target.target_ref or "")
        if c.completion is not CompletionMode.UNSPECIFIED:
            kwargs["completion"] = int(c.completion)
        if c.completion_event:
            kwargs["completion_event"] = c.completion_event
        proto.append(capability_pb2.Capability(**kwargs))
    snapshot = capability_pb2.CapabilitySet(
        asset_sn=caps.asset_sn,
        asset_type=getattr(caps.asset_type, "name", str(caps.asset_type)),
        capabilities=proto,
        snapshot_state=capability_pb2.SNAPSHOT_STATE_CURRENT,
        telemetry_fields=[
            capability_pb2.TelemetryField(
                key=f.key,
                type=int(f.type),
                unit=f.unit,
                description=f.description,
                allowed_values=list(f.allowed_values),
            )
            for f in caps.telemetry_fields
        ],
    )
    if caps.timestamp is not None:
        snapshot.observed_at.FromDatetime(caps.timestamp)
    else:
        snapshot.observed_at.CopyFrom(_now())
    return snapshot


class EdgeAdapterV3Servicer(edge_v3_grpc.EdgeAdapterServiceServicer):
    """``zqnt.edge.v3.EdgeAdapterService`` on top of the same EdgeAdapter the v2 servicer uses."""

    def __init__(self, adapter: EdgeAdapter) -> None:
        self._adapter = adapter

    async def _completion(self, sn: str, command_id: str, response: CustomCommandResponse) -> CompletionMode:
        """
        The command's declared completion mode, looked up only when it decides something: a
        success that did not bring its own execution id. Never fails the command.
        """
        if not response.success or response.external_execution_id:
            return CompletionMode.UNSPECIFIED
        try:
            capability = (await self._adapter.advertised_capabilities(sn)).get(command_id)
        except Exception:
            logger.debug("capabilities of %s unreadable; completion left to the response", sn, exc_info=True)
            return CompletionMode.UNSPECIFIED
        return capability.completion if capability is not None else CompletionMode.UNSPECIFIED

    async def GetCapabilities(self, request, context):
        try:
            caps = await self._adapter.get_capabilities(sn=request.asset.sn, asset_id=request.asset.id or None)
        except Exception as exc:
            logger.exception("v3 GetCapabilities error [sn=%s]", request.asset.sn)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))
        return edge_v3.GetCapabilitiesResponse(capabilities=capability_set(caps))

    async def ExecuteCommand(self, request, context):
        command = request.command
        ctx = _context(request.context, command.asset, request.command_execution_id)
        params = _python(command.params) if command.HasField("params") else {}
        try:
            response = await self._adapter.execute_command(
                ctx, CustomCommandRequest(command_type=command.command_id, params=params)
            )
        except Exception as exc:
            logger.exception("v3 ExecuteCommand error [sn=%s command=%s]", ctx.sn, command.command_id)
            response = CustomCommandResponse.fail(ctx.tid, ctx.sn, command.command_id, _asset_error(str(exc)))
        if response.success and response.external_execution_id:
            CommandRuns.remember(
                response.external_execution_id, request.command_execution_id, command.command_id, ctx.sn
            )
        completion = await self._completion(ctx.sn, command.command_id, response)
        return edge_v3.ExecuteCommandResponse(
            result=command_result(command.command_id, request.command_execution_id, response, completion)
        )

    async def CancelCommand(self, request, context):
        ctx = _context(request.context, common_pb2.AssetRef())
        try:
            response = await self._adapter.cancel_command(ctx, request.command_execution_id, request.reason)
        except Exception as exc:
            logger.exception("v3 CancelCommand error [%s]", request.command_execution_id)
            response = CustomCommandResponse.fail(ctx.tid, ctx.sn, "", _asset_error(str(exc)))
        result = command_result(response.command_type, request.command_execution_id, response)
        if result.state in (command_pb2.COMMAND_STATE_SUCCEEDED, command_pb2.COMMAND_STATE_ACCEPTED):
            result.state = command_pb2.COMMAND_STATE_CANCELLED
        return edge_v3.CancelCommandResponse(result=result)

    async def StreamManualControl(self, request_iterator, context):
        try:
            first = await request_iterator.__anext__()
        except StopAsyncIteration:
            return edge_v3.StreamManualControlResponse()
        ctx = _context(common_pb2.RequestContext(), first.asset)
        accepted = 0

        async def inputs() -> AsyncIterator[ManualControlInput]:
            nonlocal accepted
            accepted += 1
            yield _manual_input(first.input)
            async for req in request_iterator:
                accepted += 1
                yield _manual_input(req.input)

        result = await self._adapter.manual_control_input(ctx, inputs())
        response = edge_v3.StreamManualControlResponse(accepted_inputs=accepted)
        if not result.success and result.error is not None:
            response.error.CopyFrom(
                common_pb2.Error(
                    category=common_pb2.ERROR_CATEGORY_ASSET, message=result.error.message, occurred_at=_now()
                )
            )
        return response

    async def StreamDetections(self, request, context):
        ctx = _context(common_pb2.RequestContext(), request.asset)
        try:
            async for batch in self._adapter.get_detections(ctx, request.stream_url or None):
                detections = [detection_to_v3(d) for d in batch.detections]
                yield edge_v3.StreamDetectionsResponse(
                    asset=request.asset, detections=detections, stream_url=request.stream_url, observed_at=_now()
                )
        except NotImplementedError:
            await context.abort(grpc.StatusCode.UNIMPLEMENTED, "StreamDetections is not supported by this adapter")


def _manual_input(proto) -> ManualControlInput:
    return ManualControlInput(
        roll=proto.roll,
        pitch=proto.pitch,
        yaw=proto.yaw,
        throttle=proto.throttle,
        gimbal_pitch=proto.gimbal_pitch if proto.HasField("gimbal_pitch") else None,
    )


def _asset_error(message: str):
    from ..models.common import ErrorMessage

    return ErrorMessage(message=message, code=ErrorCode.ASSET_ERROR)


def add_to_server(adapter: EdgeAdapter, server) -> None:
    edge_v3_grpc.add_EdgeAdapterServiceServicer_to_server(EdgeAdapterV3Servicer(adapter), server)

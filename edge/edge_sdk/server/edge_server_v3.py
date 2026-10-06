"""
The v3 edge contract (``zqnt.edge.v3.EdgeAdapterService``), served next to v2 on the same port.

v3 has no per-command RPCs: every command arrives as ``ExecuteCommand`` with a dotted command id
and runs through the same dispatch an adapter already has for ``send_custom_command`` -- handlers
registered with :meth:`EdgeAdapter.register_command` first, then built-in ids routed onto the typed
methods an older adapter overrides. An adapter therefore serves v2 and v3 from one set of
declarations and needs no change to answer v3 calls.

Long-running commands: when the adapter returns an ``external_execution_id`` the command is
reported ``ACCEPTED`` and that id is handed back in ``result.external_execution_id``; completion
still arrives as the adapter's v2 ``CommandExecutionEvent`` until the platform serves
``zqnt.edge.v3.EdgeGatewayService`` (zqnt-core#147).
"""

import logging
import time
from collections.abc import AsyncIterator

import grpc
from google.protobuf import json_format, struct_pb2, timestamp_pb2
from zqnt_utils.generated.zqnt.capability.v3 import capability_pb2, command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc

from ..adapter.base import EdgeAdapter
from ..models.common import (
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


def _context(request_context, asset) -> RequestContext:
    from datetime import datetime, timezone

    return RequestContext(tid=request_context.request_id, sn=asset.sn, timestamp=datetime.now(tz=timezone.utc))


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
    )
    if caps.timestamp is not None:
        snapshot.observed_at.FromDatetime(caps.timestamp)
    else:
        snapshot.observed_at.CopyFrom(_now())
    return snapshot


class EdgeAdapterV3Servicer(edge_v3_grpc.EdgeAdapterServiceServicer):
    """``zqnt.edge.v3.EdgeAdapterService`` on top of the same EdgeAdapter the v2 servicer uses."""

    #: How long the adapter's capability list is reused to look up a command's completion mode.
    COMPLETION_CACHE_SECONDS = 30.0

    def __init__(self, adapter: EdgeAdapter) -> None:
        self._adapter = adapter
        self._completion_cache: dict[str, tuple[float, dict[str, CompletionMode]]] = {}

    async def _completion(self, sn: str, command_id: str, response: CustomCommandResponse) -> CompletionMode:
        """
        The command's declared completion mode, looked up only when it decides something: a
        success that did not bring its own execution id. Never fails the command.
        """
        if not response.success or response.external_execution_id:
            return CompletionMode.UNSPECIFIED
        now = time.monotonic()
        cached = self._completion_cache.get(sn)
        if cached is None or cached[0] <= now:
            try:
                caps = await self._adapter.get_capabilities(sn=sn, asset_id=None)
            except Exception:
                logger.debug("capabilities of %s unreadable; completion left to the response", sn, exc_info=True)
                return CompletionMode.UNSPECIFIED
            modes = {c.command_id: c.completion for c in (caps.capabilities if caps else [])}
            cached = (now + self.COMPLETION_CACHE_SECONDS, modes)
            self._completion_cache[sn] = cached
        return cached[1].get(command_id, CompletionMode.UNSPECIFIED)

    async def GetCapabilities(self, request, context):
        try:
            caps = await self._adapter.get_capabilities(sn=request.asset.sn, asset_id=request.asset.id or None)
        except Exception as exc:
            logger.exception("v3 GetCapabilities error [sn=%s]", request.asset.sn)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))
        return edge_v3.GetCapabilitiesResponse(capabilities=capability_set(caps))

    async def ExecuteCommand(self, request, context):
        command = request.command
        ctx = _context(request.context, command.asset)
        params = json_format.MessageToDict(command.params) if command.HasField("params") else {}
        try:
            response = await self._adapter.send_custom_command(
                ctx, CustomCommandRequest(command_type=command.command_id, params=params)
            )
        except Exception as exc:
            logger.exception("v3 ExecuteCommand error [sn=%s command=%s]", ctx.sn, command.command_id)
            response = CustomCommandResponse.fail(ctx.tid, ctx.sn, command.command_id, _asset_error(str(exc)))
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
                detections = []
                for d in batch.detections:
                    detection = edge_v3.Detection(
                        object_id=d.object_id or "", object_type=d.object_type or "", confidence=d.confidence or 0.0
                    )
                    if d.bounding_box is not None:
                        detection.bounding_box.CopyFrom(
                            edge_v3.BoundingBox(
                                x=d.bounding_box.x,
                                y=d.bounding_box.y,
                                width=d.bounding_box.width,
                                height=d.bounding_box.height,
                            )
                        )
                    if d.position is not None:
                        point = common_pb2.GeoPoint(latitude=d.position.latitude, longitude=d.position.longitude)
                        if d.position.altitude is not None:
                            point.altitude = d.position.altitude
                        detection.position.CopyFrom(point)
                    detections.append(detection)
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

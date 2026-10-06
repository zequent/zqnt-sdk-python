"""
Unit tests for the v3 edge contract (``zqnt.edge.v3.EdgeAdapterService``).

v3 has no per-command RPCs. What these guard: one adapter, declared once, answers v3
``ExecuteCommand`` for registered handlers and for built-in ids it implements typed; an unknown id
is refused as REJECTED (never an aborted call); a long command is ACCEPTED with the id it runs
under; capabilities come out of the same registry as v2's.
"""

from google.protobuf import struct_pb2
from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse
from edge_sdk.models.common import (
    CapabilityState,
    CompletionMode,
    Coordinates,
    CustomCommandResponse,
    ErrorCode,
    ErrorMessage,
)
from edge_sdk.server.edge_server_v3 import NOT_SUPPORTED_CODE, EdgeAdapterV3Servicer


class _Context:
    """Stands in for grpc.aio.ServicerContext; v3 never aborts a command call."""

    async def abort(self, code, details):
        raise AssertionError(f"aborted: {code} {details}")


class _Adapter(EdgeAdapter):
    def __init__(self):
        self.takeoffs: list[Coordinates] = []
        self.sprays: list[dict] = []
        self.stopped: list[str] = []
        self.register_command("vendor.acme.spray", self._spray)
        self.register_command("mission.waypoint.execute", self._mission)
        self.register_command("vendor.acme.broken", self._broken)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    # A typed implementation, the way every adapter that predates the registry is written.
    async def take_off(self, ctx, coordinates):
        self.takeoffs.append(coordinates)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def stop_task(self, ctx, task_id):
        self.stopped.append(task_id)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def _spray(self, ctx, params):
        self.sprays.append(params)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "vendor.acme.spray", result={"litres": 2})

    async def _mission(self, ctx, params):
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "mission.waypoint.execute", external_execution_id="dji-77")

    async def _broken(self, ctx, params):
        return CustomCommandResponse.fail(
            ctx.tid, ctx.sn, "vendor.acme.broken", ErrorMessage("nozzle blocked", ErrorCode.ASSET_ERROR)
        )


def _execute(command_id: str, params: dict | None = None) -> edge_v3.ExecuteCommandRequest:
    command = command_pb2.Command(asset=common_pb2.AssetRef(sn="SN-1"), command_id=command_id)
    if params:
        s = struct_pb2.Struct()
        s.update(params)
        command.params.CopyFrom(s)
    return edge_v3.ExecuteCommandRequest(
        context=common_pb2.RequestContext(request_id="req-1"), command=command, command_execution_id="cx-1"
    )


async def test_a_registered_handler_runs_and_returns_its_result():
    adapter = _Adapter()
    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(
        _execute("vendor.acme.spray", {"seconds": 3}), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_SUCCEEDED
    assert response.result.command_execution_id == "cx-1"
    assert dict(response.result.result) == {"litres": 2.0}
    assert adapter.sprays == [{"seconds": 3.0}]


async def test_a_built_in_id_reaches_the_typed_method_of_an_older_adapter():
    adapter = _Adapter()
    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(
        _execute("flight.takeoff", {"latitude": 52.5, "longitude": 13.4, "altitude": 40}), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_SUCCEEDED
    assert adapter.takeoffs[0].latitude == 52.5
    assert adapter.takeoffs[0].altitude == 40


async def test_an_unknown_id_is_rejected_not_aborted():
    response = await EdgeAdapterV3Servicer(_Adapter()).ExecuteCommand(_execute("vendor.nope.nothing"), _Context())

    assert response.result.state == command_pb2.COMMAND_STATE_REJECTED
    assert response.result.error.code == NOT_SUPPORTED_CODE
    assert response.result.error.category == common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT


async def test_a_long_command_is_accepted_under_the_id_it_runs_as():
    response = await EdgeAdapterV3Servicer(_Adapter()).ExecuteCommand(_execute("mission.waypoint.execute"), _Context())

    assert response.result.state == command_pb2.COMMAND_STATE_ACCEPTED
    assert response.result.result["external_execution_id"] == "dji-77"


async def test_an_adapter_failure_is_failed_with_its_message():
    response = await EdgeAdapterV3Servicer(_Adapter()).ExecuteCommand(_execute("vendor.acme.broken"), _Context())

    assert response.result.state == command_pb2.COMMAND_STATE_FAILED
    assert response.result.error.category == common_pb2.ERROR_CATEGORY_ASSET
    assert response.result.error.message == "nozzle blocked"


async def test_cancel_stops_through_stop_task():
    adapter = _Adapter()
    response = await EdgeAdapterV3Servicer(adapter).CancelCommand(
        edge_v3.CancelCommandRequest(command_execution_id="dji-77", reason="operator"), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_CANCELLED
    assert adapter.stopped == ["dji-77"]


async def test_capabilities_come_from_the_same_registry_as_v2():
    response = await EdgeAdapterV3Servicer(_Adapter()).GetCapabilities(
        edge_v3.GetCapabilitiesRequest(asset=common_pb2.AssetRef(sn="SN-1")), _Context()
    )
    caps = {c.command_id: c for c in response.capabilities.capabilities}

    assert response.capabilities.asset_sn == "SN-1"
    assert caps["vendor.acme.spray"].state == int(CapabilityState.AVAILABLE)
    # Typed take_off is overridden, so the built-in id is advertised as available too.
    assert caps["flight.takeoff"].state == int(CapabilityState.AVAILABLE)
    assert "properties" in caps["flight.takeoff"].input_schema


class _DeclaringAdapter(_Adapter):
    """Declares take-off ASYNCHRONOUS: its typed take_off still answers a plain success."""

    async def get_capabilities(self, sn, asset_id):
        caps = self._auto_capabilities(sn, AssetType.AIRCRAFT)
        for capability in caps.capabilities:
            if capability.command_id == "flight.takeoff":
                capability.completion = CompletionMode.ASYNCHRONOUS
                capability.completion_event = "flight.takeoff.completed"
            if capability.command_id == "vendor.acme.spray":
                capability.completion = CompletionMode.ON_REPLY
        return caps


async def test_a_declared_asynchronous_command_waits_even_when_its_handler_answered_success():
    response = await EdgeAdapterV3Servicer(_DeclaringAdapter()).ExecuteCommand(
        _execute("flight.takeoff", {"latitude": 52.5, "longitude": 13.4, "altitude": 40}), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_ACCEPTED
    assert response.result.command_execution_id == "cx-1"


async def test_a_declared_on_reply_command_is_done_on_its_reply():
    response = await EdgeAdapterV3Servicer(_DeclaringAdapter()).ExecuteCommand(
        _execute("vendor.acme.spray", {"seconds": 1}), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_SUCCEEDED


async def test_the_completion_mode_is_published_with_the_capability():
    response = await EdgeAdapterV3Servicer(_DeclaringAdapter()).GetCapabilities(
        edge_v3.GetCapabilitiesRequest(asset=common_pb2.AssetRef(sn="SN-1")), _Context()
    )
    caps = {c.command_id: c for c in response.capabilities.capabilities}

    assert caps["flight.takeoff"].completion == int(CompletionMode.ASYNCHRONOUS)
    assert caps["flight.takeoff"].completion_event == "flight.takeoff.completed"
    assert caps["vendor.acme.spray"].completion == int(CompletionMode.ON_REPLY)


async def test_unreadable_capabilities_leave_the_command_to_its_response():
    class _Broken(_Adapter):
        async def get_capabilities(self, sn, asset_id):
            raise RuntimeError("registry down")

    response = await EdgeAdapterV3Servicer(_Broken()).ExecuteCommand(
        _execute("vendor.acme.spray", {"seconds": 1}), _Context()
    )

    assert response.result.state == command_pb2.COMMAND_STATE_SUCCEEDED

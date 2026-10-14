"""
v3 runs only what an adapter published; 2.x calls reach the same handlers through the bridge, with
the platform's execution id and with text converted to the published types. Free-form 2.x commands
go to ``legacy_custom_command``, never reached from v3.
"""

from google.protobuf import struct_pb2
from zqnt_api.generated.zqnt import common_pb2 as common_v2
from zqnt_api.generated.zqnt.capability.v3 import command_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

from edge_sdk import AssetType, EdgeAdapter, schema
from edge_sdk.adapter.validation import convert_text
from edge_sdk.models.common import CustomCommandResponse
from edge_sdk.server.edge_server import _EdgeAdapterServicer
from edge_sdk.server.edge_server_v3 import NOT_SUPPORTED_CODE, EdgeAdapterV3Servicer

EXECUTION_ID = "capexec:exec-1:node-1"

SPRAY = schema(
    {
        "seconds": {"type": "integer"},
        "pressure": {"type": "number"},
        "dry_run": {"type": "boolean"},
        "nozzle": {"type": "string", "enum": ["FINE", "WIDE"]},
        "label": {"type": "string"},
    },
    ["seconds"],
)


class _Adapter(EdgeAdapter):
    def __init__(self):
        self.calls: list[tuple[str | None, dict]] = []
        self.legacy: list[str] = []
        self.register_command("vendor.acme.spray", self._record, input_schema=SPRAY)
        self.register_command("flight.takeoff", self._record)
        self.register_command("mission.stop", self._stop)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def _record(self, ctx, params):
        self.calls.append((ctx.command_execution_id, params))
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "recorded")

    async def _stop(self, ctx, params):
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "mission.stop", message="detection stopped")


class _LegacyAdapter(_Adapter):
    async def legacy_custom_command(self, ctx, request):
        self.legacy.append(request.command_type)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, request.command_type, result={"sent": True})


def _base(external_id: str | None = EXECUTION_ID) -> common_v2.RequestBase:
    base = common_v2.RequestBase(tid="tid-1", sn="SN-1")
    if external_id is not None:
        base.external_id = external_id
    return base


def _struct(params: dict) -> struct_pb2.Struct:
    s = struct_pb2.Struct()
    s.update(params)
    return s


def _custom(command_id: str, params: dict | None = None) -> common_v2.CustomCommandRequest:
    request = common_v2.CustomCommandRequest(base=_base(), command_id=command_id)
    if params:
        request.params.CopyFrom(_struct(params))
    return request


def _execute(command_id: str, params: dict | None = None) -> edge_v3.ExecuteCommandRequest:
    command = command_pb2.Command(asset=common_pb2.AssetRef(sn="SN-1"), command_id=command_id)
    if params:
        command.params.CopyFrom(_struct(params))
    return edge_v3.ExecuteCommandRequest(
        context=common_pb2.RequestContext(request_id="req-1"), command=command, command_execution_id=EXECUTION_ID
    )


async def test_v3_refuses_an_unpublished_id_even_when_the_adapter_takes_free_form_commands():
    adapter = _LegacyAdapter()

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(_execute("mode_change"), None)

    assert response.result.state == command_pb2.COMMAND_STATE_REJECTED
    assert response.result.error.code == NOT_SUPPORTED_CODE
    assert adapter.legacy == []


async def test_v2_hands_an_unpublished_id_to_the_legacy_hook():
    adapter = _LegacyAdapter()

    response = await _EdgeAdapterServicer(adapter).SendCustomCommand(_custom("Start Test"), None)

    assert not response.has_errors
    assert adapter.legacy == ["Start Test"]


async def test_the_legacy_hook_refuses_by_default():
    adapter = _Adapter()

    response = await _EdgeAdapterServicer(adapter).SendCustomCommand(_custom("Start Test"), None)

    assert response.has_errors
    assert "not supported" in response.error.error_message
    assert adapter.calls == []


async def test_a_published_id_never_reaches_the_legacy_hook():
    adapter = _LegacyAdapter()

    await _EdgeAdapterServicer(adapter).SendCustomCommand(_custom("vendor.acme.spray", {"seconds": 3}), None)

    assert adapter.legacy == []
    assert adapter.calls == [(EXECUTION_ID, {"seconds": 3})]


async def test_v2_custom_command_hands_the_execution_id_to_the_handler():
    adapter = _Adapter()

    await _EdgeAdapterServicer(adapter).SendCustomCommand(_custom("vendor.acme.spray", {"seconds": 3}), None)

    assert adapter.calls[0][0] == EXECUTION_ID


async def test_v2_typed_call_hands_the_execution_id_to_the_handler():
    adapter = _Adapter()
    request = common_v2.CoordinateCommandRequest(
        base=_base(), coordinate=common_v2.GeoCoordinate(latitude=52.5, longitude=13.4, altitude=30.0)
    )

    response = await _EdgeAdapterServicer(adapter).TakeOff(request, None)

    assert not response.has_errors
    assert adapter.calls[0][0] == EXECUTION_ID


async def test_a_v2_call_without_an_execution_id_has_none():
    adapter = _Adapter()
    request = common_v2.CustomCommandRequest(
        base=_base(external_id=None), command_id="vendor.acme.spray", params=_struct({"seconds": 3})
    )

    await _EdgeAdapterServicer(adapter).SendCustomCommand(request, None)

    assert adapter.calls[0][0] is None


async def test_v2_converts_text_to_the_published_types():
    adapter = _Adapter()
    text = {"seconds": "5", "pressure": " 52.5200 ", "dry_run": "TRUE", "nozzle": "wide", "label": "0123"}

    response = await _EdgeAdapterServicer(adapter).SendCustomCommand(_custom("vendor.acme.spray", text), None)

    assert not response.has_errors
    params = adapter.calls[0][1]
    assert params == {"seconds": 5, "pressure": 52.52, "dry_run": True, "nozzle": "WIDE", "label": "0123"}
    assert isinstance(params["seconds"], int)


async def test_v3_keeps_text_as_text():
    adapter = _Adapter()

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(
        _execute("vendor.acme.spray", {"seconds": "5", "nozzle": "wide"}), None
    )

    assert response.result.state == command_pb2.COMMAND_STATE_REJECTED
    assert response.result.error.code == "command.invalid_params"
    assert adapter.calls == []


async def test_v2_still_refuses_text_that_is_not_exactly_the_published_type():
    adapter = _Adapter()

    response = await _EdgeAdapterServicer(adapter).SendCustomCommand(
        _custom("vendor.acme.spray", {"seconds": "3.5"}), None
    )

    assert response.has_errors
    assert "params.seconds must be integer, got string" in response.error.error_message
    assert adapter.calls == []


async def test_v2_typed_call_keeps_the_handler_message():
    response = await _EdgeAdapterServicer(_Adapter()).StopTask(
        common_v2.TaskCommandRequest(base=_base(), task_id="task-1"), None
    )

    assert not response.has_errors
    assert response.meta.response_message == "detection stopped"


def test_only_exact_conversions():
    converted = convert_text(
        SPRAY,
        {"seconds": "3.0", "pressure": "NaN", "dry_run": "yes", "nozzle": "medium", "label": "1.0.0"},
    )

    assert converted == {"seconds": 3, "pressure": "NaN", "dry_run": "yes", "nozzle": "medium", "label": "1.0.0"}
    assert convert_text(SPRAY, {"pressure": "1_000"}) == {"pressure": "1_000"}
    assert convert_text(SPRAY, {"pressure": "-1e3"}) == {"pressure": -1000.0}


def test_conversion_follows_nested_objects_and_arrays():
    waypoints = schema(
        {
            "waypoints": {
                "type": "array",
                "items": schema({"latitude": {"type": "number"}, "flyThrough": {"type": "boolean"}}),
            }
        }
    )

    converted = convert_text(waypoints, {"waypoints": [{"latitude": "47.5", "flyThrough": "false"}]})

    assert converted == {"waypoints": [{"latitude": 47.5, "flyThrough": False}]}


def test_an_enum_value_in_two_cases_is_left_to_validation():
    ambiguous = schema({"mode": {"type": "string", "enum": ["auto", "AUTO"]}})

    assert convert_text(ambiguous, {"mode": "Auto"}) == {"mode": "Auto"}


def test_a_number_that_does_not_fit_an_integer_stays_text():
    huge = "9" * 20

    assert convert_text(SPRAY, {"seconds": huge}) == {"seconds": huge}

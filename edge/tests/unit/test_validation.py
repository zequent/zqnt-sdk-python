"""
Params are checked against the command's input schema once, in the SDK, before any handler runs.
"""

import math

from google.protobuf import struct_pb2
from zqnt_utils.generated.zqnt import common_pb2 as common_v2
from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

from edge_sdk import AssetType, EdgeAdapter, schema
from edge_sdk.adapter.validation import check_schema, example_params, validate_params
from edge_sdk.models.common import CustomCommandResponse, ErrorCode
from edge_sdk.server.edge_server import _EdgeAdapterServicer
from edge_sdk.server.edge_server_v3 import EdgeAdapterV3Servicer

SPRAY = schema(
    {
        "seconds": {"type": "integer", "minimum": 1, "maximum": 60},
        "nozzle": {"type": "string", "enum": ["fine", "wide"]},
        "latitude": {"type": "number"},
    },
    ["seconds"],
)


class _Adapter(EdgeAdapter):
    def __init__(self):
        self.calls: list[dict] = []
        self.register_command("vendor.acme.spray", self._spray, input_schema=SPRAY)
        self.register_command("navigation.go_to", self._go_to)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def _spray(self, ctx, params):
        self.calls.append(params)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "vendor.acme.spray")

    async def _go_to(self, ctx, params):
        self.calls.append(params)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "navigation.go_to")


def _execute(command_id: str, params: dict) -> edge_v3.ExecuteCommandRequest:
    s = struct_pb2.Struct()
    s.update(params)
    return edge_v3.ExecuteCommandRequest(
        context=common_pb2.RequestContext(request_id="req-1"),
        command=command_pb2.Command(asset=common_pb2.AssetRef(sn="SN-1"), command_id=command_id, params=s),
        command_execution_id="capexec:e1:n1",
    )


def test_an_integral_double_becomes_an_int_where_the_schema_says_integer():
    checked = validate_params(SPRAY, {"seconds": 5.0})

    assert checked.valid
    assert checked.params["seconds"] == 5
    assert isinstance(checked.params["seconds"], int)


def test_a_fractional_number_is_not_an_integer():
    checked = validate_params(SPRAY, {"seconds": 5.5})

    assert not checked.valid
    assert "params.seconds must be integer" in checked.message


def test_every_violation_is_reported():
    checked = validate_params(SPRAY, {"seconds": 0, "nozzle": "jet", "colour": "red"})

    assert "params.seconds must be >= 1" in checked.errors
    assert "params.nozzle must be one of 'fine', 'wide'" in checked.errors
    assert "params.colour is not a known parameter" in checked.errors


def test_nan_is_a_number_but_never_satisfies_required():
    go_to = schema({"latitude": {"type": "number"}, "altitude": {"type": "number"}}, ["latitude"])

    omitted_altitude = validate_params(go_to, {"latitude": 47.0, "altitude": float("nan")})
    omitted_latitude = validate_params(go_to, {"latitude": float("nan")})

    assert omitted_altitude.valid
    assert math.isnan(omitted_altitude.params["altitude"])
    assert omitted_latitude.errors == ["params.latitude is required"]


def test_nan_written_as_json_text_counts_as_a_number():
    checked = validate_params(schema({"altitude": {"type": "number"}}), {"altitude": "NaN"})

    assert checked.valid
    assert math.isnan(checked.params["altitude"])


def test_nested_waypoints_are_checked_and_coerced():
    mission = schema(
        {
            "waypoints": {
                "type": "array",
                "minItems": 1,
                "items": schema({"latitude": {"type": "number"}, "wpOrder": {"type": "integer"}}, ["latitude"]),
            }
        },
        ["waypoints"],
    )

    checked = validate_params(mission, {"waypoints": [{"latitude": 1.0, "wpOrder": 2.0}, {"wpOrder": 3.0}]})

    assert checked.errors == ["params.waypoints[1].latitude is required"]
    assert checked.params["waypoints"][0]["wpOrder"] == 2
    assert validate_params(mission, {"waypoints": []}).errors == ["params.waypoints needs at least 1 items"]


def test_no_schema_lets_everything_through():
    assert validate_params(None, {"anything": 1}).valid


def test_a_malformed_schema_never_blocks_a_command():
    assert validate_params({"type": "object", "properties": {"x": {"type": "decimal"}}}, {"x": 1}).valid
    assert check_schema({"type": "object", "properties": {"x": {"type": "decimal"}}}) == [
        "schema.properties.x.type: unknown type 'decimal'"
    ]


def test_the_minimal_example_satisfies_its_schema():
    assert validate_params(SPRAY, example_params(SPRAY)).valid


def test_unique_items_refuses_a_repeated_item():
    bands = schema(
        {
            "bands": {
                "type": "array",
                "items": {"type": "string", "enum": ["GNSS", "ISM_2400", "ISM_5800"]},
                "minItems": 2,
                "uniqueItems": True,
            }
        },
        ["bands"],
    )

    assert check_schema(bands) == []
    assert validate_params(bands, {"bands": ["GNSS", "ISM_2400"]}).valid
    assert validate_params(bands, {"bands": ["GNSS", "GNSS"]}).errors == ["params.bands must not repeat an item"]
    assert validate_params(bands, example_params(bands)).valid


async def test_invalid_params_never_reach_the_handler_and_are_rejected():
    adapter = _Adapter()

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(
        _execute("vendor.acme.spray", {"seconds": 120}), None
    )

    assert adapter.calls == []
    assert response.result.state == command_pb2.COMMAND_STATE_REJECTED
    assert response.result.error.code == "command.invalid_params"
    assert response.result.error.category == common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT
    assert "params.seconds must be <= 60" in response.result.error.message


async def test_the_handler_gets_coerced_params():
    adapter = _Adapter()

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(_execute("vendor.acme.spray", {"seconds": 3}), None)

    assert response.result.state == command_pb2.COMMAND_STATE_SUCCEEDED
    assert adapter.calls == [{"seconds": 3}]
    assert isinstance(adapter.calls[0]["seconds"], int)


async def test_a_catalog_command_is_checked_against_the_catalog_schema():
    adapter = _Adapter()

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(_execute("navigation.go_to", {"altitude": 40}), None)

    assert response.result.state == command_pb2.COMMAND_STATE_REJECTED
    assert "params.latitude is required" in response.result.error.message


async def test_v2_custom_commands_are_checked_too():
    adapter = _Adapter()
    params = struct_pb2.Struct()
    params.update({"seconds": "five"})
    request = common_v2.CustomCommandRequest(
        base=common_v2.RequestBase(tid="t", sn="SN-1"), command_id="vendor.acme.spray", params=params
    )

    response = await _EdgeAdapterServicer(adapter).SendCustomCommand(request, None)

    assert response.has_errors
    assert response.error.error_code == int(ErrorCode.CLIENT_ERROR)
    assert "params.seconds must be integer, got string" in response.error.error_message
    assert adapter.calls == []

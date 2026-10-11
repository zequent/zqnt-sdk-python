"""A command's risk reaches the platform: declared by the adapter, else the catalog's rating."""

from zqnt_api.generated.zqnt.capability.v3 import capability_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

from edge_sdk import AssetType, CommandRisk, CommandSafety, CustomCommandResponse, EdgeAdapter
from edge_sdk.adapter.commands import catalog_safety
from edge_sdk.server.edge_server_v3 import EdgeAdapterV3Servicer


class _Context:
    async def abort(self, code, details):
        raise AssertionError(f"aborted: {code} {details}")


async def _ok(ctx, params):
    return CustomCommandResponse.ok(ctx.tid, ctx.sn, "ok")


class _Adapter(EdgeAdapter):
    def __init__(self):
        self.register_command("flight.takeoff", _ok)
        self.register_command("flight.land", _ok)
        self.register_command(
            "dock.open_cover",
            _ok,
            safety=CommandSafety(risk=CommandRisk.MOVE, preconditions=("no aircraft above the dock",)),
        )
        self.register_command("vendor.acme.spray", _ok, safety=CommandRisk.CRITICAL)
        self.register_command("vendor.acme.status", _ok)
        self.register_command("vendor.betaflight.arm", _ok)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)


async def _advertised() -> dict[str, capability_pb2.Capability]:
    response = await EdgeAdapterV3Servicer(_Adapter()).GetCapabilities(
        edge_v3.GetCapabilitiesRequest(asset=common_pb2.AssetRef(sn="SN-1")), _Context()
    )
    return {c.command_id: c for c in response.capabilities.capabilities}


async def test_a_standard_command_is_advertised_with_its_catalog_risk():
    caps = await _advertised()

    takeoff = caps["flight.takeoff"].safety
    assert takeoff.risk == capability_pb2.COMMAND_RISK_MOVE
    assert takeoff.reversible
    assert takeoff.undo_command_id == "flight.return_to_home"
    assert caps["flight.land"].safety.risk == capability_pb2.COMMAND_RISK_CRITICAL
    assert caps["camera.take_photo"].safety.risk == capability_pb2.COMMAND_RISK_OBSERVE


async def test_the_adapters_own_safety_wins():
    caps = await _advertised()

    assert caps["dock.open_cover"].safety.risk == capability_pb2.COMMAND_RISK_MOVE
    assert list(caps["dock.open_cover"].safety.preconditions) == ["no aircraft above the dock"]
    assert caps["vendor.acme.spray"].safety.risk == capability_pb2.COMMAND_RISK_CRITICAL


async def test_an_unknown_id_declares_nothing_and_an_unrated_catalog_id_counts_as_critical():
    caps = await _advertised()

    assert not caps["vendor.acme.status"].HasField("safety")
    assert caps["vendor.betaflight.arm"].safety.risk == capability_pb2.COMMAND_RISK_CRITICAL


def test_a_property_setter_matches_the_catalog_pattern():
    assert catalog_safety("asset.property.night_lights_state.set").risk is CommandRisk.ADJUST
    assert catalog_safety("asset.property.set") is None

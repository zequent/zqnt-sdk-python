"""
Unit tests for the command registry — the 2.0 mechanism that makes one registration produce
both the advertised capability and the dispatch entry.

The bug class these guard against is "handled but unadvertised" / "advertised but rejected":
before the registry, ``get_capabilities`` was derived from overridden methods while
``send_custom_command`` dispatched on hand-written string comparisons, so the two drifted.
"""

import pytest

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse, schema
from edge_sdk.models.common import (
    CapabilityState,
    CapabilityTarget,
    CapabilityTargetType,
    Coordinates,
    CustomCommandRequest,
    CustomCommandResponse,
    ErrorCode,
    ErrorMessage,
)
from tests.conftest import make_ctx


class _RegistryAdapter(EdgeAdapter):
    """Declares everything through register_command — no typed methods overridden at all."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.register_command("flight.takeoff", self._record)
        self.register_command("mission.waypoint.execute", self._record)
        self.register_command(
            "vendor.acme.spray",
            self._record,
            description="Run the spray boom",
            input_schema=schema({"seconds": {"type": "number"}}, ["seconds"]),
            target=CapabilityTarget(CapabilityTargetType.PAYLOAD, "payload-1"),
        )
        # Declared but not runnable — a contract the asset knows about yet cannot serve now.
        self.register_command(
            "dock.open_cover",
            state=CapabilityState.TEMPORARILY_UNAVAILABLE,
            unavailable_reason="cover jammed",
        )

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def _record(self, ctx, params) -> CustomCommandResponse:
        self.calls.append((ctx.tid, params))
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "recorded", result={"ok": True})


def _caps(adapter: EdgeAdapter) -> dict:
    return {c.command_id: c for c in adapter._auto_capabilities("SN-1", AssetType.AIRCRAFT).capabilities}


# ---------------------------------------------------------------------------
# Advertisement
# ---------------------------------------------------------------------------


def test_registered_command_is_advertised_with_catalog_schema():
    caps = _caps(_RegistryAdapter())

    takeoff = caps["flight.takeoff"]
    assert takeoff.state is CapabilityState.AVAILABLE
    # Contract defaulted from the platform catalog, not re-typed by the adapter.
    assert takeoff.input_schema["properties"].keys() == {"latitude", "longitude", "altitude"}
    assert takeoff.description


def test_registered_command_can_carry_its_own_vendor_contract():
    spray = _caps(_RegistryAdapter())["vendor.acme.spray"]

    assert spray.input_schema["required"] == ["seconds"]
    assert spray.target.type is CapabilityTargetType.PAYLOAD
    assert spray.target.target_ref == "payload-1"


def test_registration_can_declare_a_command_as_temporarily_unavailable():
    cover = _caps(_RegistryAdapter())["dock.open_cover"]

    assert cover.state is CapabilityState.TEMPORARILY_UNAVAILABLE
    assert cover.unavailable_reason == "cover jammed"


def test_every_dispatchable_command_is_advertised():
    """The regression guard: nothing may be runnable without appearing in the snapshot."""
    adapter = _RegistryAdapter()
    advertised = _caps(adapter).keys()

    for command_id, registered in adapter.registered_commands().items():
        if registered.dispatchable:
            assert command_id in advertised, f"{command_id} is handled but never advertised"


def test_command_ids_are_dotted():
    """Core matches on dotted ids; a PascalCase id would silently never match."""
    for command_id in _caps(_RegistryAdapter()):
        assert "." in command_id, f"{command_id!r} is not a dotted platform command id"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_custom_command_dispatches_to_registered_handler():
    adapter = _RegistryAdapter()
    ctx = make_ctx()

    response = await adapter.send_custom_command(
        ctx, CustomCommandRequest(command_type="mission.waypoint.execute", params={"waypoints": [1]})
    )

    assert response.success
    assert adapter.calls == [(ctx.tid, {"waypoints": [1]})]


@pytest.mark.asyncio
async def test_send_custom_command_refuses_an_unregistered_command():
    response = await _RegistryAdapter().send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="flight.nope", params={})
    )

    assert not response.success


@pytest.mark.asyncio
async def test_registered_but_handlerless_command_is_not_dispatchable():
    """Declaring a contract must not imply the adapter can run it."""
    response = await _RegistryAdapter().send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="dock.open_cover", params={})
    )

    assert not response.success


# ---------------------------------------------------------------------------
# Typed-RPC delegation — the "no flag day" half of the design
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_typed_rpc_delegates_into_the_registry():
    """take_off() is never overridden, yet works because flight.takeoff is registered."""
    adapter = _RegistryAdapter()

    response = await adapter.take_off(make_ctx(), Coordinates(latitude=1.0, longitude=2.0, altitude=30.0))

    assert response.success
    assert adapter.calls[-1][1] == {"latitude": 1.0, "longitude": 2.0, "altitude": 30.0}


@pytest.mark.asyncio
async def test_typed_rpc_without_registration_still_reports_not_supported():
    class _Bare(EdgeAdapter):
        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    response = await _Bare().take_off(make_ctx(), Coordinates(latitude=1.0, longitude=2.0, altitude=3.0))

    assert not response.success
    assert response.error.code is ErrorCode.SDK_ERROR


@pytest.mark.asyncio
async def test_typed_rpc_propagates_a_handler_failure():
    class _Failing(EdgeAdapter):
        def __init__(self):
            self.register_command("flight.takeoff", self._boom)

        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.AIRCRAFT)

        async def _boom(self, ctx, params):
            return CustomCommandResponse.fail(
                ctx.tid, ctx.sn, "flight.takeoff", ErrorMessage(message="no GPS", code=ErrorCode.ASSET_ERROR)
            )

    response = await _Failing().take_off(make_ctx(), Coordinates(latitude=0.0, longitude=0.0, altitude=0.0))

    assert not response.success
    assert response.error.message == "no GPS"


@pytest.mark.asyncio
async def test_overriding_a_typed_method_still_wins():
    """Adapters converting one command at a time must keep their existing typed implementations."""

    class _Typed(EdgeAdapter):
        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.AIRCRAFT)

        async def take_off(self, ctx, coordinates):
            return EdgeResponse.ok(ctx.tid, ctx.sn, "typed")

    adapter = _Typed()
    response = await adapter.take_off(make_ctx(), Coordinates(latitude=0.0, longitude=0.0, altitude=0.0))

    assert response.success
    assert _caps(adapter)["flight.takeoff"].state is CapabilityState.AVAILABLE

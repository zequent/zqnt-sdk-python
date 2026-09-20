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


# ---------------------------------------------------------------------------
# The other direction: an adapter that implements the typed methods must also
# answer the id it advertises, or "advertised but not executable" survives in
# the Python SDK exactly as it did in edge-dji.
# ---------------------------------------------------------------------------


class _TypedOnlyAdapter(EdgeAdapter):
    """No registrations at all — just typed overrides, like every pre-2.0 adapter."""

    def __init__(self):
        self.calls: list[str] = []

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(self, ctx, coordinates):
        self.calls.append(f"take_off:{coordinates.latitude},{coordinates.altitude}")
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def boot_up_sub_asset(self, ctx):
        self.calls.append("boot_up")
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def boot_down_sub_asset(self, ctx):
        self.calls.append("boot_down")
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def close_cover(self, ctx, force):
        self.calls.append(f"close_cover:{force}")
        return EdgeResponse.ok(ctx.tid, ctx.sn)


@pytest.mark.asyncio
async def test_a_typed_only_adapter_answers_the_id_it_advertises():
    adapter = _TypedOnlyAdapter()

    response = await adapter.send_custom_command(
        make_ctx(),
        CustomCommandRequest(
            command_type="flight.takeoff", params={"latitude": 47.1, "longitude": 8.5, "altitude": 30.0}
        ),
    )

    assert response.success
    assert adapter.calls == ["take_off:47.1,30.0"]


@pytest.mark.asyncio
async def test_typed_dispatch_picks_the_method_from_the_params():
    up, down = _TypedOnlyAdapter(), _TypedOnlyAdapter()

    await up.send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="asset.boot_sub_asset", params={"enabled": True})
    )
    await down.send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="asset.boot_sub_asset", params={"enabled": False})
    )

    assert up.calls == ["boot_up"]
    assert down.calls == ["boot_down"]


@pytest.mark.asyncio
async def test_typed_dispatch_reports_an_unimplemented_command_as_unsupported():
    """Routable id, no implementation — must fail, not pretend to have run."""
    response = await _TypedOnlyAdapter().send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="dock.open_cover", params={})
    )

    assert not response.success


@pytest.mark.asyncio
async def test_a_registered_handler_still_wins_over_the_typed_method():
    class _Both(_TypedOnlyAdapter):
        def __init__(self):
            super().__init__()
            self.register_command("flight.takeoff", self._registered)

        async def _registered(self, ctx, params):
            self.calls.append("registered")
            return CustomCommandResponse.ok(ctx.tid, ctx.sn, "flight.takeoff")

    adapter = _Both()
    await adapter.send_custom_command(
        make_ctx(), CustomCommandRequest(command_type="flight.takeoff", params={"latitude": 1.0})
    )

    assert adapter.calls == ["registered"]


@pytest.mark.asyncio
async def test_every_advertised_command_is_routable_by_id():
    """
    The cross-SDK invariant: nothing may be advertised that cannot be reached by its id.

    Checked against the routing tables rather than by calling each command, because an
    unimplemented command and an unknown one both come back as a plain failure — routability is
    the property that actually matters here, and the only one the two can be told apart by.
    """
    from edge_sdk.adapter.base import _STREAMING_COMMANDS, _TYPED_DISPATCH

    adapter = _TypedOnlyAdapter()
    caps = await adapter.get_capabilities("SN-1", None)

    unroutable = [
        c.command_id
        for c in caps.capabilities
        # Only what the adapter claims it can do. The snapshot also carries every catalog command
        # it cannot, as UNSUPPORTED — that entry is itself the statement "not routable here", so
        # requiring a route for it would contradict what it says.
        if c.state is CapabilityState.AVAILABLE
        and c.command_id not in _TYPED_DISPATCH
        and c.command_id not in adapter.registered_commands()
        and c.command_id not in _STREAMING_COMMANDS
    ]

    assert not unroutable, f"advertised but not routable by id: {unroutable}"


# ---------------------------------------------------------------------------
# supports_method — what the gRPC servicer gates every RPC on
# ---------------------------------------------------------------------------


def test_a_registered_command_makes_its_typed_rpc_supported():
    adapter = _RegistryAdapter()
    # Nothing is overridden on this adapter; flight.takeoff exists only as a registration.
    assert adapter._is_overridden("take_off") is False
    assert adapter.supports_method("take_off") is True


def test_send_custom_command_is_always_supported():
    """It routes registrations and built-in ids, and reports an unknown id as a failed response."""
    assert _RegistryAdapter().supports_method("send_custom_command") is True


def test_unregistered_command_stays_unsupported():
    assert _RegistryAdapter().supports_method("close_cover") is False


def test_a_declaration_without_a_handler_is_not_executable():
    """dock.open_cover is advertised TEMPORARILY_UNAVAILABLE with no handler — a contract, not a run."""
    adapter = _RegistryAdapter()
    assert _caps(adapter)["dock.open_cover"].state is CapabilityState.TEMPORARILY_UNAVAILABLE
    assert adapter.supports_method("open_cover") is False


# ---------------------------------------------------------------------------
# Skills and labels
# ---------------------------------------------------------------------------


def test_catalog_commands_carry_a_skill_and_a_label():
    caps = _caps(_RegistryAdapter())
    assert caps["mission.waypoint.execute"].skill_id == "mission"
    assert caps["mission.waypoint.execute"].display_name == "Fly waypoint mission"
    # Unsupported entries are advertised too, and are just as groupable.
    assert caps["dock.close_cover"].skill_id == "dock"
    assert caps["dock.close_cover"].display_name == "Close cover"


def test_manual_control_is_its_own_skill_not_flight():
    caps = _caps(_RegistryAdapter())
    assert caps["flight.manual.input"].skill_id == "manual_control"
    assert caps["flight.takeoff"].skill_id == "flight"


def test_vendor_command_can_declare_its_skill():
    class _Vendor(_RegistryAdapter):
        def __init__(self):
            super().__init__()
            self.register_command(
                "vendor.acme.spray",
                self._record,
                description="Run the spray boom",
                display_name="Spray",
                skill_id="spraying",
            )

    caps = _caps(_Vendor())
    assert caps["vendor.acme.spray"].skill_id == "spraying"
    assert caps["vendor.acme.spray"].display_name == "Spray"


def test_the_whole_catalog_is_reported_even_when_unsupported():
    """
    A snapshot answers for every catalog command, not only the ones with a typed SDK method.

    mission.waypoint.execute, mission.pause and mission.resume have no typed method at all: they
    used to be absent from the snapshot of any adapter that did not register them, which reads as
    "this asset has not reported yet" rather than "this asset cannot do that".
    """
    caps = _caps(_TypedOnlyAdapter())
    for command_id in ("mission.waypoint.execute", "mission.pause", "mission.resume", "audio.play_tts"):
        assert caps[command_id].state is CapabilityState.UNSUPPORTED


def test_registering_one_of_them_flips_it_available():
    adapter = _RegistryAdapter()
    assert _caps(adapter)["mission.waypoint.execute"].state is CapabilityState.AVAILABLE

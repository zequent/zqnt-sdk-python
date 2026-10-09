"""The conformance kit catches drift between what an adapter advertises and what it runs."""

import pytest

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse, TelemetryValueType, schema
from edge_sdk.models.common import Capabilities, Capability, CommandExecutionStatus, CustomCommandResponse
from edge_sdk.models.notification import CommandExecutionEvent
from edge_sdk.testing import RecordingGateway, assert_conformant, check_conformance


async def _ok(ctx, params):
    return CustomCommandResponse.ok(ctx.tid, ctx.sn, "ok")


class _Good(EdgeAdapter):
    def __init__(self):
        self.register_command("dock.open_cover", _ok)
        self.register_command("mission.waypoint.execute", _ok)
        self.register_command("vendor.acme.spray", _ok, input_schema=schema({"seconds": {"type": "integer"}}))
        self.declare_telemetry_field("dock.cover_state", TelemetryValueType.STRING, allowed_values=["OPEN", "CLOSED"])

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)


class _AdvertisesWithoutHandler(_Good):
    def __init__(self):
        super().__init__()
        self.register_command("vendor.acme.ghost")


class _HidesWhatItRuns(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return Capabilities(asset_sn=sn, asset_type=AssetType.DOCK, capabilities=[])

    async def open_cover(self, ctx):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


class _BadSchema(_Good):
    async def get_capabilities(self, sn, asset_id):
        caps = await super().get_capabilities(sn, asset_id)
        caps.capabilities.append(
            Capability(
                command_id="vendor.acme.odd", input_schema={"type": "object", "properties": {"x": {"type": "x"}}}
            )
        )
        return caps


class _RejectsItsOwnCommand(_Good):
    def __init__(self):
        super().__init__()
        self.register_command("vendor.acme.picky", self._picky)

    async def _picky(self, ctx, params):
        return CustomCommandResponse.invalid_params(ctx.tid, ctx.sn, "vendor.acme.picky", "never happy")


async def test_a_registry_adapter_is_conformant():
    await assert_conformant(_Good(), execute=True)


async def test_an_advertised_command_without_a_handler_is_reported():
    report = await check_conformance(_AdvertisesWithoutHandler())

    assert "vendor.acme.ghost is advertised but has no handler" in report.problems


async def test_an_executable_command_that_is_not_advertised_is_reported():
    with pytest.warns(DeprecationWarning):

        class _Hidden(_HidesWhatItRuns):
            async def close_cover(self, ctx, force):
                return EdgeResponse.ok(ctx.tid, ctx.sn)

    report = await check_conformance(_Hidden())

    assert "dock.open_cover is executable but not advertised" in report.problems
    assert "dock.close_cover is executable but not advertised" in report.problems


async def test_a_schema_the_sdk_cannot_read_is_reported():
    report = await check_conformance(_BadSchema())

    assert any("vendor.acme.odd input schema" in p and "unknown type 'x'" in p for p in report.problems)


async def test_execution_finds_a_command_that_refuses_valid_params():
    report = await check_conformance(_RejectsItsOwnCommand(), execute=True)

    assert any(p.startswith("vendor.acme.picky is advertised but ExecuteCommand refused it") for p in report.problems)


async def test_the_recording_gateway_checks_published_events():
    gateway = RecordingGateway()

    await gateway.publish_command_event(
        CommandExecutionEvent(external_execution_id="v-1", status=CommandExecutionStatus.SUCCEEDED, sn="SN-1")
    )

    gateway.assert_events_complete()
    assert gateway.events[0].command_execution_id == "v-1"

"""
A command event reaches the platform under the platform's command_execution_id and always with
occurred_at -- the platform refuses one without it.
"""

from datetime import datetime, timezone

from google.protobuf import struct_pb2
from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

from edge_sdk import AssetType, EdgeAdapter
from edge_sdk.client.edge_gateway import CommandRuns, V3Fallback, command_event
from edge_sdk.models.common import CommandExecutionStatus, CustomCommandResponse
from edge_sdk.models.notification import CommandExecutionEvent
from edge_sdk.server.edge_server_v3 import EdgeAdapterV3Servicer


class _Adapter(EdgeAdapter):
    def __init__(self):
        self.seen_ids: list[str | None] = []
        self.register_command("vendor.acme.survey", self._survey)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def _survey(self, ctx, params):
        self.seen_ids.append(ctx.command_execution_id)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "vendor.acme.survey", external_execution_id="vendor-9")


def test_occurred_at_is_set_when_the_adapter_gave_none():
    event = command_event(
        CommandExecutionEvent(external_execution_id="x", status=CommandExecutionStatus.SUCCEEDED, sn="SN-1")
    )

    assert event.HasField("occurred_at")
    assert event.occurred_at.seconds > 0


def test_the_adapters_time_and_fields_are_kept():
    at = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    event = command_event(
        CommandExecutionEvent(
            external_execution_id="x",
            command_execution_id="capexec:e1:n1",
            status=CommandExecutionStatus.RUNNING,
            sn="SN-1",
            command_id="vendor.acme.survey",
            progress=0.5,
            message="halfway",
            output={"photos": 3},
            occurred_at=at,
        )
    )

    assert event.command_execution_id == "capexec:e1:n1"
    assert event.state == command_pb2.COMMAND_STATE_RUNNING
    assert event.occurred_at.ToDatetime(tzinfo=timezone.utc) == at
    assert event.progress == 0.5
    assert event.message == "halfway"
    assert event.result["photos"] == 3
    assert event.asset.sn == "SN-1"


def test_a_failure_carries_an_error():
    event = command_event(
        CommandExecutionEvent(
            external_execution_id="x", status=CommandExecutionStatus.FAILED, sn="SN-1", message="motor fault"
        )
    )

    assert event.state == command_pb2.COMMAND_STATE_FAILED
    assert event.error.message == "motor fault"
    assert event.error.HasField("occurred_at")


def test_nan_progress_is_left_out():
    event = command_event(
        CommandExecutionEvent(
            external_execution_id="x", status=CommandExecutionStatus.RUNNING, sn="SN-1", progress=float("nan")
        )
    )

    assert not event.HasField("progress")


async def test_an_accepted_v3_command_maps_the_adapters_id_to_the_platforms():
    adapter = _Adapter()
    request = edge_v3.ExecuteCommandRequest(
        context=common_pb2.RequestContext(request_id="req-1"),
        command=command_pb2.Command(
            asset=common_pb2.AssetRef(sn="SN-1"), command_id="vendor.acme.survey", params=struct_pb2.Struct()
        ),
        command_execution_id="capexec:e1:n7",
    )

    response = await EdgeAdapterV3Servicer(adapter).ExecuteCommand(request, None)
    event = command_event(
        CommandExecutionEvent(external_execution_id="vendor-9", status=CommandExecutionStatus.SUCCEEDED)
    )

    assert response.result.state == command_pb2.COMMAND_STATE_ACCEPTED
    assert adapter.seen_ids == ["capexec:e1:n7"]
    assert event.command_execution_id == "capexec:e1:n7"
    assert event.command_id == "vendor.acme.survey"
    assert event.asset.sn == "SN-1"


def test_an_unknown_id_is_sent_as_the_adapters_own():
    event = command_event(
        CommandExecutionEvent(external_execution_id="vendor-1", status=CommandExecutionStatus.SUCCEEDED, sn="SN-1")
    )

    assert event.command_execution_id == "vendor-1"


def test_runs_are_bounded():
    for i in range(CommandRuns.MAX_ENTRIES + 5):
        CommandRuns.remember(f"v-{i}", f"c-{i}", "x", "SN")

    assert CommandRuns.lookup("v-0") is None
    assert CommandRuns.lookup(f"v-{CommandRuns.MAX_ENTRIES + 4}").command_execution_id == (
        f"c-{CommandRuns.MAX_ENTRIES + 4}"
    )


def test_v3_unavailability_is_remembered_for_the_window_then_retried():
    now = [100.0]
    fallback = V3Fallback("svc", clock=lambda: now[0])

    fallback.mark_unavailable()
    assert not fallback.available()
    assert not V3Fallback("svc", clock=lambda: now[0]).available()

    now[0] += V3Fallback.WINDOW_SECONDS
    assert fallback.available()

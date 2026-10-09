"""
Conformance kit for adapter test suites::

    from edge_sdk.testing import assert_conformant

    async def test_adapter_is_conformant():
        await assert_conformant(MyAdapter(fake_device), sn="SIM-1")

Checks: every advertised (AVAILABLE) id is executable, every executable id is advertised, every
schema parses and accepts a minimal example, telemetry field keys are unique, and a completion
event built by the SDK carries ``occurred_at``. ``execute=True`` also runs each advertised command
through v3 ``ExecuteCommand`` with minimal params -- only against a fake or simulated device.

:class:`RecordingGateway` stands in for the platform in adapter tests and records what the adapter
publishes (``NotificationPublisher(..., gateway=RecordingGateway())``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.protobuf import struct_pb2

from .adapter.base import _STREAMING_COMMANDS, EdgeAdapter
from .adapter.validation import check_schema, example_params, validate_params
from .client.edge_gateway import EdgeGatewayClient, command_event
from .models.common import INVALID_PARAMS_CODE, Capabilities, CapabilityState, CommandExecutionStatus
from .models.notification import CommandExecutionEvent


@dataclass
class ConformanceReport:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def __str__(self) -> str:
        if self.ok:
            return "conformant"
        return "not conformant:\n" + "\n".join(f"  - {p}" for p in self.problems)


async def check_conformance(adapter: EdgeAdapter, sn: str = "CONFORMANCE-1", *, execute: bool = False):
    report = ConformanceReport()
    caps = await adapter.get_capabilities(sn=sn, asset_id=None)
    advertised = {c.command_id: c for c in caps.capabilities}
    available = {
        command_id
        for command_id, c in advertised.items()
        if c.state == CapabilityState.AVAILABLE and command_id not in _STREAMING_COMMANDS
    }
    listed = {command_id for command_id, c in advertised.items() if c.state != CapabilityState.UNSUPPORTED}
    executable = adapter.executable_command_ids()
    routes_itself = adapter._is_overridden("send_custom_command")

    if not routes_itself:
        for command_id in sorted(available - executable):
            report.problems.append(f"{command_id} is advertised but has no handler")
    for command_id in sorted(executable - listed):
        report.problems.append(f"{command_id} is executable but not advertised")

    for command_id, c in sorted(advertised.items()):
        _check_schemas(report, command_id, c.input_schema, c.output_schema)

    keys = [f.key for f in caps.telemetry_fields]
    for key in sorted({k for k in keys if keys.count(k) > 1}):
        report.problems.append(f"telemetry field {key} is declared more than once")
    if any(not k for k in keys):
        report.problems.append("a telemetry field has no key")

    event = command_event(
        CommandExecutionEvent(external_execution_id="conformance", status=CommandExecutionStatus.SUCCEEDED, sn=sn)
    )
    if not event.HasField("occurred_at"):
        report.problems.append("a completion event goes out without occurred_at")

    if execute:
        await _execute_all(report, adapter, sn, advertised, available)
    return report


async def assert_conformant(adapter: EdgeAdapter, sn: str = "CONFORMANCE-1", *, execute: bool = False) -> None:
    report = await check_conformance(adapter, sn, execute=execute)
    assert report.ok, str(report)


def _check_schemas(report: ConformanceReport, command_id: str, input_schema, output_schema) -> None:
    for kind, schema in (("input", input_schema), ("output", output_schema)):
        if schema is None:
            continue
        problems = check_schema(schema, f"{command_id} {kind} schema")
        report.problems.extend(problems)
        if problems:
            continue
        if schema.get("type") != "object":
            report.problems.append(f"{command_id} {kind} schema must describe an object")
            continue
        try:
            struct_pb2.Struct().update(schema)
        except (TypeError, ValueError) as exc:
            report.problems.append(f"{command_id} {kind} schema does not fit a protobuf Struct: {exc}")
            continue
        if kind == "input":
            checked = validate_params(schema, example_params(schema))
            if not checked.valid:
                report.problems.append(f"{command_id} input schema rejects its own minimal example: {checked.message}")


async def _execute_all(report, adapter, sn, advertised, available) -> None:
    from google.protobuf import struct_pb2 as struct
    from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
    from zqnt_utils.generated.zqnt.common.v3 import common_pb2
    from zqnt_utils.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3

    from .server.edge_server_v3 import NOT_SUPPORTED_CODE, EdgeAdapterV3Servicer

    servicer = EdgeAdapterV3Servicer(adapter)
    for command_id in sorted(available):
        params = struct.Struct()
        params.update(example_params(advertised[command_id].input_schema))
        request = edge_v3.ExecuteCommandRequest(
            context=common_pb2.RequestContext(request_id="conformance"),
            command=command_pb2.Command(asset=common_pb2.AssetRef(sn=sn), command_id=command_id, params=params),
            command_execution_id=f"conformance:{command_id}",
        )
        result = (await servicer.ExecuteCommand(request, None)).result
        if result.state == command_pb2.COMMAND_STATE_REJECTED and result.error.code in (
            NOT_SUPPORTED_CODE,
            INVALID_PARAMS_CODE,
        ):
            report.problems.append(f"{command_id} is advertised but ExecuteCommand refused it: {result.error.message}")


class RecordingGateway(EdgeGatewayClient):
    """Records command events and capability reports instead of sending them."""

    def __init__(self) -> None:
        super().__init__(host="recording", port=0, token="")
        self.events: list = []
        self.capabilities: list[Capabilities] = []

    async def publish_command_event(self, event: CommandExecutionEvent) -> bool:
        self.events.append(command_event(event))
        return True

    async def report_capabilities(self, caps: Capabilities) -> str:
        self.capabilities.append(caps)
        return str(len(self.capabilities))

    def assert_events_complete(self) -> None:
        for event in self.events:
            assert event.HasField("occurred_at"), f"event for {event.command_execution_id} has no occurred_at"
            assert event.command_execution_id, "event without command_execution_id"
            assert event.asset.sn, f"event for {event.command_execution_id} has no asset serial"

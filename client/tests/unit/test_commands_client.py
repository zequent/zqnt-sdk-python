"""``CommandsClient`` against an in-process fake ``zqnt.control.v3.RemoteControlService``."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import grpc
import grpc.aio
import pytest
from google.protobuf import timestamp_pb2
from zqnt_utils.generated.zqnt.capability.v3 import capability_pb2, command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2
from zqnt_utils.generated.zqnt.control.v3 import remote_control_service_pb2 as control_pb2
from zqnt_utils.generated.zqnt.control.v3 import remote_control_service_pb2_grpc as control_pb2_grpc

from client_sdk import CommandError, ZequentClient
from client_sdk.commands import CommandsClient, to_dict, to_struct
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


def _event(execution_id: str, state: int, **result) -> command_pb2.CommandEvent:
    event = command_pb2.CommandEvent(
        command_execution_id=execution_id,
        command_id="navigation.go_to",
        asset=common_pb2.AssetRef(sn="DRONE-1"),
        state=state,
        occurred_at=timestamp_pb2.Timestamp(seconds=1_760_000_000),
    )
    if result:
        event.result.CopyFrom(to_struct(result))
    return event


class FakeRemoteControlV3(control_pb2_grpc.RemoteControlServiceServicer):
    def __init__(self) -> None:
        self.requests: dict[str, object] = {}
        self.metadata: dict[str, str] = {}
        self.refuse_with: tuple[grpc.StatusCode, str] | None = None
        self.answer_with: command_pb2.CommandResult | None = None
        self.asset_watch_cancelled = asyncio.Event()
        self.asset_watch_open = asyncio.Event()
        self.asset_watches: list[asyncio.Queue] = []
        self.events_on_execute: list[command_pb2.CommandEvent] = []
        self.received: list[str] = []

    async def _refused(self, context) -> bool:
        self.metadata = dict(context.invocation_metadata())
        if self.refuse_with is None:
            return False
        await context.abort(*self.refuse_with)
        return True

    async def GetCapabilities(self, request, context):  # noqa: N802
        self.requests["GetCapabilities"] = request
        await self._refused(context)
        return control_pb2.GetCapabilitiesResponse(
            capabilities=capability_pb2.CapabilitySet(
                asset_sn=request.asset.sn,
                capabilities=[
                    capability_pb2.Capability(command_id="flight.takeoff"),
                    capability_pb2.Capability(command_id="navigation.go_to"),
                ],
            )
        )

    async def ExecuteCommand(self, request, context):  # noqa: N802
        self.requests["ExecuteCommand"] = request
        self.received.append("ExecuteCommand")
        await self._refused(context)
        for event in self.events_on_execute:
            for watch in self.asset_watches:
                watch.put_nowait(event)
        result = self.answer_with or command_pb2.CommandResult(
            command_execution_id="exec-1",
            command_id=request.command.command_id,
            state=command_pb2.COMMAND_STATE_ACCEPTED,
        )
        return control_pb2.ExecuteCommandResponse(result=result)

    async def CancelCommand(self, request, context):  # noqa: N802
        self.requests["CancelCommand"] = request
        await self._refused(context)
        return control_pb2.CancelCommandResponse(
            result=command_pb2.CommandResult(
                command_execution_id=request.command_execution_id,
                state=command_pb2.COMMAND_STATE_CANCELLED,
            )
        )

    async def WatchCommandEvents(self, request, context):  # noqa: N802
        self.requests["WatchCommandEvents"] = request
        self.received.append("WatchCommandEvents")
        await self._refused(context)
        if request.command_execution_id:
            yield control_pb2.WatchCommandEventsResponse(
                event=_event(request.command_execution_id, command_pb2.COMMAND_STATE_RUNNING)
            )
            yield control_pb2.WatchCommandEventsResponse(
                event=_event(request.command_execution_id, command_pb2.COMMAND_STATE_SUCCEEDED, arrived=True)
            )
            return
        events: asyncio.Queue = asyncio.Queue()
        self.asset_watches.append(events)
        context.add_done_callback(lambda _ctx: self.asset_watch_cancelled.set())
        self.asset_watch_open.set()
        yield control_pb2.WatchCommandEventsResponse(event=_event("exec-2", command_pb2.COMMAND_STATE_RUNNING))
        while True:
            yield control_pb2.WatchCommandEventsResponse(event=await events.get())


@pytest.fixture
async def fake():
    servicer = FakeRemoteControlV3()
    server = grpc.aio.server()
    control_pb2_grpc.add_RemoteControlServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    servicer.port = port
    yield servicer
    await server.stop(None)


@pytest.fixture
async def client(fake):
    config = ServiceConfig("remote-control", host="127.0.0.1", port=fake.port)
    async with ZequentClient(
        connector_config=config,
        remote_control_config=config,
        mission_autonomy_config=config,
        live_data_config=config,
        resilience=ResilienceConfig(max_retry_attempts=0, request_timeout_seconds=5),
        client_token="test-token",
    ) as zequent:
        yield zequent.commands


async def test_lists_the_capabilities_of_an_asset(client: CommandsClient, fake: FakeRemoteControlV3):
    capabilities = await client.list_capabilities("DRONE-1")

    assert fake.requests["GetCapabilities"].asset.sn == "DRONE-1"
    assert fake.requests["GetCapabilities"].context.request_id
    assert [c.command_id for c in capabilities.capabilities] == ["flight.takeoff", "navigation.go_to"]
    assert fake.metadata["authorization"] == "Bearer test-token"


async def test_executes_a_command_by_id_with_its_params(client: CommandsClient, fake: FakeRemoteControlV3):
    result = await client.execute_command(
        "DRONE-1",
        "navigation.go_to",
        {"latitude": 52.52, "longitude": 13.405, "altitude": 40, "speed": None},
    )

    sent = fake.requests["ExecuteCommand"]
    assert sent.command.asset.sn == "DRONE-1"
    assert sent.command.command_id == "navigation.go_to"
    assert to_dict(sent.command.params) == {"latitude": 52.52, "longitude": 13.405, "altitude": 40.0}
    assert sent.context.idempotency_key
    assert not sent.no_fly_zone_override
    assert result.state == command_pb2.COMMAND_STATE_ACCEPTED
    assert result.command_execution_id == "exec-1"


async def test_sends_the_options_of_a_command(client: CommandsClient, fake: FakeRemoteControlV3):
    await client.execute_command(
        None,
        "camera.change_zoom",
        {"zoom": 4, "lens": "zoom"},
        asset_id="asset-uuid",
        target=capability_pb2.Target(type=capability_pb2.TARGET_TYPE_PAYLOAD, ref="payload-0"),
        timeout=timedelta(seconds=90),
        reason="inspect the roof",
        no_fly_zone_override=True,
        idempotency_key="key-1",
    )

    sent = fake.requests["ExecuteCommand"]
    assert sent.command.asset.id == "asset-uuid"
    assert sent.command.asset.sn == ""
    assert sent.command.target.ref == "payload-0"
    assert sent.command.timeout.seconds == 90
    assert sent.reason == "inspect the roof"
    assert sent.no_fly_zone_override
    assert sent.context.idempotency_key == "key-1"


async def test_a_rejected_command_raises_its_category_and_code(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.answer_with = command_pb2.CommandResult(
        command_id="flight.takeoff",
        state=command_pb2.COMMAND_STATE_REJECTED,
        error=common_pb2.Error(
            category=common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
            code="command.invalid_params",
            message="altitude must be a number",
        ),
    )

    with pytest.raises(CommandError) as raised:
        await client.execute_command("DRONE-1", "flight.takeoff", {"altitude": "high"})

    assert raised.value.category == common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT
    assert raised.value.category_name == "ERROR_CATEGORY_INVALID_ARGUMENT"
    assert raised.value.code == "command.invalid_params"
    assert str(raised.value) == "altitude must be a number"
    assert raised.value.status is None
    assert raised.value.result.state == command_pb2.COMMAND_STATE_REJECTED


@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (grpc.StatusCode.INVALID_ARGUMENT, common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT, False),
        (grpc.StatusCode.PERMISSION_DENIED, common_pb2.ERROR_CATEGORY_PERMISSION_DENIED, False),
        (grpc.StatusCode.FAILED_PRECONDITION, common_pb2.ERROR_CATEGORY_PRECONDITION_FAILED, False),
        (grpc.StatusCode.UNAVAILABLE, common_pb2.ERROR_CATEGORY_SERVICE, True),
    ],
)
async def test_a_refused_call_raises_the_matching_category(
    client: CommandsClient, fake: FakeRemoteControlV3, status, category, retryable
):
    fake.refuse_with = (status, "refused by the fake")

    with pytest.raises(CommandError) as raised:
        await client.execute_command("DRONE-1", "flight.takeoff")

    assert raised.value.category == category
    assert raised.value.status == status
    assert raised.value.retryable is retryable
    assert "refused by the fake" in str(raised.value)


async def test_a_failed_run_is_a_result_not_an_exception(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.answer_with = command_pb2.CommandResult(
        command_execution_id="exec-9",
        command_id="flight.takeoff",
        state=command_pb2.COMMAND_STATE_FAILED,
        error=common_pb2.Error(category=common_pb2.ERROR_CATEGORY_ASSET, code="flight.not_airborne"),
    )

    result = await client.execute_command("DRONE-1", "flight.takeoff")

    assert result.state == command_pb2.COMMAND_STATE_FAILED
    assert result.error.code == "flight.not_airborne"


async def test_cancels_a_command_run(client: CommandsClient, fake: FakeRemoteControlV3):
    result = await client.cancel_command("exec-1", "operator abort")

    assert fake.requests["CancelCommand"].command_execution_id == "exec-1"
    assert fake.requests["CancelCommand"].reason == "operator abort"
    assert result.state == command_pb2.COMMAND_STATE_CANCELLED


async def test_watches_one_run_until_its_terminal_event(client: CommandsClient, fake: FakeRemoteControlV3):
    events = [event async for event in client.watch_command("exec-1")]

    assert fake.requests["WatchCommandEvents"].command_execution_id == "exec-1"
    assert [e.state for e in events] == [command_pb2.COMMAND_STATE_RUNNING, command_pb2.COMMAND_STATE_SUCCEEDED]
    assert to_dict(events[-1].result) == {"arrived": True}


async def test_watches_an_asset_until_the_loop_is_left(client: CommandsClient, fake: FakeRemoteControlV3):
    events = client.watch_asset("DRONE-1")
    first = await anext(events)
    await events.aclose()

    assert fake.requests["WatchCommandEvents"].asset.sn == "DRONE-1"
    assert first.command_execution_id == "exec-2"
    await asyncio.wait_for(fake.asset_watch_cancelled.wait(), timeout=5)


async def test_a_refused_watch_raises(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.refuse_with = (grpc.StatusCode.INVALID_ARGUMENT, "give either command_execution_id or asset.sn")

    with pytest.raises(CommandError) as raised:
        async for _ in client.watch_command("exec-1"):
            pass

    assert raised.value.category == common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT


async def test_an_asset_and_a_command_id_are_required(client: CommandsClient):
    with pytest.raises(ValueError):
        await client.execute_command(" ", "flight.takeoff")
    with pytest.raises(ValueError):
        await client.execute_command("DRONE-1", "")
    with pytest.raises(ValueError):
        await client.list_capabilities("")


async def test_execute_and_wait_returns_the_succeeded_result(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.events_on_execute = [
        _event("exec-1", command_pb2.COMMAND_STATE_RUNNING),
        _event("exec-1", command_pb2.COMMAND_STATE_SUCCEEDED, arrived=True),
    ]

    async with asyncio.timeout(5):
        result = await client.execute_and_wait("DRONE-1", "navigation.go_to", {"latitude": 52.52})

    assert result.state == command_pb2.COMMAND_STATE_SUCCEEDED
    assert result.command_execution_id == "exec-1"
    assert to_dict(result.result) == {"arrived": True}
    assert fake.requests["WatchCommandEvents"].asset.sn == "DRONE-1"
    await asyncio.wait_for(fake.asset_watch_cancelled.wait(), timeout=5)


async def test_execute_and_wait_raises_the_final_result_of_a_failed_run(
    client: CommandsClient, fake: FakeRemoteControlV3
):
    failed = _event("exec-1", command_pb2.COMMAND_STATE_FAILED)
    failed.error.CopyFrom(common_pb2.Error(code="flight.not_airborne", message="not airborne"))
    fake.events_on_execute = [failed]

    with pytest.raises(CommandError) as raised:
        async with asyncio.timeout(5):
            await client.execute_and_wait("DRONE-1", "navigation.go_to")

    assert raised.value.result.state == command_pb2.COMMAND_STATE_FAILED
    assert raised.value.result.command_execution_id == "exec-1"
    assert raised.value.category == common_pb2.ERROR_CATEGORY_ASSET
    assert raised.value.code == "flight.not_airborne"
    assert str(raised.value) == "not airborne"
    await asyncio.wait_for(fake.asset_watch_cancelled.wait(), timeout=5)


async def test_execute_and_wait_raises_a_rejection_without_waiting(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.answer_with = command_pb2.CommandResult(
        command_id="flight.takeoff",
        state=command_pb2.COMMAND_STATE_REJECTED,
        error=common_pb2.Error(code="command.invalid_params"),
    )

    with pytest.raises(CommandError) as raised:
        async with asyncio.timeout(5):
            await client.execute_and_wait("DRONE-1", "flight.takeoff")

    assert raised.value.category == common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT
    assert raised.value.result.state == command_pb2.COMMAND_STATE_REJECTED


async def test_execute_and_wait_ignores_events_of_other_runs(client: CommandsClient, fake: FakeRemoteControlV3):
    fake.events_on_execute = [
        _event("exec-7", command_pb2.COMMAND_STATE_FAILED),
        _event("exec-1", command_pb2.COMMAND_STATE_SUCCEEDED),
    ]

    async with asyncio.timeout(5):
        result = await client.execute_and_wait("DRONE-1", "navigation.go_to")

    assert result.command_execution_id == "exec-1"
    assert result.state == command_pb2.COMMAND_STATE_SUCCEEDED


async def test_execute_and_wait_sees_an_outcome_that_arrives_before_the_reply(
    client: CommandsClient, fake: FakeRemoteControlV3
):
    fake.events_on_execute = [_event("exec-1", command_pb2.COMMAND_STATE_SUCCEEDED)]

    async with asyncio.timeout(5):
        result = await client.execute_and_wait("DRONE-1", "navigation.go_to")

    assert fake.received == ["WatchCommandEvents", "ExecuteCommand"]
    assert result.state == command_pb2.COMMAND_STATE_SUCCEEDED


async def test_execute_and_wait_closes_the_watch_on_the_callers_timeout(
    client: CommandsClient, fake: FakeRemoteControlV3
):
    fake.events_on_execute = [_event("exec-1", command_pb2.COMMAND_STATE_RUNNING)]

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.5):
            await client.execute_and_wait("DRONE-1", "navigation.go_to")

    await asyncio.wait_for(fake.asset_watch_cancelled.wait(), timeout=5)


def test_params_round_trip_through_a_struct():
    params = {"waypoints": [{"latitude": 1.5}], "enabled": True, "mode": "cool", "unset": None}

    assert to_dict(to_struct(params)) == {"waypoints": [{"latitude": 1.5}], "enabled": True, "mode": "cool"}

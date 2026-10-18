"""``SimulationsClient`` against an in-process fake ``zqnt.application_simulation.v3.SimulationService``."""

from __future__ import annotations

import grpc
import grpc.aio
import pytest
from google.protobuf import struct_pb2
from zqnt_api.generated.zqnt.application_simulation.v3 import (
    application_simulation_pb2 as sim_pb2,
)
from zqnt_api.generated.zqnt.application_simulation.v3 import (
    application_simulation_pb2_grpc as sim_pb2_grpc,
)
from zqnt_api.generated.zqnt.common.v3 import common_pb2

from client_sdk import CommandError, SimulationsClient, ZequentClient
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


def _trace(execution_id: str, status: int) -> sim_pb2.SimulationTrace:
    output = struct_pb2.Struct()
    output.update({"battery_percent": 18})
    return sim_pb2.SimulationTrace(
        execution_id=execution_id,
        status=status,
        asset_sn="VIRTUAL-exec-1-DRONE-1",
        fast_forward=True,
        steps=[
            sim_pb2.TraceStep(
                node_id="takeoff",
                command_id="flight.takeoff",
                status=sim_pb2.NODE_STATUS_FAILED,
                output=output,
                next=[
                    sim_pb2.TraceTransition(
                        target_node_id="return",
                        edge_type=sim_pb2.EDGE_TYPE_FAILURE,
                        reason="failed: flight.not_airborne",
                    )
                ],
                simulated_by="scenario: failure",
            )
        ],
        skipped_node_ids=["land"],
    )


class FakeSimulations(sim_pb2_grpc.SimulationServiceServicer):
    def __init__(self) -> None:
        self.start: sim_pb2.StartSimulationRequest | None = None
        self.trace_request: sim_pb2.GetSimulationTraceRequest | None = None
        self.cancel: sim_pb2.CancelSimulationRequest | None = None
        self.refuse_with: tuple[grpc.StatusCode, str] | None = None
        self.statuses: list[int] = []
        self.trace_calls = 0

    async def StartSimulation(self, request, context):  # noqa: N802
        self.start = request
        return sim_pb2.StartSimulationResponse(execution_id="exec-1", status=sim_pb2.SIMULATION_STATUS_RUNNING)

    async def GetSimulationTrace(self, request, context):  # noqa: N802
        self.trace_request = request
        self.trace_calls += 1
        if self.refuse_with is not None:
            await context.abort(*self.refuse_with)
        if len(self.statuses) > 1:
            status = self.statuses.pop(0)
        else:
            status = self.statuses[0] if self.statuses else sim_pb2.SIMULATION_STATUS_RUNNING
        return sim_pb2.GetSimulationTraceResponse(trace=_trace(request.execution_id, status))

    async def CancelSimulation(self, request, context):  # noqa: N802
        self.cancel = request
        return sim_pb2.CancelSimulationResponse(status=sim_pb2.SIMULATION_STATUS_CANCELLING)


@pytest.fixture
async def fake():
    servicer = FakeSimulations()
    server = grpc.aio.server()
    sim_pb2_grpc.add_SimulationServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    servicer.port = port
    yield servicer
    await server.stop(None)


@pytest.fixture
async def client(fake):
    config = ServiceConfig("mission-autonomy", host="127.0.0.1", port=fake.port)
    async with ZequentClient(
        connector_config=config,
        remote_control_config=config,
        mission_autonomy_config=config,
        live_data_config=config,
        resilience=ResilienceConfig(max_retry_attempts=0, request_timeout_seconds=5),
        client_token="test-token",
    ) as zequent:
        yield zequent.simulations


async def test_start_generates_an_idempotency_key_when_the_caller_gives_none(
    client: SimulationsClient, fake: FakeSimulations
):
    request = sim_pb2.StartSimulationRequest(
        application_id="app-1",
        nodes=[
            sim_pb2.NodeScenario(
                command_id="flight.takeoff",
                outcome=sim_pb2.NODE_OUTCOME_FAILURE,
                error_code="flight.not_airborne",
            )
        ],
        fleet=[sim_pb2.VirtualAsset(sn="DRONE-1", battery_percent=18)],
    )

    started = await client.start_simulation(request)

    assert started.execution_id == "exec-1"
    assert started.status == sim_pb2.SIMULATION_STATUS_RUNNING
    assert fake.start.context.idempotency_key
    assert fake.start.context.request_id
    assert list(fake.start.nodes) == list(request.nodes)
    assert list(fake.start.fleet) == list(request.fleet)
    assert not request.context.idempotency_key


async def test_start_keeps_the_callers_idempotency_key(client: SimulationsClient, fake: FakeSimulations):
    await client.start_simulation(
        sim_pb2.StartSimulationRequest(
            context=common_pb2.RequestContext(idempotency_key="retry-me"), application_id="app-1"
        )
    )

    assert fake.start.context.idempotency_key == "retry-me"


async def test_start_without_an_application_is_refused_before_it_is_sent(
    client: SimulationsClient, fake: FakeSimulations
):
    with pytest.raises(ValueError):
        await client.start_simulation(sim_pb2.StartSimulationRequest())

    assert fake.start is None


async def test_trace_is_the_one_the_platform_answers(client: SimulationsClient, fake: FakeSimulations):
    fake.statuses = [sim_pb2.SIMULATION_STATUS_FAILED]

    trace = await client.simulation_trace("exec-1")

    assert fake.trace_request.execution_id == "exec-1"
    assert trace == _trace("exec-1", sim_pb2.SIMULATION_STATUS_FAILED)
    assert trace.steps[0].next[0].edge_type == sim_pb2.EDGE_TYPE_FAILURE


async def test_cancel_returns_the_status(client: SimulationsClient, fake: FakeSimulations):
    status = await client.cancel_simulation("exec-1")

    assert fake.cancel.execution_id == "exec-1"
    assert status == sim_pb2.SIMULATION_STATUS_CANCELLING


async def test_an_unknown_run_raises_not_found(client: SimulationsClient, fake: FakeSimulations):
    fake.refuse_with = (grpc.StatusCode.NOT_FOUND, "no simulation exec-9")

    with pytest.raises(CommandError) as raised:
        await client.simulation_trace("exec-9")

    assert raised.value.status == grpc.StatusCode.NOT_FOUND


async def test_wait_polls_until_the_run_has_ended(client: SimulationsClient, fake: FakeSimulations):
    fake.statuses = [
        sim_pb2.SIMULATION_STATUS_PENDING,
        sim_pb2.SIMULATION_STATUS_RUNNING,
        sim_pb2.SIMULATION_STATUS_CANCELLING,
        sim_pb2.SIMULATION_STATUS_CANCELLED,
    ]

    trace = await client.wait_for_simulation("exec-1", interval=0.01, timeout=5)

    assert trace.status == sim_pb2.SIMULATION_STATUS_CANCELLED
    assert fake.trace_calls == 4


async def test_wait_raises_timeout_while_the_run_keeps_going(client: SimulationsClient, fake: FakeSimulations):
    with pytest.raises(CommandError) as raised:
        await client.wait_for_simulation("exec-1", interval=0.01, timeout=0.1)

    assert raised.value.category == common_pb2.ERROR_CATEGORY_TIMEOUT
    assert fake.cancel is None


async def test_simulate_starts_and_waits_for_the_trace(client: SimulationsClient, fake: FakeSimulations):
    fake.statuses = [sim_pb2.SIMULATION_STATUS_RUNNING, sim_pb2.SIMULATION_STATUS_SUCCEEDED]

    trace = await client.simulate(sim_pb2.StartSimulationRequest(application_id="app-1"), interval=0.01, timeout=5)

    assert fake.trace_request.execution_id == "exec-1"
    assert trace.status == sim_pb2.SIMULATION_STATUS_SUCCEEDED

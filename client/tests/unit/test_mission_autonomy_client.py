"""Unit tests for ``MissionAutonomyClient``."""

from __future__ import annotations

from typing import Any

import pytest

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.generated import common_pb2, mission_autonomy_pb2
from client_sdk.mission_autonomy.client import MissionAutonomyClient
from client_sdk.models.enums import MissionStatus, MissionType, TaskStatus, TaskType
from client_sdk.models.mission_autonomy import MissionDTO, SchedulerDTO, TaskDTO
from client_sdk.models.task_config import WaypointDTO, WaypointTaskConfig


def _ok_mission_response() -> mission_autonomy_pb2.MissionResponse:
    return mission_autonomy_pb2.MissionResponse(
        hasErrors=False,
        tid="tid-1",
        missionId="m1",
        missionDTO=common_pb2.MissionProtoDTO(
            id="m1",
            name="m",
            status=common_pb2.MissionStatus.OPERATION_DRAFT,
            type=common_pb2.MissionType.STANDARD,
        ),
    )


def _ok_task_response(task_id: str = "t1") -> mission_autonomy_pb2.TaskResponse:
    return mission_autonomy_pb2.TaskResponse(
        hasErrors=False,
        tid="tid-2",
        taskId=task_id,
        taskDTO=common_pb2.TaskProtoDTO(
            id=task_id,
            missionId="m1",
            taskType=common_pb2.TaskTypeProto.TASK_TYPE_WAYPOINT,
            status=common_pb2.TaskStatus.TASK_DRAFT,
        ),
    )


def _ok_start_task_response(task_id: str = "t1") -> mission_autonomy_pb2.StartTaskResponse:
    from google.protobuf import empty_pb2
    return mission_autonomy_pb2.StartTaskResponse(
        hasErrors=False, tid="tid-s", taskId=task_id, empty=empty_pb2.Empty()
    )


def _ok_stop_task_response(task_id: str = "t1") -> mission_autonomy_pb2.StopTaskResponse:
    from google.protobuf import empty_pb2
    return mission_autonomy_pb2.StopTaskResponse(
        hasErrors=False, tid="tid-s2", taskId=task_id, empty=empty_pb2.Empty()
    )


def _ok_scheduler_response() -> mission_autonomy_pb2.SchedulerResponse:
    return mission_autonomy_pb2.SchedulerResponse(
        hasErrors=False,
        tid="tid-3",
        schedulerId="s1",
        schedulerDTO=common_pb2.SchedulerProtoDTO(
            id="s1",
            missionId="m1",
            taskId="t1",
        ),
    )


class _FakeStub:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001
            self.calls[name] = (request, timeout)
            return self._response

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


def _client(stub: Any) -> MissionAutonomyClient:
    c = MissionAutonomyClient.__new__(MissionAutonomyClient)
    c._channel = None
    c._resilience = ResilienceConfig()
    from client_sdk.grpc_.resilience import GrpcResilience
    c._resilience_helper = GrpcResilience(c._resilience)
    c._stub = stub
    return c


# ---------------------------------------------------------------------------
# Mission CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_mission_round_trips() -> None:
    stub = _FakeStub(_ok_mission_response())
    c = _client(stub)
    resp = await c.create_mission(
        MissionDTO(
            name="m",
            id="m1",
            status=MissionStatus.DRAFT,
            type=MissionType.STANDARD,
        )
    )
    assert resp.success is True
    assert resp.mission is not None
    assert resp.mission.id == "m1"
    assert "CreateMission" in stub.calls


@pytest.mark.asyncio
async def test_get_mission_validates_id() -> None:
    c = _client(_FakeStub(_ok_mission_response()))
    with pytest.raises(ValueError):
        await c.get_mission("")


@pytest.mark.asyncio
async def test_delete_mission_calls_rpc() -> None:
    stub = _FakeStub(_ok_mission_response())
    c = _client(stub)
    resp = await c.delete_mission("m1")
    assert resp.success is True
    assert "DeleteMission" in stub.calls


# ---------------------------------------------------------------------------
# Task CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_with_waypoint_config() -> None:
    stub = _FakeStub(_ok_task_response("t1"))
    c = _client(stub)

    task = TaskDTO(
        id="t1",
        mission_id="m1",
        task_type=TaskType.WAYPOINT,
        status=TaskStatus.DRAFT,
        sn_number="DOCK-1",
        config=WaypointTaskConfig(
            flight_id="flight-1",
            waypoints=[
                WaypointDTO(latitude=10.0, longitude=20.0, altitude=30.0),
                WaypointDTO(latitude=11.0, longitude=21.0, altitude=31.0),
            ],
            global_speed=5.0,
        ),
    )
    resp = await c.create_task(task)
    assert resp.success is True
    assert resp.task is not None
    assert resp.task.id == "t1"
    sent = stub.calls["CreateTask"][0]
    assert sent.taskDTO.taskType == common_pb2.TaskTypeProto.TASK_TYPE_WAYPOINT


@pytest.mark.asyncio
async def test_start_and_stop_task() -> None:
    # Build two stubs because StartTask and StopTask return different proto types.
    start_stub = _FakeStub(_ok_start_task_response("t1"))
    c1 = _client(start_stub)
    await c1.start_task("t1")
    assert "StartTask" in start_stub.calls

    stop_stub = _FakeStub(_ok_stop_task_response("t1"))
    c2 = _client(stop_stub)
    await c2.stop_task("t1")
    assert "StopTask" in stop_stub.calls


@pytest.mark.asyncio
async def test_get_task_by_flight_id_validates_input() -> None:
    c = _client(_FakeStub(_ok_task_response("t1")))
    with pytest.raises(ValueError):
        await c.get_task_by_flight_id("")


# ---------------------------------------------------------------------------
# Scheduler CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_scheduler() -> None:
    stub = _FakeStub(_ok_scheduler_response())
    c = _client(stub)
    resp = await c.create_scheduler(
        SchedulerDTO(
            name="daily",
            cron_expression="0 0 * * *",
            id="s1",
            mission_id="m1",
            task_id="t1",
        )
    )
    assert resp.success is True
    assert resp.scheduler is not None
    assert resp.scheduler.id == "s1"


@pytest.mark.asyncio
async def test_delete_scheduler() -> None:
    stub = _FakeStub(_ok_scheduler_response())
    c = _client(stub)
    resp = await c.delete_scheduler("s1")
    assert resp.success is True
    assert "DeleteScheduler" in stub.calls

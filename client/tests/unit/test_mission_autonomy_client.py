"""Unit tests for ``MissionAutonomyClient`` (Mission / Task / Scheduler), as it exists at the
1.3.0 wire contract this branch tracks. See this file's own main-branch counterpart for the
mirror-image cut (Application/SkillExecution real, Mission/Task stubbed)."""

from __future__ import annotations

from typing import Any

import pytest
from zqnt_utils.generated.zqnt import base_pb2
from zqnt_utils.generated.zqnt import (
    mission_autonomy_contracts_pb2 as mac,
)
from zqnt_utils.generated.zqnt import (
    mission_autonomy_dto_pb2 as mad,
)

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.mission_autonomy.client import MissionAutonomyClient
from client_sdk.models.enums import MissionStatus, MissionType, TaskStatus, TaskType
from client_sdk.models.mission_autonomy import MissionDTO, SchedulerDTO, TaskDTO


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


def _error_response(cls, **extra):
    return cls(
        has_errors=True,
        error=base_pb2.GlobalErrorMessage(error_message="boom", error_code=base_pb2.ErrorCode.ERROR_CODE_SERVICE),
        **extra,
    )


# ---------------------------------------------------------------------------
# Mission CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_mission_round_trips() -> None:
    mission = mad.MissionProtoDTO(id="m1", name="Perimeter sweep", status=1, type=0)
    stub = _FakeStub(mac.MissionResponse(has_errors=False, mission_id="m1", mission=mission))
    c = _client(stub)

    result = await c.create_mission(MissionDTO(name="Perimeter sweep"))

    assert result.success is True
    assert result.mission is not None
    assert result.mission.id == "m1"
    assert result.mission.name == "Perimeter sweep"
    sent = stub.calls["CreateMission"][0]
    assert sent.mission.name == "Perimeter sweep"


@pytest.mark.asyncio
async def test_create_mission_raises_on_error() -> None:
    stub = _FakeStub(_error_response(mac.MissionResponse))
    c = _client(stub)
    result = await c.create_mission(MissionDTO(name="m"))
    assert result.success is False
    assert result.error is not None
    assert result.error.error_message == "boom"


@pytest.mark.asyncio
async def test_get_mission_validates_id() -> None:
    c = _client(_FakeStub(mac.MissionResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.get_mission("")


@pytest.mark.asyncio
async def test_get_mission_passes_id() -> None:
    mission = mad.MissionProtoDTO(id="m1", status=2, type=1)
    stub = _FakeStub(mac.MissionResponse(has_errors=False, mission=mission))
    c = _client(stub)

    result = await c.get_mission("m1")
    assert result.mission is not None
    assert result.mission.status == MissionStatus.ACTIVE
    assert result.mission.type == MissionType.REMOTE_OPS
    assert stub.calls["GetMission"][0].mission_id == "m1"


@pytest.mark.asyncio
async def test_update_mission() -> None:
    mission = mad.MissionProtoDTO(id="m1", name="Renamed")
    stub = _FakeStub(mac.MissionResponse(has_errors=False, mission=mission))
    c = _client(stub)

    result = await c.update_mission("m1", MissionDTO(name="Renamed"))
    assert result.mission.name == "Renamed"
    sent = stub.calls["UpdateMission"][0]
    assert sent.mission_id == "m1"
    assert sent.mission.name == "Renamed"


@pytest.mark.asyncio
async def test_delete_mission() -> None:
    stub = _FakeStub(mac.MissionResponse(has_errors=False, mission_id="m1"))
    c = _client(stub)
    result = await c.delete_mission("m1")
    assert result.success is True
    assert stub.calls["DeleteMission"][0].mission_id == "m1"


# ---------------------------------------------------------------------------
# Task CRUD + lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_round_trips() -> None:
    task = mad.TaskProtoDTO(id="t1", name="Waypoint run", status=3, task_type=3, asset_id="a1")
    stub = _FakeStub(mac.TaskResponse(has_errors=False, task_id="t1", task=task))
    c = _client(stub)

    result = await c.create_task(TaskDTO(name="Waypoint run", task_type=TaskType.WAYPOINT))

    assert result.success is True
    assert result.task is not None
    assert result.task.id == "t1"
    assert result.task.status == TaskStatus.RUNNING
    sent = stub.calls["CreateTask"][0]
    assert sent.task.name == "Waypoint run"
    assert sent.task.task_type == 3


@pytest.mark.asyncio
async def test_create_task_reports_error() -> None:
    """Mission/Task/Scheduler responses report failure via ``success``/``error`` on the
    dataclass, same as this branch's Scheduler methods -- they never raise
    :class:`MissionAutonomyError` themselves (unlike main's Application/SkillExecution
    ``_unwrap``, which this branch has none of)."""
    stub = _FakeStub(_error_response(mac.TaskResponse))
    c = _client(stub)
    result = await c.create_task(TaskDTO())
    assert result.success is False
    assert result.error is not None
    assert result.error.error_message == "boom"


@pytest.mark.asyncio
async def test_get_task_validates_id() -> None:
    c = _client(_FakeStub(mac.TaskResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.get_task("")


@pytest.mark.asyncio
async def test_get_task_by_flight_id() -> None:
    task = mad.TaskProtoDTO(id="t1", status=3)
    stub = _FakeStub(mac.TaskResponse(has_errors=False, task=task))
    c = _client(stub)

    result = await c.get_task_by_flight_id("flight-42")
    assert result.task.id == "t1"
    assert stub.calls["GetTaskByFlightId"][0].flight_id == "flight-42"


@pytest.mark.asyncio
async def test_update_task() -> None:
    task = mad.TaskProtoDTO(id="t1", current_progress=50, status=3)
    stub = _FakeStub(mac.TaskResponse(has_errors=False, task=task))
    c = _client(stub)

    result = await c.update_task("t1", TaskDTO(current_progress=50))
    assert result.task.current_progress == 50
    sent = stub.calls["UpdateTask"][0]
    assert sent.task_id == "t1"


@pytest.mark.asyncio
async def test_delete_task() -> None:
    stub = _FakeStub(mac.TaskResponse(has_errors=False, task_id="t1"))
    c = _client(stub)
    result = await c.delete_task("t1")
    assert result.success is True
    assert stub.calls["DeleteTask"][0].task_id == "t1"


@pytest.mark.asyncio
async def test_task_lifecycle_operations() -> None:
    task = mad.TaskProtoDTO(id="t1", status=3)
    for op, method in [
        ("StartTask", "start_task"),
        ("StopTask", "stop_task"),
        ("PauseTask", "pause_task"),
        ("ResumeTask", "resume_task"),
    ]:
        stub = _FakeStub(mac.TaskResponse(has_errors=False, task=task))
        c = _client(stub)
        result = await getattr(c, method)("t1")
        assert result.task.id == "t1"
        assert op in stub.calls
        assert stub.calls[op][0].task_id == "t1"


@pytest.mark.asyncio
async def test_task_lifecycle_validates_id() -> None:
    c = _client(_FakeStub(mac.TaskResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.start_task("")


# ---------------------------------------------------------------------------
# Scheduler CRUD (Mission/Task-based shape at 1.3.0, not the mission-free one main uses)
# ---------------------------------------------------------------------------


def _ok_scheduler_response() -> mac.SchedulerResponse:
    return mac.SchedulerResponse(
        has_errors=False,
        tid="tid-3",
        scheduler_id="s1",
        scheduler=mad.SchedulerProtoDTO(
            id="s1",
            name="daily",
            cron_expression="0 0 * * *",
            mission_id="m1",
            task_id="t1",
        ),
    )


@pytest.mark.asyncio
async def test_create_scheduler() -> None:
    stub = _FakeStub(_ok_scheduler_response())
    c = _client(stub)
    resp = await c.create_scheduler(
        SchedulerDTO(
            name="daily",
            cron_expression="0 0 * * *",
            mission_id="m1",
            task_id="t1",
        )
    )
    assert resp.success is True
    assert resp.scheduler is not None
    assert resp.scheduler.id == "s1"
    assert resp.scheduler.mission_id == "m1"
    sent = stub.calls["CreateScheduler"][0]
    assert sent.scheduler.task_id == "t1"


@pytest.mark.asyncio
async def test_delete_scheduler() -> None:
    stub = _FakeStub(_ok_scheduler_response())
    c = _client(stub)
    resp = await c.delete_scheduler("s1")
    assert resp.success is True
    assert "DeleteScheduler" in stub.calls


@pytest.mark.asyncio
async def test_list_schedulers_returns_all() -> None:
    dto_list = mad.SchedulerProtoDTOList(
        scheduler_dto_list=[
            mad.SchedulerProtoDTO(id="s1", name="a", cron_expression="* * * * *"),
            mad.SchedulerProtoDTO(id="s2", name="b", cron_expression="* * * * *"),
        ]
    )
    stub = _FakeStub(mac.SchedulerResponse(has_errors=False, tid="t", scheduler_id="", schedulers=dto_list))
    c = _client(stub)

    resp = await c.list_schedulers()
    assert resp.schedulers is not None
    assert [s.id for s in resp.schedulers] == ["s1", "s2"]
    assert not stub.calls["ListSchedulers"][0].HasField("task_id")


@pytest.mark.asyncio
async def test_list_schedulers_filters_by_task_id() -> None:
    stub = _FakeStub(mac.SchedulerResponse(has_errors=False, tid="t", scheduler_id=""))
    c = _client(stub)
    await c.list_schedulers(task_id="t1")
    assert stub.calls["ListSchedulers"][0].task_id == "t1"


@pytest.mark.asyncio
async def test_create_and_delete_schedulers_batch() -> None:
    stub = _FakeStub(_ok_scheduler_response())
    c = _client(stub)
    await c.create_schedulers(
        [SchedulerDTO(name="a", cron_expression="* * * * *"), SchedulerDTO(name="b", cron_expression="* * * * *")]
    )
    assert len(stub.calls["CreateSchedulers"][0].schedulers) == 2

    stub2 = _FakeStub(_ok_scheduler_response())
    c2 = _client(stub2)
    await c2.delete_schedulers(["s1", "s2"])
    assert list(stub2.calls["DeleteSchedulers"][0].scheduler_ids) == ["s1", "s2"]


@pytest.mark.asyncio
async def test_create_scheduler_validates_name() -> None:
    c = _client(_FakeStub(_ok_scheduler_response()))
    with pytest.raises(ValueError):
        await c.create_scheduler(SchedulerDTO(name="", cron_expression="* * * * *"))


# ---------------------------------------------------------------------------
# No Application/SkillExecution surface on this branch (main/2.0.0-only -- capability-execution-
# *.proto don't exist at 1.3.0).
# ---------------------------------------------------------------------------


def test_client_has_no_application_skill_execution_methods() -> None:
    for name in (
        "upsert_application",
        "get_application",
        "list_applications",
        "delete_application",
        "create_skill_execution",
        "execute_skill",
        "get_skill_execution",
        "list_skill_executions",
        "start_skill_execution",
        "signal_skill_execution",
    ):
        assert not hasattr(MissionAutonomyClient, name)

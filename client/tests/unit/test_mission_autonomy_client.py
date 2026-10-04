"""Unit tests for ``MissionAutonomyClient`` (Application / SkillExecution / Scheduler)."""

from __future__ import annotations

from typing import Any

import pytest
from zqnt_utils.generated.zqnt import (
    base_pb2,
)
from zqnt_utils.generated.zqnt import (
    capability_execution_contracts_pb2 as exc,
)
from zqnt_utils.generated.zqnt import (
    capability_execution_dto_pb2 as execdto,
)
from zqnt_utils.generated.zqnt import (
    capability_execution_types_pb2 as exts,
)
from zqnt_utils.generated.zqnt import (
    mission_autonomy_contracts_pb2 as mac,
)
from zqnt_utils.generated.zqnt import (
    mission_autonomy_dto_pb2 as mad,
)

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.exceptions import LegacyOperationRemovedError, MissionAutonomyError
from client_sdk.mission_autonomy.client import MissionAutonomyClient
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
# Application admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_application_round_trips() -> None:
    app = execdto.ApplicationProtoDTO(id="app1", version="v1", name="App One")
    stub = _FakeStub(exc.ApplicationResponse(has_errors=False, application=app))
    c = _client(stub)

    result = await c.upsert_application(app, expected_revision="rev-1")

    assert result.id == "app1"
    sent = stub.calls["UpsertApplication"][0]
    assert sent.application.id == "app1"
    assert sent.expected_revision == "rev-1"


@pytest.mark.asyncio
async def test_upsert_application_raises_on_error() -> None:
    stub = _FakeStub(_error_response(exc.ApplicationResponse))
    c = _client(stub)
    with pytest.raises(MissionAutonomyError, match="boom"):
        await c.upsert_application(execdto.ApplicationProtoDTO(id="app1"))


@pytest.mark.asyncio
async def test_get_application_validates_id() -> None:
    c = _client(_FakeStub(exc.ApplicationResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.get_application("")


@pytest.mark.asyncio
async def test_get_application_passes_version() -> None:
    app = execdto.ApplicationProtoDTO(id="app1", version="v2")
    stub = _FakeStub(exc.ApplicationResponse(has_errors=False, application=app))
    c = _client(stub)

    result = await c.get_application("app1", version="v2")
    assert result.version == "v2"
    assert stub.calls["GetApplication"][0].version == "v2"


@pytest.mark.asyncio
async def test_list_applications_returns_page() -> None:
    apps = [execdto.ApplicationProtoDTO(id="a"), execdto.ApplicationProtoDTO(id="b")]
    stub = _FakeStub(
        exc.ApplicationListResponse(
            has_errors=False,
            result=exc.ApplicationList(applications=apps, next_page_token="page-2"),
        )
    )
    c = _client(stub)

    result, next_page_token = await c.list_applications(enabled_only=True, page_size=10)

    assert [a.id for a in result] == ["a", "b"]
    assert next_page_token == "page-2"
    assert stub.calls["ListApplications"][0].enabled_only is True
    assert stub.calls["ListApplications"][0].page_size == 10


@pytest.mark.asyncio
async def test_delete_application_raises_on_error() -> None:
    stub = _FakeStub(_error_response(exc.ApplicationResponse))
    c = _client(stub)
    with pytest.raises(MissionAutonomyError):
        await c.delete_application("app1")


@pytest.mark.asyncio
async def test_delete_application_succeeds_silently() -> None:
    stub = _FakeStub(exc.ApplicationResponse(has_errors=False))
    c = _client(stub)
    await c.delete_application("app1", version="v1", expected_revision="rev-1")
    sent = stub.calls["DeleteApplication"][0]
    assert sent.version == "v1"
    assert sent.expected_revision == "rev-1"


@pytest.mark.asyncio
async def test_promote_application_version() -> None:
    pointer = execdto.ApplicationEnvironmentPointerProtoDTO(
        application_id="app1",
        environment=exts.ApplicationEnvironmentProto.APPLICATION_ENVIRONMENT_PRODUCTION,
        version="v1",
    )
    stub = _FakeStub(
        exc.ApplicationEnvironmentsResponse(has_errors=False, result=exc.ApplicationEnvironmentList(pointers=[pointer]))
    )
    c = _client(stub)

    pointers = await c.promote_application_version(
        "app1", "v1", exts.ApplicationEnvironmentProto.APPLICATION_ENVIRONMENT_PRODUCTION
    )
    assert len(pointers) == 1
    assert pointers[0].version == "v1"


# ---------------------------------------------------------------------------
# SkillExecution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_simple_sends_simple_spec() -> None:
    execution = execdto.SkillExecutionProtoDTO(id="exec-1", asset_sn="DOCK-1")
    stub = _FakeStub(exc.SkillExecutionResponse(has_errors=False, execution=execution))
    c = _client(stub)

    result = await c.execute_simple("DOCK-1", "dock.open_cover", {"force": True})

    assert result.id == "exec-1"
    sent = stub.calls["ExecuteSkill"][0]
    assert sent.base.sn == "DOCK-1"
    assert sent.spec.simple.command_id == "dock.open_cover"
    assert sent.spec.simple.parameters.fields["force"].bool_value is True


@pytest.mark.asyncio
async def test_execute_application_sends_application_spec() -> None:
    execution = execdto.SkillExecutionProtoDTO(id="exec-2", asset_sn="DOCK-1")
    stub = _FakeStub(exc.SkillExecutionResponse(has_errors=False, execution=execution))
    c = _client(stub)

    result = await c.execute_application("DOCK-1", "app1", "skill1", application_version="v3")

    assert result.id == "exec-2"
    sent = stub.calls["ExecuteSkill"][0]
    assert sent.spec.application.application_id == "app1"
    assert sent.spec.application.skill_id == "skill1"
    assert sent.spec.application.application_version == "v3"


@pytest.mark.asyncio
async def test_create_simple_execution_validates_sn() -> None:
    c = _client(_FakeStub(exc.SkillExecutionResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.create_simple_execution("", "dock.open_cover")


@pytest.mark.asyncio
async def test_get_skill_execution_raises_on_error() -> None:
    stub = _FakeStub(_error_response(exc.SkillExecutionResponse))
    c = _client(stub)
    with pytest.raises(MissionAutonomyError, match="boom"):
        await c.get_skill_execution("exec-1")


@pytest.mark.asyncio
async def test_list_skill_executions_returns_page() -> None:
    executions = [execdto.SkillExecutionProtoDTO(id="e1"), execdto.SkillExecutionProtoDTO(id="e2")]
    stub = _FakeStub(
        exc.SkillExecutionListResponse(
            has_errors=False,
            result=exc.SkillExecutionList(executions=executions, next_page_token="tok"),
        )
    )
    c = _client(stub)

    result, next_page_token = await c.list_skill_executions(asset_sn="DOCK-1", application_id="app1")
    assert [e.id for e in result] == ["e1", "e2"]
    assert next_page_token == "tok"
    assert stub.calls["ListSkillExecutions"][0].asset_sn == "DOCK-1"


@pytest.mark.asyncio
async def test_lifecycle_operations() -> None:
    execution = execdto.SkillExecutionProtoDTO(id="exec-1")
    for op, method in [
        ("StartSkillExecution", "start_skill_execution"),
        ("PauseSkillExecution", "pause_skill_execution"),
        ("ResumeSkillExecution", "resume_skill_execution"),
        ("CancelSkillExecution", "cancel_skill_execution"),
    ]:
        stub = _FakeStub(exc.SkillExecutionResponse(has_errors=False, execution=execution))
        c = _client(stub)
        result = await getattr(c, method)("exec-1", reason="operator request")
        assert result.id == "exec-1"
        assert op in stub.calls
        assert stub.calls[op][0].reason == "operator request"


@pytest.mark.asyncio
async def test_signal_skill_execution_event_wait() -> None:
    execution = execdto.SkillExecutionProtoDTO(id="exec-1")
    stub = _FakeStub(exc.SkillExecutionResponse(has_errors=False, execution=execution))
    c = _client(stub)

    await c.signal_skill_execution(
        "exec-1", node_id="node-2", event_type="dock.open_cover.completed", data={"ok": True}
    )

    sent = stub.calls["SignalSkillExecution"][0]
    assert sent.node_id == "node-2"
    assert sent.event_type == "dock.open_cover.completed"
    assert sent.data.fields["ok"].bool_value is True


@pytest.mark.asyncio
async def test_signal_skill_execution_human_approval() -> None:
    execution = execdto.SkillExecutionProtoDTO(id="exec-1")
    stub = _FakeStub(exc.SkillExecutionResponse(has_errors=False, execution=execution))
    c = _client(stub)

    await c.signal_skill_execution("exec-1", node_id="node-3", approved=True)

    sent = stub.calls["SignalSkillExecution"][0]
    assert sent.approved is True


@pytest.mark.asyncio
async def test_resolve_execution_config_returns_dict() -> None:
    from google.protobuf import struct_pb2

    values = struct_pb2.Struct()
    values.update({"max_altitude": 120})
    stub = _FakeStub(
        exc.ResolveExecutionConfigResponse(
            has_errors=False,
            config=execdto.ResolvedExecutionConfigProtoDTO(values=values),
        )
    )
    c = _client(stub)

    context = execdto.ExecutionConfigContextProto(asset_sn="DOCK-1")
    result = await c.resolve_execution_config(context, keys=["max_altitude"])

    assert result == {"max_altitude": 120.0}
    assert list(stub.calls["ResolveExecutionConfig"][0].keys) == ["max_altitude"]


# ---------------------------------------------------------------------------
# Scheduler CRUD
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
            asset_sn="DOCK-1",
            command_id="dock.open_cover",
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
            asset_sn="DOCK-1",
            command_id="dock.open_cover",
        )
    )
    assert resp.success is True
    assert resp.scheduler is not None
    assert resp.scheduler.id == "s1"
    assert resp.scheduler.asset_sn == "DOCK-1"
    sent = stub.calls["CreateScheduler"][0]
    assert sent.scheduler.command_id == "dock.open_cover"


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
# Deprecated Mission/Task operations — removed on the backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_legacy_mission_operations_raise() -> None:
    c = _client(_FakeStub(None))
    with pytest.raises(LegacyOperationRemovedError):
        await c.create_mission(MissionDTO(name="m"))
    with pytest.raises(LegacyOperationRemovedError):
        await c.get_mission("m1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.update_mission("m1", MissionDTO(name="m"))
    with pytest.raises(LegacyOperationRemovedError):
        await c.delete_mission("m1")


@pytest.mark.asyncio
async def test_legacy_task_operations_raise() -> None:
    c = _client(_FakeStub(None))
    with pytest.raises(LegacyOperationRemovedError):
        await c.create_task(TaskDTO())
    with pytest.raises(LegacyOperationRemovedError):
        await c.get_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.get_task_by_flight_id("flight-1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.start_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.stop_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.pause_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.resume_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.delete_task("t1")
    with pytest.raises(LegacyOperationRemovedError):
        await c.update_task("t1", TaskDTO())

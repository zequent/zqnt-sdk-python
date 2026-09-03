"""Unit tests for ``MissionAutonomyClient`` (edge-side — Scheduler lookup only).

This branch tracks the 1.3.0 SchedulerProtoDTO shape (mission_id/task_id) -- main/2.0.0
replaced it with a mission-free scheduler target (asset_sn/command_id/application_id/skill_id)
as part of the Missions/Tasks -> Skills/Applications refactor; see this file's own main-branch
counterpart and models/scheduler.py's docstring.
"""

from __future__ import annotations

from typing import Any

import pytest
from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2 as mac
from zqnt_utils.generated.zqnt import mission_autonomy_dto_pb2 as mad

from edge_sdk.client.mission_autonomy_client import MissionAutonomyClient
from edge_sdk.models.common import SchedulerType


def _client(stub: Any) -> MissionAutonomyClient:
    c = MissionAutonomyClient.__new__(MissionAutonomyClient)
    c._host = "localhost"
    c._port = 50054
    c._call_timeout = 5.0
    c._max_retries = 3
    c._channel = object()
    c._stub = stub
    return c


class _FakeStub:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001
            self.calls[name] = request
            return self._response

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


@pytest.mark.asyncio
async def test_get_scheduler_found() -> None:
    scheduler = mad.SchedulerProtoDTO(
        id="s1",
        name="daily",
        cron_expression="0 0 * * *",
        mission_id="m1",
        task_id="t1",
        type=1,  # SchedulerType.TASK
    )
    stub = _FakeStub(mac.SchedulerResponse(has_errors=False, scheduler=scheduler))
    client = _client(stub)

    result = await client.get_scheduler("s1", sn="DOCK-1")

    assert result is not None
    assert result.id == "s1"
    assert result.mission_id == "m1"
    assert result.task_id == "t1"
    assert result.type == SchedulerType.TASK
    sent = stub.calls["GetScheduler"]
    assert sent.scheduler_id == "s1"
    assert sent.base.sn == "DOCK-1"


@pytest.mark.asyncio
async def test_get_scheduler_not_found() -> None:
    stub = _FakeStub(mac.SchedulerResponse(has_errors=False))
    client = _client(stub)
    result = await client.get_scheduler("missing")
    assert result is None


def test_client_has_no_legacy_mission_task_methods() -> None:
    assert not hasattr(MissionAutonomyClient, "get_mission")
    assert not hasattr(MissionAutonomyClient, "create_mission")
    assert not hasattr(MissionAutonomyClient, "get_task")

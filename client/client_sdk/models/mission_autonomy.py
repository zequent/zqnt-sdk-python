"""Domain models for the MissionAutonomy sub-client.

Mirrors ``com.zqnt.sdk.client.missionautonomy.domains`` from the Java client SDK
plus the underlying ``MissionDTO`` / ``TaskDTO`` / ``SchedulerDTO`` shared types.

The full proto ``TaskProtoDTO`` carries a ``oneof taskConfig`` with six task
config variants. To keep the public Python surface stable, we expose the
common scalar fields here and surface the type-specific config as a
:class:`TaskConfig` sub-class hierarchy in :mod:`client_sdk.models.task_config`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .common import ErrorInfo, ProgressInfo
from .enums import MissionStatus, MissionType, SchedulerType, TaskStatus, TaskType
from .task_config import TaskConfig, WaypointDTO  # noqa: F401  (re-exported)


# ---------------------------------------------------------------------------
# Mission / Task / Scheduler DTOs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MissionDTO:
    """Mission definition, mirrors :proto:`MissionProtoDTO`."""

    name: str
    description: str = ""
    status: MissionStatus = MissionStatus.DRAFT
    type: MissionType = MissionType.STANDARD
    id: str | None = None
    tasks: list["TaskDTO"] = field(default_factory=list)
    geo_json: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    assigned_assets: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    modified_at: datetime | None = None
    updated_user: str | None = None


@dataclass(slots=True)
class TaskDTO:
    """Task definition, mirrors :proto:`TaskProtoDTO`."""

    status: TaskStatus = TaskStatus.UNKNOWN
    id: str | None = None
    mission_id: str | None = None
    name: str | None = None
    description: str | None = None
    task_type: TaskType | None = None
    asset_id: str | None = None
    sn_number: str | None = None
    current_progress: int | None = None
    current_step: str | None = None
    break_reason: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    modified_from: str | None = None
    config: TaskConfig | None = None


@dataclass(slots=True)
class SchedulerDTO:
    """Scheduler definition, mirrors :proto:`SchedulerProtoDTO`."""

    name: str
    cron_expression: str
    type: SchedulerType = SchedulerType.TASK
    id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    active: bool | None = None
    client_time_zone: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None


# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MissionResponse:
    """Response shared by every mission RPC (CRUD)."""

    success: bool
    tid: str
    mission_id: str = ""
    timestamp: datetime | None = None
    error: ErrorInfo | None = None
    progress: ProgressInfo | None = None
    mission: MissionDTO | None = None


@dataclass(slots=True)
class TaskResponse:
    """Response shared by every task RPC (CRUD + start/stop)."""

    success: bool
    tid: str
    task_id: str = ""
    timestamp: datetime | None = None
    error: ErrorInfo | None = None
    progress: ProgressInfo | None = None
    task: TaskDTO | None = None


@dataclass(slots=True)
class SchedulerResponse:
    """Response shared by every scheduler RPC (CRUD).

    For ``getAllSchedulers`` the platform returns a list — exposed as
    :attr:`schedulers`. Single-scheduler RPCs populate :attr:`scheduler`.
    """

    success: bool
    tid: str
    scheduler_id: str = ""
    timestamp: datetime | None = None
    error: ErrorInfo | None = None
    progress: ProgressInfo | None = None
    scheduler: SchedulerDTO | None = None
    schedulers: list[SchedulerDTO] | None = None

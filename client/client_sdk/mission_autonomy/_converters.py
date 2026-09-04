"""Proto <-> dataclass converters for the MissionAutonomy sub-client's Mission/Task/Scheduler
surface, as it exists at the 1.3.0 wire contract this branch tracks.

Main/2.0.0 replaced Mission/Task/Scheduler entirely with the capability-execution model
(Application/SkillExecution) -- capability-execution-*.proto don't exist at 1.3.0 at all, so
this branch has no equivalent of main's "Application/SkillExecution work with raw generated proto
DTOs" scope note; instead, Mission/Task/Scheduler (flat-ish messages, no huge execution-graph
schema to avoid re-wrapping) get real dataclass converters. ``TaskProtoDTO``'s ``oneof
task_config`` (six typed variants: waypoint/detect/area_mapping/poi/follow/track) is deliberately
NOT round-tripped here -- :class:`~client_sdk.models.mission_autonomy.TaskDTO.config` stays
``None`` on both directions. Building a full bidirectional converter for all six nested configs
adds real surface for something no caller in this codebase actually needs yet; the typed
dataclasses (:mod:`client_sdk.models.task_config`) remain available for a caller who wants to
construct a proto ``TaskProtoDTO`` by hand and pass it straight to the RPC instead.

Generated proto modules are imported lazily so the package remains importable before the SDK's
protobuf dependency has been installed.
"""

from __future__ import annotations

from typing import Any

from ..models._converters import (
    datetime_to_proto_ts,
    opt_field,
    proto_to_error_info,
    proto_to_progress_info,
    proto_ts_to_datetime,
)
from ..models.enums import MissionStatus, MissionType, SchedulerType, TaskStatus, TaskType
from ..models.mission_autonomy import (
    MissionDTO,
    MissionResponse,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
)


def _set_opt(kwargs: dict[str, Any], proto_field: str, value: Any) -> None:
    if value is not None:
        kwargs[proto_field] = value


# ---------------------------------------------------------------------------
# Scheduler DTO <-> proto
# ---------------------------------------------------------------------------


def scheduler_to_proto(s: SchedulerDTO):
    from zqnt_utils.generated.zqnt import mission_autonomy_dto_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {
        "name": s.name,
        "cron_expression": s.cron_expression,
        "type": s.type.value,
    }
    _set_opt(kwargs, "id", s.id)
    _set_opt(kwargs, "active", s.active)
    _set_opt(kwargs, "client_time_zone", s.client_time_zone)
    if s.created_at is not None:
        kwargs["created_at"] = datetime_to_proto_ts(s.created_at)
    if s.modified_at is not None:
        kwargs["modified_at"] = datetime_to_proto_ts(s.modified_at)
    _set_opt(kwargs, "mission_id", s.mission_id)
    _set_opt(kwargs, "task_id", s.task_id)
    return mission_autonomy_dto_pb2.SchedulerProtoDTO(**kwargs)


def proto_to_scheduler(proto) -> SchedulerDTO:
    return SchedulerDTO(
        name=proto.name,
        cron_expression=proto.cron_expression,
        type=SchedulerType(proto.type),
        id=opt_field(proto, "id"),
        active=opt_field(proto, "active"),
        client_time_zone=opt_field(proto, "client_time_zone"),
        created_at=proto_ts_to_datetime(opt_field(proto, "created_at")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modified_at")),
        mission_id=opt_field(proto, "mission_id"),
        task_id=opt_field(proto, "task_id"),
    )


def proto_to_scheduler_response(proto) -> SchedulerResponse:
    which = proto.WhichOneof("response")
    return SchedulerResponse(
        success=not bool(opt_field(proto, "has_errors")),
        tid=proto.tid,
        scheduler_id=proto.scheduler_id,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        scheduler=proto_to_scheduler(proto.scheduler) if which == "scheduler" else None,
        schedulers=[proto_to_scheduler(s) for s in proto.schedulers.scheduler_dto_list]
        if which == "schedulers"
        else None,
    )


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


def mission_to_proto(m: MissionDTO):
    from zqnt_utils.generated.zqnt import mission_autonomy_dto_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {
        "name": m.name,
        "description": m.description,
        "status": m.status.value,
        "type": m.type.value,
    }
    _set_opt(kwargs, "id", m.id)
    _set_opt(kwargs, "geo_json", m.geo_json)
    if m.start_date is not None:
        kwargs["start_date"] = datetime_to_proto_ts(m.start_date)
    if m.end_date is not None:
        kwargs["end_date"] = datetime_to_proto_ts(m.end_date)
    if m.assigned_assets:
        kwargs["assigned_assets"] = list(m.assigned_assets)
    _set_opt(kwargs, "updated_user", m.updated_user)
    # tasks/created_at/modified_at are read-only server output on this branch -- a caller builds
    # a Mission to create/update it, not to describe one that already has persisted tasks/timestamps.
    return mission_autonomy_dto_pb2.MissionProtoDTO(**kwargs)


def proto_to_mission(proto) -> MissionDTO:
    return MissionDTO(
        name=proto.name,
        description=proto.description,
        status=MissionStatus(proto.status),
        type=MissionType(proto.type),
        id=opt_field(proto, "id"),
        geo_json=opt_field(proto, "geo_json"),
        start_date=proto_ts_to_datetime(opt_field(proto, "start_date")),
        end_date=proto_ts_to_datetime(opt_field(proto, "end_date")),
        assigned_assets=list(proto.assigned_assets),
        created_at=proto_ts_to_datetime(opt_field(proto, "created_at")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modified_at")),
        updated_user=opt_field(proto, "updated_user"),
        # tasks/config: not round-tripped -- see this module's docstring.
    )


def proto_to_mission_response(proto) -> MissionResponse:
    which = proto.WhichOneof("response")
    return MissionResponse(
        success=not bool(opt_field(proto, "has_errors")),
        tid=proto.tid,
        mission_id=proto.mission_id,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        mission=proto_to_mission(proto.mission) if which == "mission" else None,
    )


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


def task_to_proto(t: TaskDTO):
    from zqnt_utils.generated.zqnt import mission_autonomy_dto_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {"status": t.status.value}
    if t.task_type is not None:
        kwargs["task_type"] = t.task_type.value
    _set_opt(kwargs, "id", t.id)
    _set_opt(kwargs, "mission_id", t.mission_id)
    _set_opt(kwargs, "name", t.name)
    _set_opt(kwargs, "description", t.description)
    _set_opt(kwargs, "asset_id", t.asset_id)
    _set_opt(kwargs, "sn_number", t.sn_number)
    _set_opt(kwargs, "current_progress", t.current_progress)
    _set_opt(kwargs, "current_step", t.current_step)
    # break_reason/created_at/modified_at/modified_from/config: not round-tripped -- see this
    # module's docstring (config) and mission_to_proto's note (server-owned fields otherwise).
    return mission_autonomy_dto_pb2.TaskProtoDTO(**kwargs)


def proto_to_task(proto) -> TaskDTO:
    return TaskDTO(
        status=TaskStatus(proto.status),
        id=opt_field(proto, "id"),
        mission_id=opt_field(proto, "mission_id"),
        name=opt_field(proto, "name"),
        description=opt_field(proto, "description"),
        task_type=TaskType(proto.task_type),
        asset_id=opt_field(proto, "asset_id"),
        sn_number=opt_field(proto, "sn_number"),
        current_progress=opt_field(proto, "current_progress"),
        current_step=opt_field(proto, "current_step"),
        created_at=proto_ts_to_datetime(opt_field(proto, "created_at")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modified_at")),
        modified_from=opt_field(proto, "modified_from"),
        # break_reason/config: not round-tripped -- see this module's docstring.
    )


def proto_to_task_response(proto) -> TaskResponse:
    which = proto.WhichOneof("response")
    return TaskResponse(
        success=not bool(opt_field(proto, "has_errors")),
        tid=proto.tid,
        task_id=proto.task_id,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        task=proto_to_task(proto.task) if which == "task" else None,
    )

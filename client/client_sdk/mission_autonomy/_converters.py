"""Proto <-> dataclass converters for the MissionAutonomy sub-client's Scheduler surface, plus
spec-builders for the SkillExecution surface.

Application/SkillExecution RPCs deliberately work with the raw generated proto DTOs
(``ApplicationProtoDTO``, ``SkillExecutionProtoDTO``, ...) instead of a parallel dataclass
hierarchy — same scope decision as ``client-go-sdk``'s ``missionautonomy`` package: the
execution-graph schema (nodes/edges/conditions/gateways/...) is large and already has a typed
representation (the generated proto classes); wrapping it a second time in idiomatic Python
buys little. Only Scheduler (a flat, small message) gets a dataclass, matching prior convention.

Generated proto modules are imported lazily so the package remains importable before the SDK's
protobuf dependency has been installed.
"""

from __future__ import annotations

from typing import Any

from ..models._converters import (
    datetime_to_proto_ts,
    dict_to_struct,
    opt_field,
    proto_to_error_info,
    proto_to_progress_info,
    proto_ts_to_datetime,
    struct_to_dict,
)
from ..models.enums import SchedulerType
from ..models.mission_autonomy import SchedulerDTO, SchedulerResponse


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
    _set_opt(kwargs, "asset_sn", s.asset_sn)
    _set_opt(kwargs, "command_id", s.command_id)
    _set_opt(kwargs, "application_id", s.application_id)
    _set_opt(kwargs, "skill_id", s.skill_id)
    if s.execution_parameters:
        kwargs["execution_parameters"] = dict_to_struct(s.execution_parameters)
    _set_opt(kwargs, "auto_start", s.auto_start)
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
        asset_sn=opt_field(proto, "asset_sn"),
        command_id=opt_field(proto, "command_id"),
        application_id=opt_field(proto, "application_id"),
        skill_id=opt_field(proto, "skill_id"),
        execution_parameters=struct_to_dict(proto.execution_parameters)
        if proto.HasField("execution_parameters")
        else None,
        auto_start=opt_field(proto, "auto_start"),
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
# SkillExecutionSpecProto builders
# ---------------------------------------------------------------------------


def simple_spec(command_id: str, parameters: dict | None):
    from zqnt_utils.generated.zqnt import capability_execution_dto_pb2 as execdto  # type: ignore[import]

    return execdto.SkillExecutionSpecProto(
        simple=execdto.SimpleExecutionSpecProto(command_id=command_id, parameters=dict_to_struct(parameters)),
    )


def application_spec(application_id: str, skill_id: str, application_version: str | None, parameters: dict | None):
    from zqnt_utils.generated.zqnt import capability_execution_dto_pb2 as execdto  # type: ignore[import]

    kwargs: dict[str, Any] = {
        "application_id": application_id,
        "skill_id": skill_id,
        "parameters": dict_to_struct(parameters),
    }
    _set_opt(kwargs, "application_version", application_version)
    return execdto.SkillExecutionSpecProto(application=execdto.ApplicationExecutionSpecProto(**kwargs))

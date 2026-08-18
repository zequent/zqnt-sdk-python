"""
Plain-Python scheduler model mirroring ``mission-autonomy-dto.proto`` ``SchedulerProtoDTO``.

The mission-free scheduler target: exactly one of ``command_id`` or ``application_id`` +
``skill_id`` is expected for new schedules (``mission_id``/``task_id`` are permanently reserved
on the wire — the legacy Mission/Task scheduling model they backed is gone).
"""

from dataclasses import dataclass
from datetime import datetime

from .common import SchedulerType


@dataclass
class SchedulerDTO:
    id: str | None
    name: str
    cron_expression: str
    type: SchedulerType = SchedulerType.SYSTEM_JOBS
    active: bool | None = None
    client_time_zone: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    asset_sn: str | None = None
    command_id: str | None = None
    application_id: str | None = None
    skill_id: str | None = None
    execution_parameters: dict | None = None
    auto_start: bool | None = None

"""
Plain-Python scheduler model mirroring ``mission-autonomy-dto.proto`` ``SchedulerProtoDTO``,
as it exists at the 1.3.0 wire contract: Mission/Task-based (``mission_id``/``task_id``).

Main/2.0.0 replaced this with a mission-free scheduler target (``asset_sn``/``command_id``/
``application_id``/``skill_id``/``execution_parameters``/``auto_start``) as part of the
Missions/Tasks -> Skills/Applications refactor -- that shape doesn't exist at 1.3.0, so this
branch keeps the original Mission/Task fields instead. See zqnt-protos' README "Versioning"
section.
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
    mission_id: str | None = None
    task_id: str | None = None
    active: bool | None = None
    client_time_zone: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

"""
Plain-Python notification models mirroring ``events.proto`` ``NotificationEvent`` variants,
as they exist at the 1.3.0 wire contract.

This branch keeps :class:`TaskEvent` (retired on main/2.0.0 in favor of the vendor-neutral
``CommandExecutionEvent``, which doesn't exist in events.proto until after the 1.3.0 tag) --
see zqnt-protos' README "Versioning" section.
"""

from dataclasses import dataclass

from .common import MissionStatus, MissionType, TaskStatus, TaskType


@dataclass
class AssetStatusEvent:
    """Asset online / offline status change."""

    sn: str
    online: bool
    asset_id: str | None = None
    message: str | None = None


@dataclass
class TaskEvent:
    """Task lifecycle event."""

    task_id: str
    task_type: TaskType
    status: TaskStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    progress: float | None = None
    message: str | None = None
    external_task_type: str | None = None


@dataclass
class MissionEvent:
    """Mission lifecycle event."""

    mission_id: str
    mission_type: MissionType
    status: MissionStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    message: str | None = None

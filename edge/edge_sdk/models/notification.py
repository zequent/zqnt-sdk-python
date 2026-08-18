"""
Plain-Python notification models mirroring ``events.proto`` ``NotificationEvent`` variants.

``TaskEvent`` is gone — ``NotificationEvent.task`` (field 2) is permanently reserved on the wire,
retired in favor of :class:`CommandExecutionEvent` (vendor-neutral command lifecycle feedback).
``OperationEvent`` is renamed :class:`MissionEvent` to match the proto's own ``mission`` branch.
"""

from dataclasses import dataclass

from .common import CommandExecutionStatus, MissionStatus, MissionType


@dataclass
class AssetStatusEvent:
    """Asset online / offline status change."""

    sn: str
    online: bool
    asset_id: str | None = None
    message: str | None = None


@dataclass
class MissionEvent:
    """Mission lifecycle event."""

    mission_id: str
    mission_type: MissionType
    status: MissionStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    message: str | None = None


@dataclass
class CommandExecutionEvent:
    """Vendor-neutral lifecycle feedback for one physical command dispatched to an edge adapter."""

    external_execution_id: str
    status: CommandExecutionStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    command_id: str | None = None
    progress: float | None = None  # 0.0 – 1.0, present when RUNNING
    message: str | None = None

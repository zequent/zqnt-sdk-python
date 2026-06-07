"""
Plain-Python notification models mirroring live-data.proto notification DTOs.
"""

from dataclasses import dataclass

from .common import MissionStatus, MissionType, TaskStatus, TaskType


@dataclass
class AssetStatusEvent:
    """Asset online / offline status change."""

    sn: str
    online: bool
    asset_id: str | None = None


@dataclass
class TaskEvent:
    """Task lifecycle event."""

    task_id: str
    task_type: TaskType
    status: TaskStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    progress: float | None = None  # 0.0 – 1.0, present when RUNNING
    message: str | None = None  # error details when ERROR
    external_task_type: str | None = None


@dataclass
class OperationEvent:
    """Mission / operation status change."""

    operation_id: str
    mission_type: MissionType
    status: MissionStatus
    sn: str = ""  # asset serial number – required for multi-asset adapters
    message: str | None = None

"""Shared response/coordinate models exposed by the SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ErrorInfo:
    """Error detail returned in a service response."""

    error_code: str
    error_message: str
    timestamp: datetime | None = None


@dataclass(slots=True)
class ProgressInfo:
    """Progress information for long-running commands."""

    progress: float
    state: str
    left_time_in_seconds: float


@dataclass(slots=True)
class RemoteControlResponse:
    """Generic response shared by every RemoteControl RPC.

    Mirrors ``com.zqnt.utils.remotecontrol.proto.RemoteControlResponse``.
    """

    success: bool
    tid: str
    sn: str
    asset_id: str | None = None
    message: str | None = None
    error: ErrorInfo | None = None
    progress: ProgressInfo | None = None


# Aliases mirror Java response types without duplication.
TakeoffResponse = RemoteControlResponse

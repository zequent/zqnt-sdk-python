"""Request dataclasses for the RemoteControl sub-client.

Mirrors the Java SDK ``com.zqnt.sdk.client.remotecontrol.domains`` package.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TakeoffRequest:
    sn: str
    latitude: float
    longitude: float
    altitude: float
    asset_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None


@dataclass(slots=True)
class GoToRequest:
    sn: str
    latitude: float
    longitude: float
    altitude: float
    asset_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None


@dataclass(slots=True)
class ReturnToHomeRequest:
    sn: str
    asset_id: str | None = None
    altitude: float | None = None
    mission_id: str | None = None
    task_id: str | None = None


@dataclass(slots=True)
class LookAtRequest:
    sn: str
    latitude: float
    longitude: float
    altitude: float
    asset_id: str | None = None


@dataclass(slots=True)
class ManualControlRequest:
    sn: str
    client_id: str
    user_id: str
    session_id: str
    asset_id: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class DockOperationRequest:
    """Request used by every parameter-less dock / asset operation.

    ``value`` is the optional boolean payload used by:
      - ``close_cover`` (``force``)
      - ``boot_sub_asset`` (``boot``)
      - ``debug_mode`` (``enabled``)
    Other operations ignore it.
    """

    sn: str
    asset_id: str | None = None
    value: bool | None = None

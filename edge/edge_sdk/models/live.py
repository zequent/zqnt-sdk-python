"""
v3 live data: a telemetry sample, an alert. Detections use :class:`~edge_sdk.models.common.DetectionBatch`.

A sample has the fields every asset shares; everything device-specific goes into ``details``
under keys the adapter declares (:meth:`EdgeAdapter.declare_telemetry_field`). Leave a value
``None`` (or NaN) when the asset does not report it -- it is then not sent at all.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


@dataclass
class TelemetrySample:
    sn: str
    observed_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    #: Metres above sea level.
    altitude: float | None = None
    #: Metres above the takeoff point.
    relative_altitude: float | None = None
    #: Degrees clockwise from true north.
    heading_degrees: float | None = None
    #: m/s.
    horizontal_speed: float | None = None
    #: m/s, positive up.
    vertical_speed: float | None = None
    battery_percent: float | None = None
    details: dict = field(default_factory=dict)
    asset_id: str | None = None


class AlertSeverity(IntEnum):
    UNSPECIFIED = 0
    INFO = 1
    WARNING = 2
    CRITICAL = 3


@dataclass
class Alert:
    """Something the asset reports on its own, e.g. a dock's rain warning or a motor fault."""

    sn: str
    #: Stable, machine-readable, e.g. ``dock.rain`` or ``vendor.dji.hms.0x16100083``.
    code: str
    message: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    details: dict = field(default_factory=dict)
    occurred_at: datetime | None = None
    asset_id: str | None = None

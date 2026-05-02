"""Shared proto <-> dataclass converters.

Per-domain converters live alongside their sub-clients
(``mission_autonomy/_converters.py``, ``live_data/_converters.py``).
This module only contains helpers used by **multiple** sub-clients.

Generated proto modules are imported lazily inside the helpers so the
package remains importable before ``scripts/generate_protos.sh`` has run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .common import ErrorInfo, ProgressInfo, RemoteControlResponse


def build_request_base(sn: str, tid: str | None = None):
    """Build a ``RequestBase`` proto with a fresh tid + UTC timestamp."""
    from google.protobuf import timestamp_pb2

    from ..generated import common_pb2  # type: ignore[import]

    ts = timestamp_pb2.Timestamp()
    ts.GetCurrentTime()
    return common_pb2.RequestBase(
        tid=tid or str(uuid.uuid4()),
        sn=sn,
        timestamp=ts,
    )


def build_coordinates(latitude: float, longitude: float, altitude: float):
    from ..generated import common_pb2  # type: ignore[import]

    return common_pb2.Coordinates(
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
    )


def proto_ts_to_datetime(ts) -> datetime | None:
    """Convert a ``google.protobuf.Timestamp`` to a UTC ``datetime`` (or None)."""
    if ts is None:
        return None
    seconds = getattr(ts, "seconds", 0)
    nanos = getattr(ts, "nanos", 0)
    if seconds == 0 and nanos == 0:
        return None
    return datetime.fromtimestamp(seconds + nanos / 1e9, tz=timezone.utc)


def datetime_to_proto_ts(dt: datetime | None):
    """Build a ``google.protobuf.Timestamp`` from a ``datetime`` (or current UTC)."""
    from google.protobuf import timestamp_pb2

    ts = timestamp_pb2.Timestamp()
    if dt is None:
        ts.GetCurrentTime()
    else:
        ts.FromDatetime(dt)
    return ts


def opt_field(msg, field: str):
    """Return ``msg.field`` if the field is set, else ``None``.

    Works for proto3 ``optional`` scalars and oneof members.
    """
    try:
        return getattr(msg, field) if msg.HasField(field) else None  # type: ignore[attr-defined]
    except (ValueError, AttributeError):
        return getattr(msg, field, None)


def _resolve_error_code(raw_code) -> str:
    """Decode a proto ``ErrorCode`` enum value to its symbolic name."""
    try:
        from ..generated import common_pb2  # type: ignore[import]

        return common_pb2.ErrorCode.Name(raw_code)
    except Exception:  # pragma: no cover - defensive
        return str(raw_code)


def proto_to_error_info(err) -> ErrorInfo:
    """Convert a ``GlobalErrorMessage`` proto into :class:`ErrorInfo`."""
    return ErrorInfo(
        error_code=_resolve_error_code(err.errorCode),
        error_message=err.errorMessage,
        timestamp=proto_ts_to_datetime(err.timestamp) if err.HasField("timestamp") else None,  # type: ignore[attr-defined]
    )


def proto_to_progress_info(p) -> ProgressInfo:
    return ProgressInfo(
        progress=p.progress,
        state=p.state,
        left_time_in_seconds=p.leftTimeInSeconds,
    )


def proto_to_response(proto, sn: str) -> RemoteControlResponse:
    """Convert a ``RemoteControlResponse`` proto into the SDK dataclass."""
    error: ErrorInfo | None = None
    progress: ProgressInfo | None = None

    if proto.HasField("error"):
        error = proto_to_error_info(proto.error)
    if proto.HasField("progress"):
        progress = proto_to_progress_info(proto.progress)

    return RemoteControlResponse(
        success=not proto.hasErrors,
        tid=proto.tid,
        sn=sn,
        asset_id=proto.assetId if proto.HasField("assetId") else None,
        message=proto.responseMessage if proto.HasField("responseMessage") else None,
        error=error,
        progress=progress,
    )

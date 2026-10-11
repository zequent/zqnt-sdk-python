"""Live telemetry, detections and alerts of Zequent 3.0 over ``zqnt.telemetry.v3.TelemetryService``.

A ``TelemetrySample`` has the fields every asset shares (position, relative altitude, heading,
speeds, battery); everything device-specific is in its ``details``, under the keys the asset
declares in its capabilities' ``telemetry_fields``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterable
from datetime import timedelta

import grpc
import grpc.aio
from google.protobuf import duration_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.telemetry.v3 import telemetry_pb2, telemetry_pb2_grpc

from ..commands.errors import CommandError

DEFAULT_HEARTBEAT_TIMEOUT = timedelta(seconds=35)


class TelemetryClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = telemetry_pb2_grpc.TelemetryServiceStub(channel)

    def watch_telemetry(
        self,
        asset_sns: Iterable[str] | None = None,
        *,
        min_interval: timedelta | float | None = None,
        heartbeat_timeout: timedelta | float = DEFAULT_HEARTBEAT_TIMEOUT,
    ) -> AsyncIterator[telemetry_pb2.TelemetrySample | telemetry_pb2.SourceStatus]:
        """Samples of the given assets from now on, until the loop is left.

        No asset watches every asset of the caller's organization; a dock's serial also brings the
        samples of its drone. ``min_interval`` keeps at most one sample per asset per interval
        (unset = every sample). Besides ``TelemetrySample``\\ s the loop yields a ``SourceStatus``
        for every watched asset first, then each time an asset goes online, stale or silent.

        The platform sends a heartbeat on a quiet stream; when neither an item nor a heartbeat
        arrives within ``heartbeat_timeout`` the loop raises a retryable :class:`CommandError` with
        category ``SERVICE``. A refused or dropped watch raises :class:`CommandError` too. The watch
        does not reconnect: watch again.
        """
        request = telemetry_pb2.WatchTelemetryRequest(context=_context(), assets=_assets(asset_sns))
        if min_interval is not None:
            request.min_interval.CopyFrom(_duration(min_interval))
        return _watch(self._stub.WatchTelemetry, request, ("sample", "source_status"), heartbeat_timeout)

    def watch_detections(
        self,
        asset_sns: Iterable[str] | None = None,
        *,
        heartbeat_timeout: timedelta | float = DEFAULT_HEARTBEAT_TIMEOUT,
    ) -> AsyncIterator[telemetry_pb2.DetectionBatch]:
        """The detection batches of the given assets from now on, until the loop is left.

        No asset watches every asset of the caller's organization. Heartbeats, refusals and a
        dropped stream behave as in :meth:`watch_telemetry`.
        """
        request = telemetry_pb2.WatchDetectionsRequest(context=_context(), assets=_assets(asset_sns))
        return _watch(self._stub.WatchDetections, request, ("batch",), heartbeat_timeout)

    def watch_alerts(
        self,
        asset_sns: Iterable[str] | None = None,
        *,
        min_severity: int = telemetry_pb2.ALERT_SEVERITY_UNSPECIFIED,
        heartbeat_timeout: timedelta | float = DEFAULT_HEARTBEAT_TIMEOUT,
    ) -> AsyncIterator[telemetry_pb2.Alert]:
        """The alerts of the given assets from now on, until the loop is left.

        No asset watches every asset of the caller's organization. ``min_severity`` (an
        ``AlertSeverity``, e.g. ``telemetry_pb2.ALERT_SEVERITY_WARNING``) drops less severe alerts;
        unset = every severity. Heartbeats, refusals and a dropped stream behave as in
        :meth:`watch_telemetry`.
        """
        request = telemetry_pb2.WatchAlertsRequest(
            context=_context(), assets=_assets(asset_sns), min_severity=min_severity
        )
        return _watch(self._stub.WatchAlerts, request, ("alert",), heartbeat_timeout)


async def _watch(rpc, request, items: tuple[str, ...], heartbeat_timeout: timedelta | float) -> AsyncIterator:
    silence = _seconds(heartbeat_timeout)
    call = rpc(request)
    try:
        while True:
            try:
                async with asyncio.timeout(silence):
                    response = await call.read()
            except TimeoutError:
                raise CommandError(
                    f"nothing and no heartbeat for {silence:g}s",
                    category=common_pb2.ERROR_CATEGORY_SERVICE,
                    retryable=True,
                ) from None
            if response is grpc.aio.EOF:
                return
            item = response.WhichOneof("item")
            if item in items:
                yield getattr(response, item)
    except grpc.aio.AioRpcError as exc:
        raise CommandError.from_exception(exc) from exc
    finally:
        call.cancel()


def _context() -> common_pb2.RequestContext:
    return common_pb2.RequestContext(request_id=str(uuid.uuid4()))


def _assets(asset_sns: Iterable[str] | None) -> list[common_pb2.AssetRef]:
    sns = list(asset_sns or ())
    if any(not sn or not sn.strip() for sn in sns):
        raise ValueError("asset_sns must not contain a blank serial")
    return [common_pb2.AssetRef(sn=sn) for sn in sns]


def _seconds(value: timedelta | float) -> float:
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


def _duration(value: timedelta | float) -> duration_pb2.Duration:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(value if isinstance(value, timedelta) else timedelta(seconds=value))
    return duration

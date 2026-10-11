"""Live telemetry of Zequent 3.0 over ``zqnt.telemetry.v3.TelemetryService``.

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

    async def watch_telemetry(
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

        The platform sends a heartbeat on a quiet stream; when neither a sample nor a heartbeat
        arrives within ``heartbeat_timeout`` the loop raises a retryable :class:`CommandError` with
        category ``SERVICE``. A refused or dropped watch raises :class:`CommandError` too. The watch
        does not reconnect: watch again.
        """
        request = telemetry_pb2.WatchTelemetryRequest(
            context=common_pb2.RequestContext(request_id=str(uuid.uuid4())),
        )
        for sn in asset_sns or ():
            if not sn or not sn.strip():
                raise ValueError("asset_sns must not contain a blank serial")
            request.assets.append(common_pb2.AssetRef(sn=sn))
        if min_interval is not None:
            request.min_interval.CopyFrom(_duration(min_interval))
        silence = _seconds(heartbeat_timeout)
        call = self._stub.WatchTelemetry(request)
        try:
            while True:
                try:
                    async with asyncio.timeout(silence):
                        response = await call.read()
                except TimeoutError:
                    raise CommandError(
                        f"no telemetry and no heartbeat for {silence:g}s",
                        category=common_pb2.ERROR_CATEGORY_SERVICE,
                        retryable=True,
                    ) from None
                if response is grpc.aio.EOF:
                    return
                item = response.WhichOneof("item")
                if item == "sample":
                    yield response.sample
                elif item == "source_status":
                    yield response.source_status
        except grpc.aio.AioRpcError as exc:
            raise CommandError.from_exception(exc) from exc
        finally:
            call.cancel()


def _seconds(value: timedelta | float) -> float:
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


def _duration(value: timedelta | float) -> duration_pb2.Duration:
    duration = duration_pb2.Duration()
    duration.FromTimedelta(value if isinstance(value, timedelta) else timedelta(seconds=value))
    return duration

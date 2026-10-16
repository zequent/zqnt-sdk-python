"""Live video of assets over ``zqnt.stream.v3.LiveStreamService``: a stream is listed while
something publishes to it on the media server, whatever started it."""

from __future__ import annotations

import uuid

import grpc
import grpc.aio
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.stream.v3 import live_stream_pb2, live_stream_pb2_grpc

from ..commands.errors import CommandError
from ..config.resilience import ResilienceConfig


class LiveStreamsClient:
    def __init__(self, channel: grpc.aio.Channel, resilience: ResilienceConfig) -> None:
        self._stub = live_stream_pb2_grpc.LiveStreamServiceStub(channel)
        self._timeout = float(resilience.request_timeout_seconds)

    async def list_live_streams(self) -> list[live_stream_pb2.LiveStream]:
        """Every stream of the caller's organization that is live right now, with its asset, media
        server path, start time (``since``) and number of ``viewers``.

        Raises :class:`CommandError` when the platform refuses the call; a retryable one with
        category ``SERVICE`` (status ``UNAVAILABLE``) when it has no current answer from the media
        server.
        """
        request = live_stream_pb2.ListLiveStreamsRequest(
            context=common_pb2.RequestContext(request_id=str(uuid.uuid4()))
        )
        try:
            response = await self._stub.ListLiveStreams(request, timeout=self._timeout)
        except grpc.aio.AioRpcError as exc:
            raise CommandError.from_exception(exc) from exc
        return list(response.streams)

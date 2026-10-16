"""The live video streams of Zequent 3.0 over ``zqnt.stream.v3.LiveStreamService``."""

from __future__ import annotations

import uuid

import grpc.aio
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.stream.v3 import live_stream_pb2, live_stream_pb2_grpc

from ..commands.errors import CommandError
from ..config.resilience import ResilienceConfig
from ..grpc_.resilience import GrpcResilience


class LiveStreamsClient:
    def __init__(self, channel: grpc.aio.Channel, resilience: ResilienceConfig) -> None:
        self._stub = live_stream_pb2_grpc.LiveStreamServiceStub(channel)
        self._timeout = float(resilience.request_timeout_seconds)
        self._resilience = GrpcResilience(resilience)

    async def list_live_streams(self) -> list[live_stream_pb2.LiveStream]:
        """Every stream of the caller's organization that is live right now: the asset publishing it
        (for a docked aircraft, the aircraft), the media server's ``path``, ``since`` when it is
        received and how many ``viewers`` read it.

        Raises :class:`CommandError` with the gRPC ``status``: ``PERMISSION_DENIED`` when the
        organization's license does not include live streams, ``UNAVAILABLE`` when the platform has
        no current answer from the media server.
        """
        request = live_stream_pb2.ListLiveStreamsRequest(
            context=common_pb2.RequestContext(request_id=str(uuid.uuid4()))
        )
        try:
            response = await self._resilience.execute(
                lambda: self._stub.ListLiveStreams(request, timeout=self._timeout)
            )
        except Exception as exc:
            raise CommandError.from_exception(exc) from exc
        return list(response.streams)

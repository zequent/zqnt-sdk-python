"""``LiveStreamsClient`` against an in-process fake ``zqnt.stream.v3.LiveStreamService``."""

from __future__ import annotations

from datetime import UTC, datetime

import grpc
import grpc.aio
import pytest
from google.protobuf import timestamp_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.stream.v3 import live_stream_pb2, live_stream_pb2_grpc

from client_sdk import CommandError, LiveStreamsClient, ZequentClient
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


class FakeLiveStreams(live_stream_pb2_grpc.LiveStreamServiceServicer):
    def __init__(self) -> None:
        self.request: live_stream_pb2.ListLiveStreamsRequest | None = None
        self.refuse_with: tuple[grpc.StatusCode, str] | None = None
        self.streams: list[live_stream_pb2.LiveStream] = []

    async def ListLiveStreams(self, request, context):  # noqa: N802
        self.request = request
        if self.refuse_with is not None:
            await context.abort(*self.refuse_with)
        return live_stream_pb2.ListLiveStreamsResponse(streams=self.streams)


@pytest.fixture
async def fake():
    servicer = FakeLiveStreams()
    server = grpc.aio.server()
    live_stream_pb2_grpc.add_LiveStreamServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    servicer.port = port
    yield servicer
    await server.stop(None)


@pytest.fixture
async def client(fake):
    config = ServiceConfig("live-data", host="127.0.0.1", port=fake.port)
    async with ZequentClient(
        connector_config=config,
        remote_control_config=config,
        mission_autonomy_config=config,
        live_data_config=config,
        resilience=ResilienceConfig(max_retry_attempts=0, request_timeout_seconds=5),
        client_token="test-token",
    ) as zequent:
        yield zequent.live_streams


async def test_lists_the_live_streams_of_the_organization(client: LiveStreamsClient, fake: FakeLiveStreams):
    since = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    started = timestamp_pb2.Timestamp()
    started.FromDatetime(since)
    fake.streams = [
        live_stream_pb2.LiveStream(
            asset=common_pb2.AssetRef(sn="DRONE-1"), path="live/DOCK-1/drone", since=started, viewers=2
        )
    ]

    streams = await client.list_live_streams()

    assert len(streams) == 1
    assert streams[0].asset.sn == "DRONE-1"
    assert streams[0].path == "live/DOCK-1/drone"
    assert streams[0].since.ToDatetime(tzinfo=UTC) == since
    assert streams[0].viewers == 2
    assert fake.request.context.request_id


async def test_nothing_live_is_an_empty_list(client: LiveStreamsClient):
    assert await client.list_live_streams() == []


@pytest.mark.parametrize("code", [grpc.StatusCode.PERMISSION_DENIED, grpc.StatusCode.UNAVAILABLE])
async def test_a_refusal_raises_command_error_with_its_status(
    client: LiveStreamsClient, fake: FakeLiveStreams, code: grpc.StatusCode
):
    fake.refuse_with = (code, "refused")

    with pytest.raises(CommandError) as raised:
        await client.list_live_streams()

    assert raised.value.status == code

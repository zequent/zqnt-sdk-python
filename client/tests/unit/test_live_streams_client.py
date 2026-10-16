"""``LiveStreamsClient`` against an in-process fake ``zqnt.stream.v3.LiveStreamService``."""

from __future__ import annotations

import grpc
import grpc.aio
import pytest
from google.protobuf import timestamp_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.stream.v3 import live_stream_pb2, live_stream_pb2_grpc

from client_sdk import CommandError, LiveStreamsClient, ZequentClient
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


class FakeLiveStreamService(live_stream_pb2_grpc.LiveStreamServiceServicer):
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
    servicer = FakeLiveStreamService()
    server = grpc.aio.server()
    live_stream_pb2_grpc.add_LiveStreamServiceServicer_to_server(servicer, server)
    servicer.port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
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


async def test_lists_the_live_streams_of_the_organization(client: LiveStreamsClient, fake: FakeLiveStreamService):
    fake.streams = [
        live_stream_pb2.LiveStream(
            asset=common_pb2.AssetRef(sn="DRONE-1"),
            path="live/DRONE-1/drone",
            since=timestamp_pb2.Timestamp(seconds=1_700_000_000),
            viewers=2,
        )
    ]

    streams = await client.list_live_streams()

    assert [(s.asset.sn, s.path, s.since.seconds, s.viewers) for s in streams] == [
        ("DRONE-1", "live/DRONE-1/drone", 1_700_000_000, 2)
    ]
    assert fake.request.context.request_id


async def test_no_stream_is_an_empty_list(client: LiveStreamsClient):
    assert await client.list_live_streams() == []


async def test_no_answer_from_the_media_server_raises_a_retryable_service_error(
    client: LiveStreamsClient, fake: FakeLiveStreamService
):
    fake.refuse_with = (grpc.StatusCode.UNAVAILABLE, "media server did not answer")

    with pytest.raises(CommandError) as raised:
        await client.list_live_streams()

    assert raised.value.category == common_pb2.ERROR_CATEGORY_SERVICE
    assert raised.value.status == grpc.StatusCode.UNAVAILABLE
    assert raised.value.retryable
    assert str(raised.value) == "media server did not answer"


async def test_a_refused_call_raises_its_category(client: LiveStreamsClient, fake: FakeLiveStreamService):
    fake.refuse_with = (grpc.StatusCode.PERMISSION_DENIED, "not licensed")

    with pytest.raises(CommandError) as raised:
        await client.list_live_streams()

    assert raised.value.category == common_pb2.ERROR_CATEGORY_PERMISSION_DENIED
    assert not raised.value.retryable

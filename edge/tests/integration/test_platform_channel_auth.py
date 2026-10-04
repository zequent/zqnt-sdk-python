"""
The edge credential reaches the platform on EVERY call type, against a real grpc.aio server.

Regression (dev, 2026-10-01): live-data refused ``ProduceTelemetry``/``ProduceDetection``/
``ProduceNotification`` "without credentials" although ``ZQNT_EDGE_TOKEN`` was set. grpc.aio sorts
each channel interceptor into ONE call-type list with an if/elif chain on its base class, so a
single interceptor inheriting all four bases was registered for unary-unary only and every
streaming call went out bare. Unit tests that call ``intercept_*`` directly cannot see that — only
a channel with a server behind it can.
"""

import asyncio
import socket

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from zqnt_utils.generated.zqnt import live_data_pb2_grpc, live_data_types_pb2  # type: ignore[import]

from edge_sdk.auth import platform_channel
from edge_sdk.client.detection_publisher import DetectionPublisher
from edge_sdk.client.notification_publisher import NotificationPublisher
from edge_sdk.client.telemetry_publisher import TelemetryPublisher
from edge_sdk.models import AssetTelemetry, DetectionBatch, DetectionResult
from edge_sdk.models.notification import AssetStatusEvent

TOKEN = "edge-credential-under-test"
BEARER = f"Bearer {TOKEN}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _authorization(context) -> str | None:
    for key, value in context.invocation_metadata() or ():
        if key == "authorization":
            return value
    return None


# ---------------------------------------------------------------------------
# All four call types through platform_channel
# ---------------------------------------------------------------------------


class _EchoAuthorization(grpc.GenericRpcHandler):
    """Answers /test.Echo/<kind> with the authorization header the call arrived with."""

    def service(self, handler_call_details):
        def header(context) -> bytes:
            return (_authorization(context) or "").encode()

        async def unary_unary(_request, context):
            return header(context)

        async def unary_stream(_request, context):
            yield header(context)

        async def stream_unary(request_iterator, context):
            async for _ in request_iterator:
                pass
            return header(context)

        async def stream_stream(request_iterator, context):
            async for _ in request_iterator:
                pass
            yield header(context)

        handlers = {
            "/test.Echo/UnaryUnary": grpc.unary_unary_rpc_method_handler(unary_unary),
            "/test.Echo/UnaryStream": grpc.unary_stream_rpc_method_handler(unary_stream),
            "/test.Echo/StreamUnary": grpc.stream_unary_rpc_method_handler(stream_unary),
            "/test.Echo/StreamStream": grpc.stream_stream_rpc_method_handler(stream_stream),
        }
        return handlers.get(handler_call_details.method)


@pytest_asyncio.fixture
async def echo_port():
    port = _free_port()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((_EchoAuthorization(),))
    server.add_insecure_port(f"localhost:{port}")
    await server.start()
    yield port
    await server.stop(grace=0)


async def _requests():
    yield b"x"


@pytest.mark.asyncio
async def test_every_call_type_carries_the_edge_credential(echo_port):
    channel = platform_channel("localhost", echo_port, TOKEN)
    try:
        unary_unary = await channel.unary_unary("/test.Echo/UnaryUnary")(b"x")
        unary_stream = [r async for r in channel.unary_stream("/test.Echo/UnaryStream")(b"x")]
        stream_unary = await channel.stream_unary("/test.Echo/StreamUnary")(_requests())
        stream_stream = [r async for r in channel.stream_stream("/test.Echo/StreamStream")(_requests())]
    finally:
        await channel.close()

    assert {
        "unary_unary": unary_unary.decode(),
        "unary_stream": unary_stream[0].decode(),
        "stream_unary": stream_unary.decode(),
        "stream_stream": stream_stream[0].decode(),
    } == {
        "unary_unary": BEARER,
        "unary_stream": BEARER,
        "stream_unary": BEARER,
        "stream_stream": BEARER,
    }


@pytest.mark.asyncio
async def test_a_call_keeps_its_own_metadata_next_to_the_credential(echo_port):
    seen: dict = {}

    class _Capture(grpc.GenericRpcHandler):
        def service(self, handler_call_details):
            async def stream_unary(request_iterator, context):
                async for _ in request_iterator:
                    pass
                seen.update(dict(context.invocation_metadata()))
                return b""

            return grpc.stream_unary_rpc_method_handler(stream_unary)

    port = _free_port()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((_Capture(),))
    server.add_insecure_port(f"localhost:{port}")
    await server.start()
    channel = platform_channel("localhost", port, TOKEN)
    try:
        await channel.stream_unary("/test.Echo/Any")(_requests(), metadata=(("x-trace", "abc"),))
    finally:
        await channel.close()
        await server.stop(grace=0)

    assert seen["authorization"] == BEARER
    assert seen["x-trace"] == "abc"


# ---------------------------------------------------------------------------
# The three client-streaming publishers live-data refused on dev
# ---------------------------------------------------------------------------


class _LiveData(live_data_pb2_grpc.LiveDataServiceServicer):
    def __init__(self) -> None:
        self.headers: dict[str, str | None] = {}
        self.received = asyncio.Event()

    async def _consume(self, name, request_iterator, context):
        self.headers[name] = _authorization(context)
        async for _ in request_iterator:
            self.received.set()

    async def ProduceTelemetry(self, request_iterator, context):  # noqa: N802 - gRPC method name
        await self._consume("ProduceTelemetry", request_iterator, context)
        return live_data_types_pb2.LiveDataResponse()

    async def ProduceDetection(self, request_iterator, context):  # noqa: N802 - gRPC method name
        await self._consume("ProduceDetection", request_iterator, context)
        return live_data_types_pb2.LiveDataResponse()

    async def ProduceNotification(self, request_iterator, context):  # noqa: N802 - gRPC method name
        await self._consume("ProduceNotification", request_iterator, context)
        return live_data_types_pb2.LiveDataResponse()


@pytest_asyncio.fixture
async def live_data():
    port = _free_port()
    servicer = _LiveData()
    server = grpc.aio.server()
    live_data_pb2_grpc.add_LiveDataServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"localhost:{port}")
    await server.start()
    yield port, servicer
    await server.stop(grace=0)


async def _publish_once(publisher, publish, servicer) -> None:
    servicer.received.clear()
    await publisher.connect()
    try:
        await publish()
        await asyncio.wait_for(servicer.received.wait(), timeout=5)
    finally:
        await publisher.close()


@pytest.mark.asyncio
async def test_produce_telemetry_carries_the_edge_credential(live_data):
    port, servicer = live_data
    publisher = TelemetryPublisher(host="localhost", port=port, sn="SN-1", token=TOKEN)
    await _publish_once(publisher, lambda: publisher.publish_asset_telemetry(AssetTelemetry(id="SN-1")), servicer)
    assert servicer.headers["ProduceTelemetry"] == BEARER


@pytest.mark.asyncio
async def test_produce_detection_carries_the_edge_credential(live_data):
    port, servicer = live_data
    publisher = DetectionPublisher(host="localhost", port=port, sn="SN-1", token=TOKEN)
    batch = DetectionBatch(sn="SN-1", detections=[DetectionResult(object_id="o", object_type="UAV", confidence=0.9)])
    await _publish_once(publisher, lambda: publisher.publish_detection_batch(batch), servicer)
    assert servicer.headers["ProduceDetection"] == BEARER


@pytest.mark.asyncio
async def test_produce_notification_carries_the_edge_credential(live_data):
    port, servicer = live_data
    publisher = NotificationPublisher(host="localhost", port=port, sn="SN-1", token=TOKEN)
    event = AssetStatusEvent(sn="SN-1", online=True)
    await _publish_once(publisher, lambda: publisher.publish_asset_status(event), servicer)
    assert servicer.headers["ProduceNotification"] == BEARER


@pytest.mark.asyncio
async def test_the_token_comes_from_the_environment_when_not_passed(live_data, monkeypatch):
    monkeypatch.setenv("ZQNT_EDGE_TOKEN", TOKEN)
    port, servicer = live_data
    publisher = TelemetryPublisher(host="localhost", port=port, sn="SN-1")
    await _publish_once(publisher, lambda: publisher.publish_asset_telemetry(AssetTelemetry(id="SN-1")), servicer)
    assert servicer.headers["ProduceTelemetry"] == BEARER

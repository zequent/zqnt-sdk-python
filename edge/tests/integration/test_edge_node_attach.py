"""
An adapter attached to a local Edge Node, against an in-process fake node on a Unix socket: live
data and capabilities reach the node with the adapter's socket in the header, a command the node
sends over that socket reaches the adapter's handler, and the adapter's events come back.
"""

import asyncio
import os
import socket
import stat
import tempfile

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from google.protobuf import empty_pb2, struct_pb2
from zqnt_api.generated.zqnt.capability.v3 import command_pb2
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_v3
from zqnt_api.generated.zqnt.edge.v3 import edge_adapter_service_pb2_grpc as edge_v3_grpc
from zqnt_api.generated.zqnt.telemetry.v3 import telemetry_pb2, telemetry_pb2_grpc

from edge_sdk import (
    AssetType,
    CommandExecutionStatus,
    CustomCommandResponse,
    EdgeAdapter,
    EdgeAdapterConfig,
    EdgeAuthConfig,
    EdgeNodeConfig,
    EdgeServer,
    TelemetrySample,
)
from edge_sdk.client.notification_publisher import NotificationPublisher
from edge_sdk.models.notification import CommandExecutionEvent
from edge_sdk.node import ADAPTER_ENDPOINT_HEADER, QUEUE_SERVICE

SN = "DOCK-1"


async def _until(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.02)


def _endpoint(context) -> str:
    return dict(context.invocation_metadata()).get(ADAPTER_ENDPOINT_HEADER, "")


class _Node:
    def __init__(self) -> None:
        self.samples: list = []
        self.sample_endpoints: list[str] = []
        self.capabilities: list = []
        self.capability_endpoints: list[str] = []
        self.events: list = []


class _Ingest(telemetry_pb2_grpc.TelemetryIngestServiceServicer):
    def __init__(self, node: _Node) -> None:
        self._n = node

    async def PublishTelemetry(self, request_iterator, context):
        self._n.sample_endpoints.append(_endpoint(context))
        async for request in request_iterator:
            self._n.samples.append(request.sample)
        return telemetry_pb2.PublishTelemetryResponse(accepted=len(self._n.samples))


class _Gateway(edge_v3_grpc.EdgeGatewayServiceServicer):
    def __init__(self, node: _Node) -> None:
        self._n = node

    async def ReportCapabilities(self, request, context):
        self._n.capability_endpoints.append(_endpoint(context))
        self._n.capabilities.append(request.capabilities)
        return edge_v3.ReportCapabilitiesResponse(accepted_revision=request.capabilities.revision)

    async def PublishCommandEvent(self, request, context):
        self._n.events.append(request.event)
        return edge_v3.PublishCommandEventResponse()


def _queue_stats(throttle: float) -> struct_pb2.Struct:
    s = struct_pb2.Struct()
    s.update(
        {
            "connected": False,
            "lanes": [
                {
                    "lane": "LANE_TELEMETRY",
                    "items": 900,
                    "bytes": 4096,
                    "max_items": 1000,
                    "max_bytes": 0,
                    "fill": 0.9,
                    "dropped": 3,
                    "oldest": "2026-11-02T10:00:00.123456789Z",
                    "throttle": throttle,
                }
            ],
        }
    )
    return s


def _queue_service() -> grpc.GenericRpcHandler:
    async def get(_request, _context):
        return _queue_stats(0.3)

    async def watch(_request, _context):
        yield _queue_stats(0.3)
        yield _queue_stats(1.0)

    kwargs = {
        "request_deserializer": empty_pb2.Empty.FromString,
        "response_serializer": struct_pb2.Struct.SerializeToString,
    }
    return grpc.method_handlers_generic_handler(
        QUEUE_SERVICE,
        {
            "GetQueueStats": grpc.unary_unary_rpc_method_handler(get, **kwargs),
            "WatchQueueStats": grpc.unary_stream_rpc_method_handler(watch, **kwargs),
        },
    )


@pytest.fixture
def sockets():
    with tempfile.TemporaryDirectory(prefix="zqnt-") as root:
        yield os.path.join(root, "node", "node.sock"), os.path.join(root, "adapters", "dock.sock")


@pytest_asyncio.fixture
async def node(sockets):
    node_sock, _ = sockets
    os.makedirs(os.path.dirname(node_sock))
    state = _Node()
    server = grpc.aio.server()
    telemetry_pb2_grpc.add_TelemetryIngestServiceServicer_to_server(_Ingest(state), server)
    edge_v3_grpc.add_EdgeGatewayServiceServicer_to_server(_Gateway(state), server)
    server.add_generic_rpc_handlers((_queue_service(),))
    server.add_insecure_port(f"unix:{node_sock}")
    await server.start()
    yield state
    await server.stop(0)


class _Dock(EdgeAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.opened: list[str] = []
        self.register_command("dock.open_cover", self._open_cover)

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    def reported_asset_sns(self):
        return [SN]

    async def _open_cover(self, ctx, params):
        self.opened.append(ctx.command_execution_id)
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "dock.open_cover", external_execution_id="vendor-7")


def _config(sockets, monkeypatch) -> EdgeAdapterConfig:
    node_sock, adapter_sock = sockets
    monkeypatch.setenv("ZQNT_EDGE_NODE_SOCKET", node_sock)
    monkeypatch.setenv("ZQNT_ADAPTER_SOCKET", adapter_sock)
    monkeypatch.setenv("EDGE_ENDPOINT", "grpc://never-written:50051")
    monkeypatch.setenv("ASSET_TYPE", "ASSET_TYPE_DOCK")
    monkeypatch.setenv("ASSET_VENDOR", "ASSET_VENDOR_DJI")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1")
    for name in (
        "ZQNT_EDGE_AUTH_DISABLED",
        "ZQNT_PLATFORM_KEYS_URL",
        "ZQNT_PLATFORM_PUBLIC_KEY",
        "REMOTE_CONTROL_HOST",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("edge_sdk.config._setup_logging", lambda *_: None)
    return EdgeAdapterConfig.from_env()


async def test_an_adapter_attaches_to_the_node_by_configuration_only(node, sockets, monkeypatch, caplog):
    caplog.set_level("INFO")
    config = _config(sockets, monkeypatch)
    _, adapter_sock = sockets
    endpoint = f"unix://{adapter_sock}"
    assert config.edge_node == EdgeNodeConfig(*sockets)
    dock = _Dock()
    bound: list[str] = []
    add_insecure_port = grpc.aio._server.Server.add_insecure_port

    def record(server, address):
        bound.append(address)
        return add_insecure_port(server, address)

    monkeypatch.setattr(grpc.aio._server.Server, "add_insecure_port", record)

    async with config.runtime() as runtime:
        assert runtime.connector is None and runtime.telemetry is None and runtime.mission_autonomy is None
        serving = asyncio.create_task(runtime.serve(dock))
        try:
            await _until(lambda: node.capabilities)
            assert node.capabilities[0].asset_sn == SN
            assert node.capability_endpoints == [endpoint]
            assert stat.S_IMODE(os.stat(adapter_sock).st_mode) == 0o660
            assert len(bound) == 1 and bound[0].startswith("unix:"), bound
            assert "NOT verified" in caplog.text
            assert "Redis endpoint registration skipped" in caplog.text

            await runtime.ingest.publish_sample(
                TelemetrySample(sn=SN, latitude=47.5, longitude=9.7, battery_percent=80)
            )
            await _until(lambda: node.samples)
            assert node.samples[0].asset.sn == SN and node.samples[0].battery_percent == 80
            assert node.sample_endpoints == [endpoint]

            async with grpc.aio.insecure_channel(f"unix:{adapter_sock}") as channel:
                response = await edge_v3_grpc.EdgeAdapterServiceStub(channel).ExecuteCommand(
                    edge_v3.ExecuteCommandRequest(
                        command=command_pb2.Command(command_id="dock.open_cover", asset=common_pb2.AssetRef(sn=SN)),
                        command_execution_id="capexec:e1:n1",
                    )
                )
            assert dock.opened == ["capexec:e1:n1"]
            assert response.result.state == command_pb2.COMMAND_STATE_ACCEPTED

            notifier = NotificationPublisher("unused", sn=SN)
            await notifier.connect()
            try:
                await notifier.publish_command_execution_event(
                    CommandExecutionEvent(
                        external_execution_id="vendor-7", status=CommandExecutionStatus.SUCCEEDED, sn=SN
                    )
                )
            finally:
                await notifier.close()
            [event] = node.events
            assert event.command_execution_id == "capexec:e1:n1"
            assert event.command_id == "dock.open_cover"
            assert event.state == command_pb2.COMMAND_STATE_SUCCEEDED

            stats = await runtime.node_queue.get()
            assert not stats.connected
            assert stats.throttle("LANE_TELEMETRY") == 0.3
            assert stats.throttle("LANE_ALARM") == 1.0
            lane = stats.lane("LANE_TELEMETRY")
            assert lane is not None and lane.items == 900 and lane.dropped == 3 and lane.oldest is not None
            watched = [s.throttle("LANE_TELEMETRY") async for s in runtime.node_queue.watch()]
            assert watched == [0.3, 1.0]
            assert runtime.node_queue.latest is not None and runtime.node_queue.latest.throttle("LANE_TELEMETRY") == 1.0
        finally:
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
    assert not os.path.exists(adapter_sock)


async def test_direct_mode_still_verifies_the_platform_token(monkeypatch):
    for name in ("ZQNT_EDGE_NODE_SOCKET", "ZQNT_ADAPTER_SOCKET"):
        monkeypatch.delenv(name, raising=False)
    assert EdgeAdapterConfig.from_env().edge_node is None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = EdgeServer(adapter=_Dock(), port=port, host="127.0.0.1", auth=EdgeAuthConfig())
    serving = asyncio.create_task(server.serve())
    try:
        await _until(lambda: server._server is not None)
        await asyncio.sleep(0.1)
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            with pytest.raises(grpc.aio.AioRpcError) as refused:
                await edge_v3_grpc.EdgeAdapterServiceStub(channel).ExecuteCommand(
                    edge_v3.ExecuteCommandRequest(
                        command=command_pb2.Command(command_id="dock.open_cover", asset=common_pb2.AssetRef(sn=SN)),
                        command_execution_id="capexec:e1:n1",
                    )
                )
        assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED
    finally:
        serving.cancel()
        await asyncio.gather(serving, return_exceptions=True)


async def test_attached_only_a_unix_peer_skips_the_token_check(sockets):
    from edge_sdk.auth import PlatformAuthServerInterceptor
    from edge_sdk.server import edge_server_v3

    _, adapter_sock = sockets
    os.makedirs(os.path.dirname(adapter_sock))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    interceptor = PlatformAuthServerInterceptor(EdgeAuthConfig(), trust_unix_peers=True)
    server = grpc.aio.server(interceptors=[interceptor])
    edge_server_v3.add_to_server(_Dock(), server)
    server.add_insecure_port(f"unix:{adapter_sock}")
    server.add_insecure_port(f"127.0.0.1:{port}")
    await server.start()
    request = edge_v3.ExecuteCommandRequest(
        command=command_pb2.Command(command_id="dock.open_cover", asset=common_pb2.AssetRef(sn=SN)),
        command_execution_id="capexec:e1:n1",
    )
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            with pytest.raises(grpc.aio.AioRpcError) as refused:
                await edge_v3_grpc.EdgeAdapterServiceStub(channel).ExecuteCommand(request)
        assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED
        async with grpc.aio.insecure_channel(f"unix:{adapter_sock}") as channel:
            response = await edge_v3_grpc.EdgeAdapterServiceStub(channel).ExecuteCommand(request)
        assert response.result.state == command_pb2.COMMAND_STATE_ACCEPTED
    finally:
        await server.stop(0)


def test_an_attach_needs_both_sockets(monkeypatch):
    monkeypatch.setenv("ZQNT_EDGE_NODE_SOCKET", "/run/zqnt-edge-node/node.sock")
    monkeypatch.delenv("ZQNT_ADAPTER_SOCKET", raising=False)
    with pytest.raises(ValueError, match="ZQNT_ADAPTER_SOCKET"):
        EdgeNodeConfig.from_env()


def test_the_adapter_socket_is_never_open_to_others():
    with pytest.raises(ValueError, match="owner and group"):
        EdgeNodeConfig("/run/node.sock", "/run/adapter.sock", socket_mode=0o666)


def test_a_relative_socket_path_is_made_absolute():
    config = EdgeNodeConfig("node.sock", "adapter.sock")
    assert config.adapter_endpoint == f"unix://{os.path.abspath('adapter.sock')}"
    assert config.node_target == f"unix:{os.path.abspath('node.sock')}"


async def test_a_file_in_place_of_the_adapter_socket_is_not_replaced(sockets):
    from edge_sdk.node import bind_adapter_socket

    _, adapter_sock = sockets
    os.makedirs(os.path.dirname(adapter_sock))
    with open(adapter_sock, "w") as f:
        f.write("keep")
    server = grpc.aio.server()
    with pytest.raises(RuntimeError, match="not a socket"):
        bind_adapter_socket(server, EdgeNodeConfig("/run/node.sock", adapter_sock))
    with open(adapter_sock) as f:
        assert f.read() == "keep"

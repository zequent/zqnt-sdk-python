"""A real EdgeServer with authentication on: only the platform may command the device."""

import asyncio
import socket
from contextlib import suppress

import grpc
import grpc.aio
import pytest
import pytest_asyncio
from zqnt_utils.generated.zqnt import (  # type: ignore[import]
    common_pb2,
    device_control_contracts_pb2,
    edge_pb2_grpc,
)

from edge_sdk import EdgeAuthConfig, EdgeServer
from tests.auth_tokens import new_key, public_key_b64, token
from tests.conftest import _TestAdapter

KEY = new_key()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest_asyncio.fixture
async def secured_port():
    port = _free_port()
    server = EdgeServer(adapter=_TestAdapter(), port=port, auth=EdgeAuthConfig(platform_public_key=public_key_b64(KEY)))
    task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    yield port
    await server.stop(grace=0)
    with suppress(asyncio.CancelledError, Exception):
        await task


async def _capabilities(port: int, metadata=None):
    async with grpc.aio.insecure_channel(f"localhost:{port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        return await stub.GetCapabilities(common_pb2.AssetCapabilitiesRequest(sn="TEST-001"), metadata=metadata)


@pytest.mark.asyncio
async def test_a_command_without_a_token_is_refused(secured_port):
    with pytest.raises(grpc.aio.AioRpcError) as refused:
        await _capabilities(secured_port)
    assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_the_platforms_token_is_accepted(secured_port):
    response = await _capabilities(secured_port, metadata=(("authorization", f"Bearer {token(KEY)}"),))
    assert response.HasField("capabilities")


@pytest.mark.asyncio
async def test_a_token_meant_for_core_is_refused(secured_port):
    with pytest.raises(grpc.aio.AioRpcError) as refused:
        await _capabilities(secured_port, metadata=(("authorization", f"Bearer {token(KEY, aud='zqnt-platform')}"),))
    assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_a_streamed_manual_control_input_without_a_token_is_refused(secured_port):
    """Manual control is a client stream — the refusal must hold for stream-shaped handlers too."""

    async def inputs():
        yield device_control_contracts_pb2.ManualControlInputCommandRequest()

    async with grpc.aio.insecure_channel(f"localhost:{secured_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as refused:
            await stub.ManualControlInput(inputs())
    assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_health_is_open(secured_port):
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    async with grpc.aio.insecure_channel(f"localhost:{secured_port}") as ch:
        response = await health_pb2_grpc.HealthStub(ch).Check(health_pb2.HealthCheckRequest(service=""))
    assert response.status == health_pb2.HealthCheckResponse.SERVING

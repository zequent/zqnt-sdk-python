"""
With ZQNT_INTERNAL_TLS on, platform_channel dials the core over TLS verified against the
installation's CA, still carrying the edge credential; the wrong CA is refused and nothing
changes without the switch.
"""

import asyncio
import socket

import grpc
import grpc.aio
import pytest
import pytest_asyncio

from edge_sdk.auth import platform_channel
from tests.certs import write_self_signed

TOKEN = "edge-credential-under-test"
METHOD = "/test.Echo/Authorization"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class _EchoAuthorization(grpc.GenericRpcHandler):
    def service(self, handler_call_details):
        if handler_call_details.method != METHOD:
            return None

        async def unary_unary(_request, context):
            for key, value in context.invocation_metadata() or ():
                if key == "authorization":
                    return value.encode()
            return b""

        return grpc.unary_unary_rpc_method_handler(unary_unary)


@pytest_asyncio.fixture
async def tls_server(tmp_path):
    cert, key = write_self_signed(tmp_path, "server")
    port = _free_port()
    server = grpc.aio.server()
    server.add_generic_rpc_handlers((_EchoAuthorization(),))
    server.add_secure_port(f"127.0.0.1:{port}", grpc.ssl_server_credentials([(key.read_bytes(), cert.read_bytes())]))
    await server.start()
    yield port, cert
    await server.stop(grace=0)


async def _call(channel: grpc.aio.Channel) -> str:
    call = channel.unary_unary(METHOD, request_serializer=bytes, response_deserializer=bytes)
    return (await asyncio.wait_for(call(b""), timeout=5)).decode()


async def test_tls_with_the_installation_ca_carries_the_credential(tls_server, monkeypatch):
    port, cert = tls_server
    monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
    monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", str(cert))
    channel = platform_channel("localhost", port, TOKEN)
    try:
        assert await _call(channel) == f"Bearer {TOKEN}"
    finally:
        await channel.close()


async def test_another_ca_is_refused(tls_server, tmp_path, monkeypatch):
    port, _ = tls_server
    other, _ = write_self_signed(tmp_path, "other")
    monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
    monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", str(other))
    channel = platform_channel("localhost", port, TOKEN)
    try:
        with pytest.raises(grpc.aio.AioRpcError) as refused:
            await _call(channel)
        assert refused.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await channel.close()


async def test_without_the_switch_the_channel_is_plaintext(tls_server, monkeypatch):
    port, cert = tls_server
    monkeypatch.delenv("ZQNT_INTERNAL_TLS", raising=False)
    monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", str(cert))
    channel = platform_channel("localhost", port, TOKEN)
    try:
        with pytest.raises(grpc.aio.AioRpcError) as refused:
            await _call(channel)
        assert refused.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await channel.close()


async def test_a_missing_ca_fails_before_dialling(monkeypatch, tmp_path):
    monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
    monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", str(tmp_path / "nope.crt"))
    with pytest.raises(FileNotFoundError, match="ZQNT_INTERNAL_TLS_CA"):
        platform_channel("localhost", 1, TOKEN)

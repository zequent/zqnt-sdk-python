"""TLS to the platform with an installation's own CA: ServiceConfig.tls_ca_file and the ZQNT_INTERNAL_TLS variables."""

from __future__ import annotations

import asyncio
import socket

import grpc
import grpc.aio
import pytest
import pytest_asyncio

from client_sdk.config.env_loader import _service
from client_sdk.config.service_config import ServiceConfig
from client_sdk.grpc_.channel_factory import create_channel
from tests.certs import write_self_signed

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


def _config(port: int, ca: str | None) -> ServiceConfig:
    return ServiceConfig(service_name="connector", host="localhost", port=port, use_plaintext=False, tls_ca_file=ca)


async def test_tls_with_the_ca_file_carries_the_client_token(tls_server):
    port, cert = tls_server
    channel = create_channel(_config(port, str(cert)), "client-token")
    try:
        assert await _call(channel) == "Bearer client-token"
    finally:
        await channel.close()


async def test_another_ca_is_refused(tls_server, tmp_path):
    port, _ = tls_server
    other, _ = write_self_signed(tmp_path, "other")
    channel = create_channel(_config(port, str(other)))
    try:
        with pytest.raises(grpc.aio.AioRpcError) as refused:
            await _call(channel)
        assert refused.value.code() == grpc.StatusCode.UNAVAILABLE
    finally:
        await channel.close()


def test_a_missing_ca_file_fails_when_the_channel_is_built(tmp_path):
    with pytest.raises(FileNotFoundError, match="connector"):
        create_channel(_config(1, str(tmp_path / "nope.crt")))


class TestEnvironment:
    def test_nothing_set_is_plaintext(self, monkeypatch):
        monkeypatch.delenv("ZQNT_INTERNAL_TLS", raising=False)
        monkeypatch.delenv("CONNECTOR_SERVICE_USE_PLAINTEXT", raising=False)
        config = _service("CONNECTOR_SERVICE", "connector")
        assert config.use_plaintext and config.tls_ca_file is None

    def test_internal_tls_switches_every_service_to_the_default_ca(self, monkeypatch):
        monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
        monkeypatch.delenv("ZQNT_INTERNAL_TLS_CA", raising=False)
        monkeypatch.delenv("LIVE_DATA_SERVICE_USE_PLAINTEXT", raising=False)
        config = _service("LIVE_DATA_SERVICE", "live-data")
        assert not config.use_plaintext
        assert config.tls_ca_file == "/etc/zqnt/internal-tls/ca.crt"

    def test_the_ca_path(self, monkeypatch):
        monkeypatch.setenv("ZQNT_INTERNAL_TLS", "yes")
        monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", " /pki/ca.pem ")
        assert _service("CONNECTOR_SERVICE", "connector").tls_ca_file == "/pki/ca.pem"

    def test_a_service_s_own_plaintext_setting_wins(self, monkeypatch):
        monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
        monkeypatch.setenv("CONNECTOR_SERVICE_USE_PLAINTEXT", "true")
        assert _service("CONNECTOR_SERVICE", "connector").use_plaintext

    def test_without_the_switch_the_ca_variable_is_ignored(self, monkeypatch):
        monkeypatch.delenv("ZQNT_INTERNAL_TLS", raising=False)
        monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", "/pki/ca.pem")
        assert _service("CONNECTOR_SERVICE", "connector").tls_ca_file is None

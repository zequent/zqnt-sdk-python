"""A host application's own interceptors (a service forwarding its caller's token, or rotating a
short-lived one) reach every channel, unary and streaming, and the ``authorization`` they set wins
over a configured client token. Plus the environment: nothing set is the local stack.

Against a real ``grpc.aio`` server on a free port, so the headers asserted are the ones on the wire.
"""

from __future__ import annotations

import asyncio

import grpc
import grpc.aio
import pytest
from zqnt_utils.generated.zqnt import (  # type: ignore[import]
    connector_pb2,
    connector_pb2_grpc,
    live_data_pb2_grpc,
    live_data_types_pb2,
)

from client_sdk import ZequentClient
from client_sdk.auth import ENV_VAR, ZequentAuthError
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig
from client_sdk.models.live_data import StreamTelemetryRequest


class _Recorder:
    def __init__(self) -> None:
        self.headers: list[list[str]] = []
        self.refuse: tuple[grpc.StatusCode, str] | None = None

    async def check(self, context: grpc.aio.ServicerContext) -> None:
        self.headers.append([v for k, v in (context.invocation_metadata() or ()) if k == "authorization"])
        if self.refuse is not None:
            await context.abort(*self.refuse)


class _Connector(connector_pb2_grpc.ConnectorServiceServicer):
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def ListSkillContracts(self, request, context):  # noqa: N802 - gRPC naming
        await self._recorder.check(context)
        return connector_pb2.SkillContractListResponse(has_errors=False)


class _LiveData(live_data_pb2_grpc.LiveDataServiceServicer):
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def StreamTelemetry(self, request, context):  # noqa: N802 - gRPC naming
        await self._recorder.check(context)
        yield live_data_types_pb2.LiveDataTelemetryResponse(sn=request.base.sn)


@pytest.fixture
async def server():
    recorder = _Recorder()
    srv = grpc.aio.server()
    connector_pb2_grpc.add_ConnectorServiceServicer_to_server(_Connector(recorder), srv)
    live_data_pb2_grpc.add_LiveDataServiceServicer_to_server(_LiveData(recorder), srv)
    port = srv.add_insecure_port("127.0.0.1:0")
    await srv.start()
    yield recorder, port
    await srv.stop(None)


def _with_bearer(details: grpc.aio.ClientCallDetails, token: str) -> grpc.aio.ClientCallDetails:
    if details.metadata and any(k == "authorization" for k, _ in details.metadata):
        return details
    metadata = grpc.aio.Metadata(*(details.metadata or ()))
    metadata.add("authorization", f"Bearer {token}")
    return grpc.aio.ClientCallDetails(
        details.method, details.timeout, metadata, details.credentials, details.wait_for_ready
    )


class _ForwardingUnary(grpc.aio.UnaryUnaryClientInterceptor):
    """What a service registers: its current caller's token, looked up per call."""

    def __init__(self, token) -> None:
        self.token = token

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(_with_bearer(client_call_details, self.token()), request)


class _ForwardingStream(grpc.aio.UnaryStreamClientInterceptor):
    def __init__(self, token) -> None:
        self.token = token

    async def intercept_unary_stream(self, continuation, client_call_details, request):
        return await continuation(_with_bearer(client_call_details, self.token()), request)


def _client(port: int, token: str | None, interceptors=()) -> ZequentClient:
    def config(name: str) -> ServiceConfig:
        return ServiceConfig(service_name=name, host="127.0.0.1", port=port)

    return ZequentClient(
        connector_config=config("connector"),
        remote_control_config=config("remote-control"),
        mission_autonomy_config=config("mission-autonomy"),
        live_data_config=config("live-data"),
        resilience=ResilienceConfig(max_retry_attempts=0, retry_delay_millis=1),
        client_token=token,
        interceptors=interceptors,
    )


async def test_the_host_interceptor_reaches_unary_and_streaming_calls(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    current = {"token": "user-token"}
    received: list[str] = []
    interceptors = [_ForwardingUnary(lambda: current["token"]), _ForwardingStream(lambda: current["token"])]
    async with _client(port, None, interceptors) as client:
        await client.connector.list_skill_contracts()
        current["token"] = "service-token"
        handle = client.live_data.stream_telemetry(StreamTelemetryRequest(sn="DOCK-1"), lambda r: received.append(r.sn))
        for _ in range(100):
            if received:
                break
            await asyncio.sleep(0.02)
        await handle.stop()
    assert recorder.headers[0] == ["Bearer user-token"]
    assert received and recorder.headers[1] == ["Bearer service-token"]


async def test_the_host_interceptors_header_wins_and_is_the_only_one(server) -> None:
    recorder, port = server
    async with _client(port, "fixed-token", [_ForwardingUnary(lambda: "forwarded")]) as client:
        await client.connector.list_skill_contracts()
    assert recorder.headers == [["Bearer forwarded"]]


async def test_the_client_token_is_still_sent_when_no_interceptor_sets_one(server) -> None:
    recorder, port = server
    async with _client(port, "fixed-token", [_ForwardingStream(lambda: "stream-only")]) as client:
        await client.connector.list_skill_contracts()
    assert recorder.headers == [["Bearer fixed-token"]]


async def test_interceptors_run_in_the_order_given(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    async with _client(port, None, [_ForwardingUnary(lambda: "first"), _ForwardingUnary(lambda: "second")]) as client:
        await client.connector.list_skill_contracts()
    assert recorder.headers == [["Bearer first"]]


async def test_a_refused_host_credential_is_still_explained(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    recorder.refuse = (grpc.StatusCode.UNAUTHENTICATED, "Invalid token")
    async with _client(port, None, [_ForwardingUnary(lambda: "stale")]) as client:
        with pytest.raises(ZequentAuthError) as refused:
            await client.connector.list_skill_contracts()
    assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Invalid token" in refused.value.details()


_SERVICE_VARS = [
    f"{prefix}_{suffix}"
    for prefix in ("CONNECTOR_SERVICE", "REMOTE_CONTROL_SERVICE", "LIVE_DATA_SERVICE", "MISSION_AUTONOMY_SERVICE")
    for suffix in ("HOST", "PORT", "USE_PLAINTEXT")
]


@pytest.fixture
def clean_env(monkeypatch):
    for name in [*_SERVICE_VARS, ENV_VAR]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


async def test_nothing_set_is_the_local_stack(clean_env) -> None:
    async with ZequentClient.from_env() as client:
        assert client._connector_config.host == "localhost" and client._connector_config.port == 8010
        assert client._remote_control_config.port == 8002
        assert client._live_data_config.port == 8003
        assert client._mission_autonomy_config.port == 8004
        assert client._connector_config.use_plaintext
        assert not client.has_client_token


async def test_a_deployment_sets_host_port_tls_and_token(clean_env) -> None:
    clean_env.setenv("CONNECTOR_SERVICE_HOST", "connector.zequent.internal")
    clean_env.setenv("CONNECTOR_SERVICE_PORT", " 443 ")
    clean_env.setenv("CONNECTOR_SERVICE_USE_PLAINTEXT", "false")
    clean_env.setenv("LIVE_DATA_SERVICE_USE_PLAINTEXT", "")
    clean_env.setenv(ENV_VAR, "deployment-token")
    async with ZequentClient.from_env() as client:
        assert client._connector_config.host == "connector.zequent.internal"
        assert client._connector_config.port == 443
        assert not client._connector_config.use_plaintext
        assert client._live_data_config.use_plaintext, "blank is the default, not false"
        assert client.has_client_token


async def test_from_env_takes_overrides(clean_env) -> None:
    interceptor = _ForwardingUnary(lambda: "x")
    async with ZequentClient.from_env(client_token="explicit", interceptors=[interceptor]) as client:
        assert client.has_client_token
        assert client._interceptors == (interceptor,)


def test_a_malformed_port_names_its_variable(clean_env) -> None:
    clean_env.setenv("LIVE_DATA_SERVICE_PORT", "80a3")
    with pytest.raises(ValueError, match="LIVE_DATA_SERVICE_PORT"):
        ZequentClient.from_env()

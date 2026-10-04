"""The client credential travels on every call, unary and streaming, and refusals say what to do.

Against a real ``grpc.aio`` server on a free port, so the header asserted is the one on the wire.
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
from client_sdk.auth import ENV_VAR, ZequentAuthError, resolve_token
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig
from client_sdk.models.live_data import StreamTelemetryRequest


class _Recorder:
    def __init__(self) -> None:
        self.headers: list[str | None] = []
        self.refuse: tuple[grpc.StatusCode, str] | None = None

    async def check(self, context: grpc.aio.ServicerContext) -> None:
        metadata = dict(context.invocation_metadata() or ())
        self.headers.append(metadata.get("authorization"))
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


def _client(port: int, token: str | None) -> ZequentClient:
    def config(name: str) -> ServiceConfig:
        return ServiceConfig(service_name=name, host="127.0.0.1", port=port)

    return ZequentClient(
        connector_config=config("connector"),
        remote_control_config=config("remote-control"),
        mission_autonomy_config=config("mission-autonomy"),
        live_data_config=config("live-data"),
        resilience=ResilienceConfig(max_retry_attempts=0, retry_delay_millis=1),
        client_token=token,
    )


async def test_every_unary_call_carries_the_credential(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    async with _client(port, "tok-123") as client:
        assert client.has_client_token
        await client.connector.list_skill_contracts()
        await client.connector.list_skill_contracts()
    assert recorder.headers == ["Bearer tok-123", "Bearer tok-123"]


async def test_a_stream_carries_the_credential_too(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    received: list[str] = []
    async with _client(port, "tok-stream") as client:
        handle = client.live_data.stream_telemetry(StreamTelemetryRequest(sn="DOCK-1"), lambda r: received.append(r.sn))
        for _ in range(100):
            if received:
                break
            await asyncio.sleep(0.02)
        await handle.stop()
    assert received and recorder.headers[0] == "Bearer tok-stream"


async def test_the_environment_variable_is_used_when_no_token_is_passed(server, monkeypatch) -> None:
    recorder, port = server
    monkeypatch.setenv(ENV_VAR, "  from-env  ")
    async with _client(port, None) as client:
        await client.connector.list_skill_contracts()
    assert recorder.headers == ["Bearer from-env"]
    assert resolve_token("explicit") == "explicit", "an explicit token wins over the environment"


async def test_without_any_credential_nothing_is_sent_and_the_refusal_names_the_variable(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    recorder.refuse = (grpc.StatusCode.UNAUTHENTICATED, "Authentication required")
    async with _client(port, None) as client:
        assert not client.has_client_token
        with pytest.raises(grpc.aio.AioRpcError) as refused:
            await client.connector.list_skill_contracts()
    assert recorder.headers == [None]
    assert isinstance(refused.value, ZequentAuthError)
    assert refused.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert ENV_VAR in refused.value.details()
    assert "Authentication required" in refused.value.details(), "the platform's own reason is kept"


async def test_a_call_outside_the_credentials_scope_says_so_and_is_not_retried(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    recorder.refuse = (
        grpc.StatusCode.PERMISSION_DENIED,
        "Asset X is not one of this credential's organization's assets",
    )
    async with _client(port, "tok") as client:
        with pytest.raises(ZequentAuthError) as refused:
            await client.connector.list_skill_contracts()
    assert refused.value.code() == grpc.StatusCode.PERMISSION_DENIED
    assert "own organization" in refused.value.details()
    assert len(recorder.headers) == 1


async def test_a_refused_stream_reports_the_explained_error(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    recorder.refuse = (grpc.StatusCode.UNAUTHENTICATED, "Credential has been revoked")
    errors: list[BaseException] = []
    async with _client(port, "revoked") as client:
        handle = client.live_data.stream_telemetry(StreamTelemetryRequest(sn="DOCK-1"), lambda r: None, errors.append)
        for _ in range(100):
            if errors:
                break
            await asyncio.sleep(0.02)
        await handle.stop()
    assert errors and isinstance(errors[0], ZequentAuthError)
    assert "revoked" in errors[0].details()

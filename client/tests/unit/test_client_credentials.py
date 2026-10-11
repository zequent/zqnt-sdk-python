"""The client credential travels on every call, unary and streaming, and refusals say what to do.

Against a real ``grpc.aio`` server on a free port, so the header asserted is the one on the wire.
"""

from __future__ import annotations

import asyncio

import grpc
import grpc.aio
import pytest
from zqnt_api.generated.zqnt import (  # type: ignore[import]
    connector_pb2,
    connector_pb2_grpc,
)
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.telemetry.v3 import telemetry_pb2, telemetry_pb2_grpc

from client_sdk import CommandError, ZequentClient
from client_sdk.auth import ENV_VAR, ZequentAuthError, resolve_token
from client_sdk.config.resilience import ResilienceConfig
from client_sdk.config.service_config import ServiceConfig


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


class _Telemetry(telemetry_pb2_grpc.TelemetryServiceServicer):
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def WatchTelemetry(self, request, context):  # noqa: N802 - gRPC naming
        await self._recorder.check(context)
        yield telemetry_pb2.WatchTelemetryResponse(
            sample=telemetry_pb2.TelemetrySample(asset=common_pb2.AssetRef(sn=request.assets[0].sn))
        )


@pytest.fixture
async def server():
    recorder = _Recorder()
    srv = grpc.aio.server()
    connector_pb2_grpc.add_ConnectorServiceServicer_to_server(_Connector(recorder), srv)
    telemetry_pb2_grpc.add_TelemetryServiceServicer_to_server(_Telemetry(recorder), srv)
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
    async with _client(port, "tok-stream") as client, asyncio.timeout(5):
        async for sample in client.telemetry.watch_telemetry(["DOCK-1"]):
            received.append(sample.asset.sn)
            break
    assert received == ["DOCK-1"] and recorder.headers[0] == "Bearer tok-stream"


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


async def test_a_refused_stream_reports_the_platforms_reason(server, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    recorder, port = server
    recorder.refuse = (grpc.StatusCode.UNAUTHENTICATED, "Credential has been revoked")
    async with _client(port, "revoked") as client, asyncio.timeout(5):
        with pytest.raises(CommandError) as refused:
            async for _ in client.telemetry.watch_telemetry(["DOCK-1"]):
                pass
    assert refused.value.status == grpc.StatusCode.UNAUTHENTICATED
    assert refused.value.category == common_pb2.ERROR_CATEGORY_PERMISSION_DENIED
    assert "revoked" in str(refused.value)

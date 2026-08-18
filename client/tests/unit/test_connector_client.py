"""Unit tests for ``ConnectorClient``."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from zqnt_utils.generated.zqnt import (
    asset_pb2,
    base_pb2,
)
from zqnt_utils.generated.zqnt import (
    connector_pb2 as cp,
)
from zqnt_utils.generated.zqnt import (
    mission_autonomy_contracts_pb2 as mac,
)
from zqnt_utils.generated.zqnt import (
    mission_autonomy_dto_pb2 as mad,
)

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.connector.client import ConnectorClient
from client_sdk.exceptions import ConnectorError
from client_sdk.models.mission_autonomy import SchedulerDTO


class _FakeStub:
    def __init__(self, response) -> None:
        self._response = response
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001
            self.calls[name] = (request, timeout)
            return self._response

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


def _client(stub: Any) -> ConnectorClient:
    c = ConnectorClient.__new__(ConnectorClient)
    c._channel = None
    c._resilience = ResilienceConfig()
    from client_sdk.grpc_.resilience import GrpcResilience

    c._resilience_helper = GrpcResilience(c._resilience)
    c._stub = stub
    return c


def _error_response(cls, **extra):
    return cls(
        has_errors=True,
        error=base_pb2.GlobalErrorMessage(error_message="boom", error_code=base_pb2.ErrorCode.ERROR_CODE_SERVICE),
        **extra,
    )


# ---------------------------------------------------------------------------
# Asset / sub-asset CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_asset_round_trips() -> None:
    asset = asset_pb2.AssetProtoDTO(id="a1", sn="SN-1", name="Dock 1")
    stub = _FakeStub(cp.ConnectorResponse(has_errors=False, asset=asset))
    c = _client(stub)

    result = await c.register_asset(asset)
    assert result.id == "a1"
    assert stub.calls["RegisterAsset"][0].asset.sn == "SN-1"


@pytest.mark.asyncio
async def test_get_asset_by_sn_validates() -> None:
    c = _client(_FakeStub(cp.ConnectorResponse(has_errors=False)))
    with pytest.raises(ValueError):
        await c.get_asset_by_sn("")


@pytest.mark.asyncio
async def test_get_asset_by_sn_raises_on_error() -> None:
    stub = _FakeStub(_error_response(cp.ConnectorResponse))
    c = _client(stub)
    with pytest.raises(ConnectorError, match="boom"):
        await c.get_asset_by_sn("SN-1")


@pytest.mark.asyncio
async def test_deregister_asset_sends_bare_request_base() -> None:
    stub = _FakeStub(cp.ConnectorResponse(has_errors=False))
    c = _client(stub)
    await c.deregister_asset("SN-1")
    sent = stub.calls["DeregisterAsset"][0]
    assert isinstance(sent, base_pb2.RequestBase)
    assert sent.sn == "SN-1"


@pytest.mark.asyncio
async def test_update_asset_with_mask() -> None:
    asset = asset_pb2.AssetProtoDTO(id="a1", name="Renamed")
    stub = _FakeStub(cp.ConnectorResponse(has_errors=False, asset=asset))
    c = _client(stub)

    result = await c.update_asset("a1", asset, update_mask=["name"])
    assert result.name == "Renamed"
    sent = stub.calls["UpdateAsset"][0]
    assert list(sent.update_mask.paths) == ["name"]


@pytest.mark.asyncio
async def test_get_sub_asset_by_sn() -> None:
    sub_asset = asset_pb2.SubAssetProtoDTO(id="sub1", sn="SUB-1")
    stub = _FakeStub(cp.ConnectorResponse(has_errors=False, sub_asset=sub_asset))
    c = _client(stub)
    result = await c.get_sub_asset_by_sn("SUB-1")
    assert result.id == "sub1"


# ---------------------------------------------------------------------------
# Asset payloads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_asset_payload_requires_owner() -> None:
    c = _client(_FakeStub(cp.AssetPayloadResponse(has_errors=False)))
    payload = cp.AssetPayloadOwner()  # placeholder, not used as payload
    with pytest.raises(ValueError):
        await c.upsert_asset_payload(payload)


@pytest.mark.asyncio
async def test_upsert_asset_payload_with_asset_owner() -> None:
    payload_dto = cp.UpsertAssetPayloadRequest().payload  # empty AssetPayloadProtoDTO instance
    stub = _FakeStub(cp.AssetPayloadResponse(has_errors=False, payload=payload_dto))
    c = _client(stub)
    await c.upsert_asset_payload(payload_dto, asset_id="a1")
    sent = stub.calls["UpsertAssetPayload"][0]
    assert sent.owner.asset_id == "a1"


@pytest.mark.asyncio
async def test_list_asset_payloads_returns_list() -> None:
    stub = _FakeStub(cp.AssetPayloadListResponse(has_errors=False, payloads=[]))
    c = _client(stub)
    result = await c.list_asset_payloads(asset_id="a1")
    assert result == []


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_organization() -> None:
    from zqnt_utils.generated.zqnt import common_pb2

    org = common_pb2.OrganizationProtoDTO(id="org1", name="Acme")
    stub = _FakeStub(cp.ConnectorResponse(has_errors=False, organization=org))
    c = _client(stub)
    result = await c.get_organization(bind_code="XYZ")
    assert result.id == "org1"
    assert stub.calls["GetOrganization"][0].bind_code == "XYZ"


# ---------------------------------------------------------------------------
# Scheduler CRUD (shared wire messages with MissionAutonomyService)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_scheduler_via_connector() -> None:
    scheduler_dto = mad.SchedulerProtoDTO(
        id="s1", name="daily", cron_expression="* * * * *", command_id="dock.open_cover"
    )
    stub = _FakeStub(mac.SchedulerResponse(has_errors=False, tid="t", scheduler_id="s1", scheduler=scheduler_dto))
    c = _client(stub)
    resp = await c.create_scheduler(
        SchedulerDTO(name="daily", cron_expression="* * * * *", command_id="dock.open_cover")
    )
    assert resp.success is True
    assert resp.scheduler.id == "s1"


# ---------------------------------------------------------------------------
# Policies / technical config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_policies_by_type() -> None:
    policy = cp.PolicyProtoDTO(id="p1", name="policy-1", policy_type="SELECTION")
    stub = _FakeStub(cp.ConnectorPolicyResponse(has_errors=False, policy_list=cp.PolicyProtoDTOList(policies=[policy])))
    c = _client(stub)
    result = await c.get_active_policies_by_type("SELECTION")
    assert [p.id for p in result] == ["p1"]


@pytest.mark.asyncio
async def test_get_technical_configs() -> None:
    cfg = cp.TechnicalConfigProtoDTO(id="c1", config_key="max_altitude")
    stub = _FakeStub(
        cp.ConnectorConfigResponse(has_errors=False, config_list=cp.TechnicalConfigProtoDTOList(configs=[cfg]))
    )
    c = _client(stub)
    result = await c.get_technical_configs(scope="GLOBAL")
    assert [x.id for x in result] == ["c1"]


# ---------------------------------------------------------------------------
# Skill Registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observe_skill_contract() -> None:
    contract = cp.SkillContractProtoDTO(id="sc1", command_id="dock.open_cover")
    stub = _FakeStub(cp.SkillContractResponse(has_errors=False, contract=contract))
    c = _client(stub)
    result = await c.observe_skill_contract(contract)
    assert result.id == "sc1"


@pytest.mark.asyncio
async def test_list_skill_contracts_by_command_id() -> None:
    contract = cp.SkillContractProtoDTO(id="sc1", command_id="dock.open_cover")
    stub = _FakeStub(cp.SkillContractListResponse(has_errors=False, contracts=[contract]))
    c = _client(stub)
    result = await c.list_skill_contracts(command_id="dock.open_cover")
    assert [x.id for x in result] == ["sc1"]
    assert stub.calls["ListSkillContracts"][0].command_id == "dock.open_cover"


@pytest.mark.asyncio
async def test_set_skill_contract_status_and_permissions() -> None:
    contract = cp.SkillContractProtoDTO(id="sc1", status=cp.SkillContractStatus.SKILL_CONTRACT_STATUS_DEPRECATED)
    stub = _FakeStub(cp.SkillContractResponse(has_errors=False, contract=contract))
    c = _client(stub)
    result = await c.set_skill_contract_status("sc1", cp.SkillContractStatus.SKILL_CONTRACT_STATUS_DEPRECATED)
    assert result.status == cp.SkillContractStatus.SKILL_CONTRACT_STATUS_DEPRECATED

    stub2 = _FakeStub(cp.SkillContractResponse(has_errors=False, contract=contract))
    c2 = _client(stub2)
    await c2.set_skill_contract_permissions("sc1", ["mission.launch"])
    assert list(stub2.calls["SetSkillContractPermissions"][0].required_permissions) == ["mission.launch"]


@pytest.mark.asyncio
async def test_set_skill_contract_status_raises_on_error() -> None:
    stub = _FakeStub(_error_response(cp.SkillContractResponse))
    c = _client(stub)
    with pytest.raises(ConnectorError):
        await c.set_skill_contract_status("sc1", cp.SkillContractStatus.SKILL_CONTRACT_STATUS_RETIRED)


# ---------------------------------------------------------------------------
# Batch sessions
# ---------------------------------------------------------------------------


class _StreamingFakeStub:
    """Simulates a client-streaming RPC: consumes the request iterator, returns a response."""

    def __init__(self, response) -> None:
        self._response = response
        self.received: list[Any] = []

    def StoreTelemetryBatch(self, request_iterator, timeout=None):  # noqa: N802
        return self._consume(request_iterator)

    def StoreDetectionBatch(self, request_iterator, timeout=None):  # noqa: N802
        return self._consume(request_iterator)

    def StoreNotificationBatch(self, request_iterator, timeout=None):  # noqa: N802
        return self._consume(request_iterator)

    async def _drain(self, request_iterator):
        async for item in request_iterator:
            self.received.append(item)
        return self._response

    def _consume(self, request_iterator):
        return asyncio.ensure_future(self._drain(request_iterator))


@pytest.mark.asyncio
async def test_telemetry_batch_session_sends_and_completes() -> None:
    stub = _StreamingFakeStub(cp.ConnectorResponse(has_errors=False))
    c = _client(stub)

    session = c.store_telemetry_batch()
    session.send(cp.ConnectorStoreTelemetryRequest())
    session.send(cp.ConnectorStoreTelemetryRequest())
    result = await session.complete()

    assert result.has_errors is False
    assert len(stub.received) == 2
    assert session.is_completed is True


@pytest.mark.asyncio
async def test_batch_session_rejects_send_after_completion() -> None:
    stub = _StreamingFakeStub(cp.ConnectorResponse(has_errors=False))
    c = _client(stub)
    session = c.store_detection_batch()
    await session.complete()
    with pytest.raises(RuntimeError):
        session.send(cp.ConnectorStoreDetectionRequest())


@pytest.mark.asyncio
async def test_batch_session_as_context_manager() -> None:
    stub = _StreamingFakeStub(cp.ConnectorResponse(has_errors=False))
    c = _client(stub)
    from zqnt_utils.generated.zqnt import events_pb2

    async with c.store_notification_batch() as session:
        session.send(events_pb2.ProduceNotificationRequest())
    assert session.is_completed is True

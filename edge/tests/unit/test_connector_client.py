"""Unit tests for ``ConnectorClient`` and the Asset/SubAsset proto converters.

Regression coverage for the current ``asset.proto`` schema (``system_connection_string``,
``live_stream_push_url``/``live_stream_pull_url``, ``sub_assets`` repeated field — the old
``connection_string``/``port``/``live_stream_server``/``online``/``stream_type``/``sub_asset_dto``
fields are permanently reserved on the wire).
"""

from __future__ import annotations

from typing import Any

import pytest
from zqnt_utils.generated.zqnt import common_pb2, connector_pb2

from edge_sdk.client.connector_client import ConnectorClient
from edge_sdk.models.asset import Asset, SubAsset
from edge_sdk.models.common import AssetConnection, AssetType, AssetVendor
from edge_sdk.server._converters import asset_to_proto, proto_to_asset, proto_to_sub_asset


def _client(stub: Any) -> ConnectorClient:
    c = ConnectorClient.__new__(ConnectorClient)
    c._host = "localhost"
    c._port = 50053
    c._call_timeout = 5.0
    c._max_retries = 3
    c._channel = object()
    c._stub = stub
    return c


class _FakeStub:
    def __init__(self, responses: dict[str, Any]) -> None:
        self._responses = responses
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001
            self.calls[name] = request
            return self._responses[name]

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


# ---------------------------------------------------------------------------
# Asset / SubAsset converters
# ---------------------------------------------------------------------------


def _sample_sub_asset() -> SubAsset:
    return SubAsset(
        id="sub-1",
        sn="SUB-1",
        name="Drone 1",
        type=AssetType.AIRCRAFT,
        vendor=AssetVendor.DJI,
        connection=AssetConnection.MQTT,
        model="M300",
        system_connection_string="mqtt://sub",
        live_stream_push_url="rtmp://push/sub",
        live_stream_pull_url="rtmp://pull/sub",
    )


def _sample_asset() -> Asset:
    return Asset(
        id="a1",
        sn="DOCK-1",
        name="Dock 1",
        type=AssetType.DOCK,
        vendor=AssetVendor.DJI,
        connection=AssetConnection.MQTT,
        model="DJI Dock 2",
        organization="org-1",
        system_connection_string="mqtt://dock",
        live_stream_push_url="rtmp://push/dock",
        live_stream_pull_url="rtmp://pull/dock",
        sub_assets=[_sample_sub_asset()],
    )


def test_asset_to_proto_uses_current_field_names() -> None:
    proto = asset_to_proto(_sample_asset(), common_pb2)
    assert proto.sn == "DOCK-1"
    assert proto.system_connection_string == "mqtt://dock"
    assert proto.live_stream_push_url == "rtmp://push/dock"
    assert proto.live_stream_pull_url == "rtmp://pull/dock"
    assert len(proto.sub_assets) == 1
    assert proto.sub_assets[0].sn == "SUB-1"
    # Reserved fields must never round-trip through the builder.
    assert not proto.HasField("id") or proto.id == "a1"


def test_asset_round_trips_through_proto() -> None:
    original = _sample_asset()
    proto = asset_to_proto(original, common_pb2)
    restored = proto_to_asset(proto)

    assert restored.sn == "DOCK-1"
    assert restored.organization == "org-1"
    assert restored.system_connection_string == "mqtt://dock"
    assert restored.live_stream_push_url == "rtmp://push/dock"
    assert restored.live_stream_pull_url == "rtmp://pull/dock"
    assert len(restored.sub_assets) == 1
    assert restored.sub_assets[0].sn == "SUB-1"
    assert restored.sub_assets[0].live_stream_push_url == "rtmp://push/sub"


def test_proto_to_sub_asset_decodes_optional_fields() -> None:
    proto = common_pb2.SubAssetProtoDTO(
        id="sub-2",
        sn="SUB-2",
        name="Drone 2",
        model="M30",
        stream_url_predefined=True,
    )
    sub = proto_to_sub_asset(proto)
    assert sub.sn == "SUB-2"
    assert sub.stream_url_predefined is True
    assert sub.system_connection_string is None


# ---------------------------------------------------------------------------
# ConnectorClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_asset_by_sn_found() -> None:
    asset_proto = common_pb2.AssetProtoDTO(id="a1", sn="DOCK-1", name="Dock 1", organization="org-1")
    stub = _FakeStub({"GetAssetBySn": connector_pb2.ConnectorResponse(has_errors=False, asset=asset_proto)})
    client = _client(stub)

    result = await client.get_asset_by_sn("DOCK-1")

    assert result is not None
    assert result.sn == "DOCK-1"
    sent = stub.calls["GetAssetBySn"]
    assert isinstance(sent, common_pb2.RequestBase)
    assert sent.sn == "DOCK-1"


@pytest.mark.asyncio
async def test_get_asset_by_sn_not_found() -> None:
    stub = _FakeStub({"GetAssetBySn": connector_pb2.ConnectorResponse(has_errors=False)})
    client = _client(stub)
    result = await client.get_asset_by_sn("MISSING")
    assert result is None


@pytest.mark.asyncio
async def test_register_asset_success() -> None:
    stub = _FakeStub({"RegisterAsset": connector_pb2.ConnectorResponse(has_errors=False, id="a1")})
    client = _client(stub)

    asset_id = await client.register_asset(_sample_asset())

    assert asset_id == "a1"
    sent = stub.calls["RegisterAsset"]
    assert sent.asset.sn == "DOCK-1"


@pytest.mark.asyncio
async def test_register_asset_failure_returns_none() -> None:
    stub = _FakeStub(
        {"RegisterAsset": connector_pb2.ConnectorResponse(has_errors=True, response_message="duplicate sn")}
    )
    client = _client(stub)
    result = await client.register_asset(_sample_asset())
    assert result is None


@pytest.mark.asyncio
async def test_watch_assets_yields_snapshots() -> None:
    asset_proto = common_pb2.AssetProtoDTO(id="a1", sn="DOCK-1")
    frame = connector_pb2.AssetMonitoringResponse(
        has_errors=False,
        assets=connector_pb2.ConnectorAssetList(assets=[asset_proto]),
    )

    class _StreamStub:
        def AssetMonitoring(self, request):  # noqa: N802 - gRPC name
            async def _gen():
                yield frame

            return _gen()

    client = _client(_StreamStub())
    snapshots = [snap async for snap in client.watch_assets()]

    assert len(snapshots) == 1
    assert snapshots[0][0].sn == "DOCK-1"


def test_connector_client_has_no_legacy_mission_task_methods() -> None:
    assert not hasattr(ConnectorClient, "get_mission")
    assert not hasattr(ConnectorClient, "get_task")
    assert not hasattr(ConnectorClient, "get_task_by_flight_id")

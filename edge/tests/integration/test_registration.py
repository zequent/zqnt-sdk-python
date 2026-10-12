"""
Integration tests for edge endpoint registration.

Uses fakeredis so no real Redis instance is needed.
Validates that the correct CacheKey format (zqnt:edge-endpoints:{vendor})
and JSON structure (compatible with Java EdgeEndpointDTO) are used.
"""

import json

import fakeredis
import pytest

from edge_sdk import AssetType, AssetVendor
from edge_sdk.auth import EdgeAuthConfig
from edge_sdk.server.edge_server import EdgeServer, RegistrationConfig

# ---------------------------------------------------------------------------
# EdgeEndpointDTO JSON format
# ---------------------------------------------------------------------------


def test_dto_serialises_to_java_compatible_json():
    from zqnt_api.core import EdgeEndpointDTO

    dto = EdgeEndpointDTO(
        endpoint="grpc://adapter:50051",
        online=True,
        asset_type="SENSOR",
        asset_vendor="ROS",
    )
    data = json.loads(dto.to_json())
    # Field names must match Java Jackson serialisation
    assert data["endpoint"] == "grpc://adapter:50051"
    assert data["online"] is True
    assert data["assetType"] == "SENSOR"  # camelCase – Java convention
    assert data["assetVendor"] == "ROS"


def test_dto_roundtrip():
    from zqnt_api.core import EdgeEndpointDTO

    original = EdgeEndpointDTO("grpc://x:1", True, "DOCK", "DJI")
    restored = EdgeEndpointDTO.from_json(original.to_json())
    assert restored == original


# ---------------------------------------------------------------------------
# EdgeServer registration
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis(monkeypatch):
    import redis.asyncio as aioredis

    server = fakeredis.FakeServer()
    monkeypatch.setattr(
        aioredis, "from_url", lambda url, **kw: fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)


def _server() -> EdgeServer:
    return EdgeServer(
        adapter=None,  # type: ignore[arg-type]
        registration=RegistrationConfig(
            endpoint="grpc://sensor:50051",
            asset_type=AssetType.SENSOR,
            asset_vendor=AssetVendor.ROS,
            redis_url="redis://localhost",
        ),
        auth=EdgeAuthConfig(),
    )


async def test_register_writes_the_endpoint_under_the_platform_key(fake_redis):
    await _server()._register(online=True)

    parsed = json.loads(await fake_redis.get("zqnt:edge-endpoints:ASSET_VENDOR_ROS"))
    assert parsed == {
        "endpoint": "grpc://sensor:50051",
        "online": True,
        "assetType": "ASSET_TYPE_SENSOR",
        "assetVendor": "ASSET_VENDOR_ROS",
    }


async def test_deregister_keeps_the_endpoint_and_marks_it_offline(fake_redis):
    server = _server()
    await server._register(online=True)
    await server._register(online=False)

    parsed = json.loads(await fake_redis.get("zqnt:edge-endpoints:ASSET_VENDOR_ROS"))
    assert parsed["online"] is False
    assert parsed["endpoint"] == "grpc://sensor:50051"


# ---------------------------------------------------------------------------
# RegistrationConfig.from_env()
# ---------------------------------------------------------------------------


def test_from_env_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("EDGE_ENDPOINT", "grpc://test:50051")
    monkeypatch.setenv("ASSET_TYPE", "ASSET_TYPE_SENSOR")
    monkeypatch.setenv("ASSET_VENDOR", "ASSET_VENDOR_ROS")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")

    cfg = RegistrationConfig.from_env()

    assert cfg.endpoint == "grpc://test:50051"
    assert cfg.asset_type == AssetType.SENSOR
    assert cfg.asset_vendor == AssetVendor.ROS
    assert cfg.redis_url == "redis://redis:6379"


def test_from_env_uses_default_redis_url(monkeypatch):
    monkeypatch.setenv("EDGE_ENDPOINT", "grpc://test:50051")
    monkeypatch.setenv("ASSET_TYPE", "ASSET_TYPE_DOCK")
    monkeypatch.setenv("ASSET_VENDOR", "ASSET_VENDOR_DJI")
    monkeypatch.delenv("REDIS_URL", raising=False)

    cfg = RegistrationConfig.from_env()
    assert cfg.redis_url == "redis://localhost:6379"


def test_from_env_raises_on_missing_required_var(monkeypatch):
    monkeypatch.delenv("EDGE_ENDPOINT", raising=False)
    monkeypatch.setenv("ASSET_TYPE", "DOCK")
    monkeypatch.setenv("ASSET_VENDOR", "DJI")

    with pytest.raises(KeyError):
        RegistrationConfig.from_env()

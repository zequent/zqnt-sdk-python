"""
Integration tests for edge endpoint registration.

Uses fakeredis so no real Redis instance is needed.
Validates that the correct CacheKey format (edge-endpoints:{vendor})
and JSON structure (compatible with Java EdgeEndpointDTO) are used.
"""

import json

import fakeredis.aioredis as fakeredis
import pytest

from edge_sdk import AssetType, AssetVendor
from edge_sdk.server.edge_server import RegistrationConfig

# ---------------------------------------------------------------------------
# Fixture: CachingService with injected fakeredis
# ---------------------------------------------------------------------------


@pytest.fixture
async def fake_cache():
    """CachingService backed by fakeredis – no real Redis needed."""
    from zqnt_utils.caching import CachingService

    svc = CachingService("redis://localhost")
    svc._client = fakeredis.FakeRedis(decode_responses=True)
    yield svc
    await svc.close()


# ---------------------------------------------------------------------------
# CacheKeys
# ---------------------------------------------------------------------------


def test_edge_endpoints_key_format():
    from zqnt_utils.caching import CacheKeys

    assert CacheKeys.EDGE_ENDPOINTS.build(vendor="DJI") == "edge-endpoints:DJI"
    assert CacheKeys.EDGE_ENDPOINTS.build(vendor="ROS") == "edge-endpoints:ROS"


def test_edge_vendor_key_format():
    from zqnt_utils.caching import CacheKeys

    assert CacheKeys.EDGE_VENDOR.build(sn="SENSOR-001") == "edge-vendor:SENSOR-001"


def test_asset_dto_key_format():
    from zqnt_utils.caching import CacheKeys

    assert CacheKeys.ASSET_DTO.build(sn="DOCK-007") == "asset-dto:DOCK-007"


# ---------------------------------------------------------------------------
# EdgeEndpointDTO JSON format
# ---------------------------------------------------------------------------


def test_dto_serialises_to_java_compatible_json():
    from zqnt_utils.core import EdgeEndpointDTO

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
    from zqnt_utils.core import EdgeEndpointDTO

    original = EdgeEndpointDTO("grpc://x:1", True, "DOCK", "DJI")
    restored = EdgeEndpointDTO.from_json(original.to_json())
    assert restored == original


# ---------------------------------------------------------------------------
# CachingService – register / get / deregister
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_endpoint_writes_correct_key(fake_cache):
    from zqnt_utils.core import EdgeEndpointDTO

    dto = EdgeEndpointDTO("grpc://sensor:50051", True, "SENSOR", "ROS")
    await fake_cache.register_edge_endpoint("ROS", dto)

    raw = await fake_cache._client.get("edge-endpoints:ROS")
    assert raw is not None
    parsed = json.loads(raw)
    assert parsed["online"] is True
    assert parsed["assetVendor"] == "ROS"


@pytest.mark.asyncio
async def test_get_endpoint_returns_dto(fake_cache):
    from zqnt_utils.core import EdgeEndpointDTO

    dto = EdgeEndpointDTO("grpc://sensor:50051", True, "SENSOR", "ROS")
    await fake_cache.register_edge_endpoint("ROS", dto)

    result = await fake_cache.get_edge_endpoint("ROS")
    assert result is not None
    assert result.endpoint == "grpc://sensor:50051"
    assert result.online is True


@pytest.mark.asyncio
async def test_deregister_sets_online_false(fake_cache):
    from zqnt_utils.core import EdgeEndpointDTO

    dto = EdgeEndpointDTO("grpc://sensor:50051", True, "SENSOR", "ROS")
    await fake_cache.register_edge_endpoint("ROS", dto)

    await fake_cache.deregister_edge_endpoint("ROS")

    result = await fake_cache.get_edge_endpoint("ROS")
    assert result is not None
    assert result.online is False  # soft delete – key still exists
    assert result.endpoint == "grpc://sensor:50051"  # data preserved


@pytest.mark.asyncio
async def test_deregister_nonexistent_does_not_raise(fake_cache):
    # Must not crash – mirrors Java's null-check before deregister
    await fake_cache.deregister_edge_endpoint("UNKNOWN_VENDOR")


@pytest.mark.asyncio
async def test_register_asset_vendor(fake_cache):
    await fake_cache.register_asset_vendor("SENSOR-001", "ROS")
    vendor = await fake_cache.get_asset_vendor("SENSOR-001")
    assert vendor == "ROS"


# ---------------------------------------------------------------------------
# RegistrationConfig.from_env()
# ---------------------------------------------------------------------------


def test_from_env_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("EDGE_ENDPOINT", "grpc://test:50051")
    monkeypatch.setenv("ASSET_TYPE", "SENSOR")
    monkeypatch.setenv("ASSET_VENDOR", "ROS")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379")

    cfg = RegistrationConfig.from_env()

    assert cfg.endpoint == "grpc://test:50051"
    assert cfg.asset_type == AssetType.SENSOR
    assert cfg.asset_vendor == AssetVendor.ROS
    assert cfg.redis_url == "redis://redis:6379"


def test_from_env_uses_default_redis_url(monkeypatch):
    monkeypatch.setenv("EDGE_ENDPOINT", "grpc://test:50051")
    monkeypatch.setenv("ASSET_TYPE", "DOCK")
    monkeypatch.setenv("ASSET_VENDOR", "DJI")
    monkeypatch.delenv("REDIS_URL", raising=False)

    cfg = RegistrationConfig.from_env()
    assert cfg.redis_url == "redis://localhost:6379"


def test_from_env_raises_on_missing_required_var(monkeypatch):
    monkeypatch.delenv("EDGE_ENDPOINT", raising=False)
    monkeypatch.setenv("ASSET_TYPE", "DOCK")
    monkeypatch.setenv("ASSET_VENDOR", "DJI")

    with pytest.raises(KeyError):
        RegistrationConfig.from_env()

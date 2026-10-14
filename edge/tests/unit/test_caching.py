import fakeredis.aioredis as fakeredis
import pytest
from zqnt_api.core import EdgeEndpointDTO

from edge_sdk.caching import CacheKeys, CachingService


@pytest.fixture
async def cache():
    service = CachingService("redis://unused:6379")
    service._client = fakeredis.FakeRedis(decode_responses=True)
    yield service
    await service.close()


class _BrokenRedis:
    async def set(self, *_):
        raise ConnectionError("down")

    async def setex(self, *_):
        raise ConnectionError("down")

    async def get(self, *_):
        raise ConnectionError("down")

    async def delete(self, *_):
        raise ConnectionError("down")

    async def aclose(self):
        pass


def test_keys_match_the_platform_layout():
    assert CacheKeys.ASSET_ONLINE.build() + "SN-1" == "zqnt:asset-online:SN-1"
    assert CacheKeys.TELEMETRY.build(sn="SN-1") == "zqnt:telemetry:SN-1"
    assert CacheKeys.EDGE_VENDOR.build(sn="SN-1") == "zqnt:edge-vendor:SN-1"
    assert CacheKeys.EDGE_ENDPOINTS.build(vendor="MAVLINK") == "zqnt:edge-endpoints:MAVLINK"
    assert CacheKeys.ASSET_ACTIVE_TASKS.build(sn="SN-1", taskId="t-1") == "zqnt:asset-active-tasks:SN-1:t-1"


def test_every_key_lives_under_the_zqnt_namespace():
    assert all(key.value.startswith("zqnt:") for key in CacheKeys)


def test_from_env_reads_the_redis_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://cache:6380")

    assert CachingService.from_env()._redis_url == "redis://cache:6380"


async def test_raw_key_values(cache):
    await cache.set("k", "v")
    assert await cache.get("k") == "v"

    await cache.setex("t", 30, "x")
    assert 0 < await cache._client.ttl("t") <= 30

    await cache.delete("k", "t")
    assert await cache.get("k") is None
    assert await cache.get("t") is None


async def test_asset_vendor_mapping(cache):
    await cache.register_asset_vendor("SN-1", "MAVLINK")

    assert await cache.get_asset_vendor("SN-1") == "MAVLINK"
    assert await cache.get("zqnt:edge-vendor:SN-1") == "MAVLINK"


async def test_edge_endpoint_lifecycle(cache):
    dto = EdgeEndpointDTO(endpoint="grpc://adapter:50051", online=True, asset_type="DRONE", asset_vendor="MAVLINK")

    await cache.register_edge_endpoint("MAVLINK", dto)
    stored = await cache.get_edge_endpoint("MAVLINK")
    assert stored.endpoint == "grpc://adapter:50051"
    assert stored.online is True

    await cache.deregister_edge_endpoint("MAVLINK")
    assert (await cache.get_edge_endpoint("MAVLINK")).online is False

    await cache.delete_edge_endpoint("MAVLINK")
    assert await cache.get_edge_endpoint("MAVLINK") is None


async def test_unparseable_endpoint_reads_as_absent(cache):
    await cache.set(CacheKeys.EDGE_ENDPOINTS.build(vendor="X"), "not json")

    assert await cache.get_edge_endpoint("X") is None


async def test_deregistering_an_unknown_endpoint_writes_nothing(cache):
    await cache.deregister_edge_endpoint("NONE")

    assert await cache.get(CacheKeys.EDGE_ENDPOINTS.build(vendor="NONE")) is None


async def test_redis_failures_are_swallowed():
    service = CachingService("redis://unused:6379")
    service._client = _BrokenRedis()

    await service.set("k", "v")
    await service.setex("k", 1, "v")
    await service.delete("k")
    await service.register_asset_vendor("SN-1", "MAVLINK")
    assert await service.get("k") is None
    assert await service.get_edge_endpoint("MAVLINK") is None


async def test_context_manager_closes_the_client(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("edge_sdk.caching.service.aioredis.from_url", lambda *_, **__: fake)

    async with CachingService("redis://unused:6379") as service:
        await service.set("k", "v")
        assert service._client is fake

    assert service._client is None

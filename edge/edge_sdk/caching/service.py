import logging
import os
from typing import Any

import redis.asyncio as aioredis
from zqnt_api.core import EdgeEndpointDTO

from .keys import CacheKeys

logger = logging.getLogger(__name__)


class CachingService:
    """Async Redis client with the key layout and operations of the platform's Java CachingService.

    Failures are logged and swallowed: a missing cache must never take an adapter down.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None

    @classmethod
    def from_env(cls, url_env: str = "REDIS_URL", default: str = "redis://localhost:6379") -> "CachingService":
        return cls(os.environ.get(url_env, default))

    async def connect(self) -> None:
        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        logger.debug("CachingService connected to %s", self._redis_url)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "CachingService":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def register_edge_endpoint(self, vendor: str, dto: EdgeEndpointDTO) -> None:
        key = CacheKeys.EDGE_ENDPOINTS.build(vendor=vendor)
        await self._safe_set(key, dto.to_json(), op=f"registerEdgeEndpoint[{vendor}]")

    async def get_edge_endpoint(self, vendor: str) -> EdgeEndpointDTO | None:
        key = CacheKeys.EDGE_ENDPOINTS.build(vendor=vendor)
        data = await self._safe_get(key, op=f"getEdgeEndpoint[{vendor}]")
        if data is None:
            return None
        try:
            return EdgeEndpointDTO.from_json(data)
        except Exception as exc:
            logger.error("Failed to parse EdgeEndpointDTO for vendor %s: %s", vendor, exc)
            return None

    async def deregister_edge_endpoint(self, vendor: str) -> None:
        dto = await self.get_edge_endpoint(vendor)
        if dto is None:
            logger.warning("Cannot deregister non-existent endpoint for vendor: %s", vendor)
            return
        dto.online = False
        key = CacheKeys.EDGE_ENDPOINTS.build(vendor=vendor)
        await self._safe_set(key, dto.to_json(), op=f"deregisterEdgeEndpoint[{vendor}]")

    async def delete_edge_endpoint(self, vendor: str) -> None:
        await self.delete(CacheKeys.EDGE_ENDPOINTS.build(vendor=vendor))

    async def register_asset_vendor(self, sn: str, vendor: str) -> None:
        key = CacheKeys.EDGE_VENDOR.build(sn=sn)
        await self._safe_set(key, vendor, op=f"registerAssetVendor[{sn},{vendor}]")

    async def get_asset_vendor(self, sn: str) -> str | None:
        return await self._safe_get(CacheKeys.EDGE_VENDOR.build(sn=sn), op=f"getAssetVendor[{sn}]")

    async def set(self, key: str, value: str) -> None:
        await self._safe_set(key, value, op=f"set[{key}]")

    async def setex(self, key: str, ttl_seconds: int, value: str) -> None:
        try:
            client = await self._get_client()
            await client.setex(key, ttl_seconds, value)
        except Exception as exc:
            logger.error("Redis setex[%s] failed: %s", key, exc)

    async def get(self, key: str) -> str | None:
        return await self._safe_get(key, op=f"get[{key}]")

    async def delete(self, *keys: str) -> None:
        try:
            client = await self._get_client()
            await client.delete(*keys)
        except Exception as exc:
            logger.error("Redis delete%s failed: %s", keys, exc)

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            await self.connect()
        return self._client

    async def _safe_set(self, key: str, value: str, *, op: str) -> None:
        try:
            client = await self._get_client()
            await client.set(key, value)
        except Exception as exc:
            logger.error("Redis operation '%s' failed: %s", op, exc)

    async def _safe_get(self, key: str, *, op: str) -> str | None:
        try:
            client = await self._get_client()
            return await client.get(key)
        except Exception as exc:
            logger.error("Redis operation '%s' failed: %s", op, exc)
            return None

"""Unit tests for the channel factory."""

from __future__ import annotations

import grpc.aio
import pytest

from client_sdk.config.service_config import LoadBalancerType, ServiceConfig
from client_sdk.grpc_.channel_factory import create_channel


@pytest.mark.asyncio
async def test_create_plaintext_channel_returns_aio_channel() -> None:
    config = ServiceConfig(
        service_name="remote-control",
        host="localhost",
        port=8002,
        use_plaintext=True,
    )
    channel = create_channel(config)
    try:
        assert isinstance(channel, grpc.aio.Channel)
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_create_secure_channel_when_plaintext_disabled() -> None:
    config = ServiceConfig(
        service_name="remote-control",
        host="example.com",
        port=443,
        use_plaintext=False,
    )
    channel = create_channel(config)
    try:
        assert isinstance(channel, grpc.aio.Channel)
    finally:
        await channel.close()


@pytest.mark.asyncio
async def test_create_channel_with_stork_uses_dns_target() -> None:
    config = ServiceConfig(
        service_name="remote-control",
        host="ignored",
        port=0,
        use_plaintext=True,
        use_stork=True,
        stork_service_name="remote-control-service",
        load_balancer_type=LoadBalancerType.ROUND_ROBIN,
    )
    channel = create_channel(config)
    try:
        assert isinstance(channel, grpc.aio.Channel)
    finally:
        await channel.close()

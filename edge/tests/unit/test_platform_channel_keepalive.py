"""Channels into the platform ping while idle, so quiet streams outlive the server's idle timeout."""

import grpc.aio
import pytest

from edge_sdk import auth
from edge_sdk.auth import (
    DEFAULT_KEEPALIVE_TIME_MS,
    KEEPALIVE_TIME_ENV,
    platform_channel,
    platform_channel_options,
)

QUARKUS_IDLE_TIMEOUT_MS = 30 * 60 * 1000


def test_default_options_ping_idle_channels_well_within_the_server_idle_timeout():
    options = dict(platform_channel_options({}))
    assert options["grpc.keepalive_time_ms"] == DEFAULT_KEEPALIVE_TIME_MS
    assert options["grpc.keepalive_time_ms"] < QUARKUS_IDLE_TIMEOUT_MS
    assert options["grpc.keepalive_timeout_ms"] > 0
    assert options["grpc.keepalive_permit_without_calls"] == 1
    assert options["grpc.http2.max_pings_without_data"] == 0


def test_the_interval_can_be_overridden():
    options = dict(platform_channel_options({KEEPALIVE_TIME_ENV: "240000"}))
    assert options["grpc.keepalive_time_ms"] == 240_000


@pytest.mark.parametrize("bad", ["abc", "0", "-5", "500"])
def test_an_unusable_override_falls_back_to_the_default(bad):
    options = dict(platform_channel_options({KEEPALIVE_TIME_ENV: bad}))
    assert options["grpc.keepalive_time_ms"] == DEFAULT_KEEPALIVE_TIME_MS


@pytest.mark.parametrize("token", ["edge-token", None])
async def test_platform_channel_is_opened_with_the_keepalive_options(monkeypatch, token):
    monkeypatch.delenv("ZQNT_INTERNAL_TLS", raising=False)
    monkeypatch.delenv(KEEPALIVE_TIME_ENV, raising=False)
    seen = {}
    real = grpc.aio.insecure_channel

    def spy(target, options=None, **kwargs):
        seen["target"] = target
        seen["options"] = dict(options or [])
        return real(target, options=options, **kwargs)

    monkeypatch.setattr(auth.InternalTls, "aio_channel", _with_spy(spy))
    channel = platform_channel("live-data-service-headless", 8003, token)
    try:
        assert seen["target"] == "live-data-service-headless:8003"
        assert seen["options"]["grpc.keepalive_time_ms"] == DEFAULT_KEEPALIVE_TIME_MS
        assert seen["options"]["grpc.keepalive_permit_without_calls"] == 1
        assert seen["options"]["grpc.http2.max_pings_without_data"] == 0
    finally:
        await channel.close()


def _with_spy(spy):
    def aio_channel(self, target, options=None, interceptors=None):
        return spy(target, options=options, interceptors=interceptors)

    return aio_channel

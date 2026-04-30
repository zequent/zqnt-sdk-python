"""Unit tests for ZequentClient lifecycle."""

from __future__ import annotations

import pytest

from client_sdk import ZequentClient
from client_sdk.config.service_config import ServiceConfig


def _config(name: str, port: int) -> ServiceConfig:
    return ServiceConfig(service_name=name, host="localhost", port=port)


@pytest.mark.asyncio
async def test_client_opens_three_channels_and_closes_them() -> None:
    client = ZequentClient(
        remote_control_config=_config("remote-control", 8002),
        mission_autonomy_config=_config("mission-autonomy", 8004),
        live_data_config=_config("live-data", 8003),
    )
    assert client.remote_control_channel is not None
    assert client.mission_autonomy_channel is not None
    assert client.live_data_channel is not None

    await client.close()
    # close() must be idempotent.
    await client.close()


@pytest.mark.asyncio
async def test_client_async_context_manager_closes_channels() -> None:
    async with ZequentClient(
        remote_control_config=_config("remote-control", 8002),
        mission_autonomy_config=_config("mission-autonomy", 8004),
        live_data_config=_config("live-data", 8003),
    ) as client:
        assert client.remote_control_channel is not None


@pytest.mark.asyncio
async def test_from_env_uses_defaults_when_no_vars_set(monkeypatch) -> None:
    # Strip any inherited env vars so the loader falls back to defaults.
    for key in list(__import__("os").environ):
        if key.endswith(("_HOST", "_PORT", "_USE_PLAINTEXT", "_USE_STORK",
                         "_STORK_NAME", "_LOAD_BALANCER")) and key.startswith(
            ("REMOTE_CONTROL_SERVICE", "MISSION_AUTONOMY_SERVICE", "LIVE_DATA_SERVICE")
        ):
            monkeypatch.delenv(key, raising=False)

    client = ZequentClient.from_env()
    try:
        assert client.remote_control_channel is not None
        assert client.mission_autonomy_channel is not None
        assert client.live_data_channel is not None
    finally:
        await client.close()

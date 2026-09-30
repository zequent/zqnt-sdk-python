"""
ZequentClient – top-level facade for all Zequent Framework services.

Mirrors the Java client SDK (``com.zqnt.sdk.client.ZequentClient``) so that
``.env`` files and configuration concepts are interchangeable between the
Java and Python SDKs.

Sub-clients (connector, remote_control, mission_autonomy, live_data) are all wired; the channel
lifecycle below is complete.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Self

import grpc.aio

from .auth import ENV_VAR, resolve_token
from .config.resilience import ResilienceConfig
from .config.service_config import ServiceConfig
from .grpc_.channel_factory import create_channel

if TYPE_CHECKING:
    from .connector.client import ConnectorClient
    from .live_data.client import LiveDataClient
    from .mission_autonomy.client import MissionAutonomyClient
    from .remote_control.client import RemoteControlClient

logger = logging.getLogger(__name__)


class ZequentClient:
    """
    Top-level entrypoint. Holds one ``grpc.aio.Channel`` per service and
    exposes typed sub-clients:

        client.connector
        client.remote_control
        client.mission_autonomy
        client.live_data

    Use as an async context manager to ensure channels are closed::

        async with ZequentClient.from_env() as client:
            ...
    """

    def __init__(
        self,
        connector_config: ServiceConfig,
        remote_control_config: ServiceConfig,
        mission_autonomy_config: ServiceConfig,
        live_data_config: ServiceConfig,
        resilience: ResilienceConfig | None = None,
        client_token: str | None = None,
    ) -> None:
        """``client_token``: the client credential issued in the console (Access & Integrations >
        Credentials, kind "client"). When omitted, ``ZQNT_CLIENT_TOKEN`` is used; with neither, the
        platform refuses every call."""
        self._connector_config = connector_config
        self._remote_control_config = remote_control_config
        self._mission_autonomy_config = mission_autonomy_config
        self._live_data_config = live_data_config
        self._client_token = resolve_token(client_token)
        if self._client_token is None:
            logger.warning(
                "No client credential configured (%s or client_token=...): the platform will refuse every call",
                ENV_VAR,
            )
        self._resilience = resilience or ResilienceConfig()

        # Channels are created eagerly so that connection problems surface
        # at construction time rather than on the first RPC.
        self._connector_channel: grpc.aio.Channel = create_channel(connector_config, self._client_token)
        self._remote_control_channel: grpc.aio.Channel = create_channel(remote_control_config, self._client_token)
        self._mission_autonomy_channel: grpc.aio.Channel = create_channel(mission_autonomy_config, self._client_token)
        self._live_data_channel: grpc.aio.Channel = create_channel(live_data_config, self._client_token)
        self._channels: list[grpc.aio.Channel] = [
            self._connector_channel,
            self._remote_control_channel,
            self._mission_autonomy_channel,
            self._live_data_channel,
        ]
        self._closed = False

        # Lazy sub-clients.
        self._connector: "ConnectorClient | None" = None
        self._remote_control: "RemoteControlClient | None" = None
        self._mission_autonomy: "MissionAutonomyClient | None" = None
        self._live_data: "LiveDataClient | None" = None

        logger.info("ZequentClient initialized with %d channels", len(self._channels))

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "ZequentClient":
        """Build a client from environment variables.

        Honours the same env var names as the Java SDK
        (``REMOTE_CONTROL_SERVICE_HOST``, ``_PORT``, ``_USE_PLAINTEXT``, ...).
        See ``core/docs/client-sdk/CONFIGURATION.md`` for the full list.
        """
        from .config.env_loader import load_from_env

        return load_from_env(cls)

    # ------------------------------------------------------------------
    # Configuration / channel access
    # ------------------------------------------------------------------

    @property
    def has_client_token(self) -> bool:
        """Whether a client credential is sent (the token itself is never exposed)."""
        return self._client_token is not None

    @property
    def resilience(self) -> ResilienceConfig:
        return self._resilience

    @property
    def connector_channel(self) -> grpc.aio.Channel:
        return self._connector_channel

    @property
    def remote_control_channel(self) -> grpc.aio.Channel:
        return self._remote_control_channel

    @property
    def mission_autonomy_channel(self) -> grpc.aio.Channel:
        return self._mission_autonomy_channel

    @property
    def live_data_channel(self) -> grpc.aio.Channel:
        return self._live_data_channel

    # ------------------------------------------------------------------
    # Sub-clients
    # ------------------------------------------------------------------

    @property
    def connector(self) -> "ConnectorClient":
        if self._connector is None:
            from .connector.client import ConnectorClient

            self._connector = ConnectorClient(self._connector_channel, self._resilience)
        return self._connector

    @property
    def remote_control(self) -> "RemoteControlClient":
        if self._remote_control is None:
            from .remote_control.client import RemoteControlClient

            self._remote_control = RemoteControlClient(self._remote_control_channel, self._resilience)
        return self._remote_control

    @property
    def mission_autonomy(self) -> "MissionAutonomyClient":
        if self._mission_autonomy is None:
            from .mission_autonomy.client import MissionAutonomyClient

            self._mission_autonomy = MissionAutonomyClient(self._mission_autonomy_channel, self._resilience)
        return self._mission_autonomy

    @property
    def live_data(self) -> "LiveDataClient":
        if self._live_data is None:
            from .live_data.client import LiveDataClient

            self._live_data = LiveDataClient(self._live_data_channel, self._resilience)
        return self._live_data

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        """Shut down every gRPC channel held by this client."""
        if self._closed:
            return
        self._closed = True
        logger.info("Shutting down ZequentClient (%d channels)", len(self._channels))
        for channel in self._channels:
            try:
                await channel.close()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error closing gRPC channel")
        logger.info("ZequentClient closed")

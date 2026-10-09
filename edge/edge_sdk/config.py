"""
EdgeAdapterConfig and EdgeAdapterRuntime
=========================================

Centralises all environment-variable reading and standard lifecycle
management for edge adapters.

Typical usage::

    async def _serve() -> None:
        config = EdgeAdapterConfig.from_env()
        async with config.runtime() as runtime:
            adapter = MyAdapter(connector=runtime.connector)
            await runtime.serve(adapter)

Environment variables (all optional, sensible defaults provided):

    GRPC_HOST           Bind host for the gRPC EdgeServer (default: 0.0.0.0)
    GRPC_PORT           Port for the gRPC EdgeServer (default: 50051)
    CONNECTOR_HOST      ConnectorService host (default: localhost)
    CONNECTOR_PORT      ConnectorService port (default: 50053)
    TELEMETRY_HOST      LiveDataService host (default: localhost)
    TELEMETRY_PORT      LiveDataService port (default: 50052)
    MISSION_AUTONOMY_HOST  MissionAutonomyService host (default: localhost)
    MISSION_AUTONOMY_PORT  MissionAutonomyService port (default: 50054)
    REMOTE_CONTROL_HOST remote-control host (EdgeGatewayService: capability reports, command
                        events). Unset: capabilities are not pushed, events go over v2.
    REMOTE_CONTROL_PORT remote-control port (default: 8002)
    ADAPTER_SN          Adapter identifier used for logging (default: "").
                        Each telemetry frame carries the asset's own SN — this
                        does not need to match an asset SN for multi-asset adapters.
    LOG_LEVEL           Python log level name (default: INFO)
    LOG_FORMAT          "json" or "text" (default: json)

    Optional – automatic Redis service-discovery registration:
    EDGE_ENDPOINT       gRPC endpoint advertised to the platform
    ASSET_TYPE          AssetType proto name, e.g. ASSET_TYPE_AIRCRAFT
    ASSET_VENDOR        AssetVendor proto name, e.g. ASSET_VENDOR_MAVLINK
    REDIS_URL           Redis URL (default: redis://localhost:6379)

    Authentication (see edge_sdk.auth):
    ZQNT_EDGE_TOKEN           Edge credential for calls into the platform (issued in the console)
    ZQNT_PLATFORM_PUBLIC_KEY  The platform's service public key (SERVICE_AUTH_PUBLIC_KEY); commands
                              without a token it verifies are refused. Alias: SERVICE_AUTH_PUBLIC_KEY
    ZQNT_EDGE_AUTH_DISABLED   "true" accepts unauthenticated commands — local SITL/simulators only
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from typing import TYPE_CHECKING

from .auth import EdgeAuthConfig

if TYPE_CHECKING:
    from .adapter.base import EdgeAdapter
    from .client.connector_client import ConnectorClient
    from .client.edge_gateway import EdgeGatewayClient
    from .client.mission_autonomy_client import MissionAutonomyClient
    from .client.telemetry_ingest import TelemetryIngestPublisher
    from .client.telemetry_publisher import TelemetryPublisher

logger = logging.getLogger(__name__)


def _setup_logging(level: str, fmt: str) -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    if fmt.lower() == "json":
        try:
            from pythonjsonlogger.json import JsonFormatter  # type: ignore[import-untyped]

            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter())
            logging.basicConfig(handlers=[handler], level=log_level, force=True)
            return
        except ImportError:
            pass
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        force=True,
    )


class EdgeAdapterRuntime:
    """
    Holds the initialised SDK clients and exposes :meth:`serve`.

    Obtain an instance via ``async with EdgeAdapterConfig(...).runtime() as rt:``.

    Attributes:
        connector:         Connected :class:`~edge_sdk.ConnectorClient`.
        telemetry:         Running :class:`~edge_sdk.TelemetryPublisher` (v2).
        ingest:            :class:`~edge_sdk.TelemetryIngestPublisher` (v3 samples, detections, alerts).
        mission_autonomy:  Connected :class:`~edge_sdk.MissionAutonomyClient`.
        gateway:           :class:`~edge_sdk.EdgeGatewayClient` when REMOTE_CONTROL_HOST is set, else None.
    """

    def __init__(
        self,
        config: "EdgeAdapterConfig",
    ) -> None:
        self._config = config
        self.connector: "ConnectorClient" = None  # type: ignore[assignment]
        self.telemetry: "TelemetryPublisher" = None  # type: ignore[assignment]
        self.mission_autonomy: "MissionAutonomyClient" = None  # type: ignore[assignment]
        self.ingest: "TelemetryIngestPublisher" = None  # type: ignore[assignment]
        self.gateway: "EdgeGatewayClient | None" = None

    async def __aenter__(self) -> "EdgeAdapterRuntime":
        from .client.connector_client import ConnectorClient
        from .client.edge_gateway import EdgeGatewayClient
        from .client.mission_autonomy_client import MissionAutonomyClient
        from .client.telemetry_ingest import TelemetryIngestPublisher
        from .client.telemetry_publisher import TelemetryPublisher

        _setup_logging(self._config.log_level, self._config.log_format)

        self.connector = ConnectorClient(
            host=self._config.connector_host,
            port=self._config.connector_port,
            claim_code=self._config.claim_code,
            token=self._config.auth.edge_token,
        )
        self.telemetry = TelemetryPublisher(
            host=self._config.telemetry_host,
            port=self._config.telemetry_port,
            sn=self._config.adapter_sn,
            token=self._config.auth.edge_token,
        )
        self.mission_autonomy = MissionAutonomyClient(
            host=self._config.mission_autonomy_host,
            port=self._config.mission_autonomy_port,
            token=self._config.auth.edge_token,
        )
        self.ingest = TelemetryIngestPublisher(
            host=self._config.telemetry_host,
            port=self._config.telemetry_port,
            token=self._config.auth.edge_token,
        )
        if self._config.remote_control_host:
            self.gateway = EdgeGatewayClient(
                host=self._config.remote_control_host,
                port=self._config.remote_control_port,
                token=self._config.auth.edge_token,
            )

        await self.connector.connect()
        await self.telemetry.connect()
        await self.mission_autonomy.connect()
        logger.info(
            "EdgeAdapterRuntime started [grpc=%s:%d connector=%s:%d telemetry=%s:%d mission_autonomy=%s:%d sn=%s]",
            self._config.grpc_host,
            self._config.grpc_port,
            self._config.connector_host,
            self._config.connector_port,
            self._config.telemetry_host,
            self._config.telemetry_port,
            self._config.mission_autonomy_host,
            self._config.mission_autonomy_port,
            self._config.adapter_sn,
        )
        return self

    async def __aexit__(self, *_exc) -> None:
        if self.telemetry is not None:
            await self.telemetry.close()
        if self.ingest is not None:
            await self.ingest.close()
        if self.gateway is not None:
            await self.gateway.close()
        if self.connector is not None:
            await self.connector.close()
        if self.mission_autonomy is not None:
            await self.mission_autonomy.close()
        logger.info("EdgeAdapterRuntime stopped")

    async def serve(self, adapter: "EdgeAdapter") -> None:
        """
        Create an :class:`~edge_sdk.EdgeServer`, wire in the optional
        :class:`~edge_sdk.RegistrationConfig`, and block until termination.
        """
        from .models.common import AssetType, AssetVendor, proto_enum_lookup
        from .server.edge_server import EdgeServer, RegistrationConfig

        cfg = self._config
        registration: RegistrationConfig | None = None
        if cfg.edge_endpoint and cfg.asset_type_name and cfg.asset_vendor_name:
            try:
                registration = RegistrationConfig(
                    endpoint=cfg.edge_endpoint,
                    asset_type=proto_enum_lookup(AssetType, cfg.asset_type_name),
                    asset_vendor=proto_enum_lookup(AssetVendor, cfg.asset_vendor_name),
                    redis_url=cfg.redis_url,
                )
            except KeyError as exc:
                logger.warning("Invalid ASSET_TYPE or ASSET_VENDOR in env, skipping registration: %s", exc)

        server = EdgeServer(
            adapter=adapter,
            port=cfg.grpc_port,
            host=cfg.grpc_host,
            registration=registration,
            auth=cfg.auth,
            gateway=self.gateway,
        )
        await server.serve()


@dataclasses.dataclass
class EdgeAdapterConfig:
    """
    Configuration for a ZQNT edge adapter.

    All fields have environment-variable defaults; use :meth:`from_env` in
    production and the constructor directly in tests.
    """

    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    connector_host: str = "localhost"
    connector_port: int = 50053
    telemetry_host: str = "localhost"
    telemetry_port: int = 50052
    mission_autonomy_host: str = "localhost"
    mission_autonomy_port: int = 50054
    remote_control_host: str | None = None
    remote_control_port: int = 8002
    adapter_sn: str = ""
    log_level: str = "INFO"
    log_format: str = "json"

    # Optional automatic service-discovery registration
    edge_endpoint: str | None = None
    asset_type_name: str | None = None
    asset_vendor_name: str | None = None
    redis_url: str = "redis://localhost:6379"
    # A one-time pairing code, minted in the console, that this adapter may trade for an asset the
    # platform does not know yet (ConnectorClient.ensure_asset). It decides the organization the
    # asset lands in, which is a decision an adapter cannot make for itself and which cannot be
    # corrected afterwards. Unset is the normal state once the assets exist.
    claim_code: str | None = None
    # Both directions of the adapter's gRPC traffic are authenticated — see edge_sdk.auth.
    auth: EdgeAuthConfig = dataclasses.field(default_factory=EdgeAuthConfig.from_env)

    @classmethod
    def from_env(cls) -> "EdgeAdapterConfig":
        """Build from environment variables (recommended for Kubernetes deployments)."""
        return cls(
            grpc_host=os.getenv("GRPC_HOST", "0.0.0.0"),
            grpc_port=int(os.getenv("GRPC_PORT", "50051")),
            connector_host=os.getenv("CONNECTOR_HOST", "localhost"),
            connector_port=int(os.getenv("CONNECTOR_PORT", "50053")),
            telemetry_host=os.getenv("TELEMETRY_HOST", "localhost"),
            telemetry_port=int(os.getenv("TELEMETRY_PORT", "50052")),
            mission_autonomy_host=os.getenv("MISSION_AUTONOMY_HOST", "localhost"),
            mission_autonomy_port=int(os.getenv("MISSION_AUTONOMY_PORT", "50054")),
            remote_control_host=os.getenv("REMOTE_CONTROL_HOST") or None,
            remote_control_port=int(os.getenv("REMOTE_CONTROL_PORT", "8002")),
            adapter_sn=os.getenv("ADAPTER_SN", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=os.getenv("LOG_FORMAT", "json"),
            edge_endpoint=os.getenv("EDGE_ENDPOINT"),
            asset_type_name=os.getenv("ASSET_TYPE"),
            asset_vendor_name=os.getenv("ASSET_VENDOR"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            claim_code=os.getenv("ZQNT_CLAIM_CODE") or None,
            auth=EdgeAuthConfig.from_env(),
        )

    def runtime(self) -> EdgeAdapterRuntime:
        """Return an async context manager that initialises all SDK clients."""
        return EdgeAdapterRuntime(self)

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
"""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter.base import EdgeAdapter
    from .client.connector_client import ConnectorClient
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
        connector:  Connected :class:`~edge_sdk.ConnectorClient`.
        telemetry:  Running :class:`~edge_sdk.TelemetryPublisher`.
    """

    def __init__(
        self,
        config: "EdgeAdapterConfig",
    ) -> None:
        self._config = config
        self.connector: "ConnectorClient" = None  # type: ignore[assignment]
        self.telemetry: "TelemetryPublisher" = None  # type: ignore[assignment]

    async def __aenter__(self) -> "EdgeAdapterRuntime":
        from .client.connector_client import ConnectorClient
        from .client.telemetry_publisher import TelemetryPublisher

        _setup_logging(self._config.log_level, self._config.log_format)

        self.connector = ConnectorClient(
            host=self._config.connector_host,
            port=self._config.connector_port,
        )
        self.telemetry = TelemetryPublisher(
            host=self._config.telemetry_host,
            port=self._config.telemetry_port,
            sn=self._config.adapter_sn,
        )

        await self.connector.connect()
        await self.telemetry.connect()
        logger.info(
            "EdgeAdapterRuntime started [grpc=%s:%d connector=%s:%d telemetry=%s:%d sn=%s]",
            self._config.grpc_host,
            self._config.grpc_port,
            self._config.connector_host,
            self._config.connector_port,
            self._config.telemetry_host,
            self._config.telemetry_port,
            self._config.adapter_sn,
        )
        return self

    async def __aexit__(self, *_exc) -> None:
        if self.telemetry is not None:
            await self.telemetry.close()
        if self.connector is not None:
            await self.connector.close()
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
    adapter_sn: str = ""
    log_level: str = "INFO"
    log_format: str = "json"

    # Optional automatic service-discovery registration
    edge_endpoint: str | None = None
    asset_type_name: str | None = None
    asset_vendor_name: str | None = None
    redis_url: str = "redis://localhost:6379"

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
            adapter_sn=os.getenv("ADAPTER_SN", ""),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_format=os.getenv("LOG_FORMAT", "json"),
            edge_endpoint=os.getenv("EDGE_ENDPOINT"),
            asset_type_name=os.getenv("ASSET_TYPE"),
            asset_vendor_name=os.getenv("ASSET_VENDOR"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        )

    def runtime(self) -> EdgeAdapterRuntime:
        """Return an async context manager that initialises all SDK clients."""
        return EdgeAdapterRuntime(self)

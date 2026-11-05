"""Per-service connection configuration. Mirrors Java ServiceConfig."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class LoadBalancerType(str, enum.Enum):
    ROUND_ROBIN = "ROUND_ROBIN"
    RANDOM = "RANDOM"
    LEAST_REQUESTS = "LEAST_REQUESTS"


@dataclass(slots=True)
class ServiceConfig:
    """gRPC connection settings for a single Zequent service."""

    service_name: str
    host: str = "localhost"
    port: int = 0
    use_plaintext: bool = True
    # With use_plaintext off: the CA the server certificate is verified against (PEM file), e.g.
    # the installation's internal CA; None is the system trust store.
    tls_ca_file: str | None = None
    use_stork: bool = False
    stork_service_name: str | None = None
    load_balancer_type: LoadBalancerType = LoadBalancerType.ROUND_ROBIN
    max_inbound_message_size: int = -1

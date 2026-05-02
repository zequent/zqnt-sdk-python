"""Build a ZequentClient from environment variables.

Honours the same variable names as the Java client SDK so .env files are
portable between languages. See core/docs/client-sdk/CONFIGURATION.md.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Type

from .resilience import ResilienceConfig
from .service_config import LoadBalancerType, ServiceConfig

if TYPE_CHECKING:
    from ..zequent_client import ZequentClient


_DEFAULT_PORTS = {
    "remote-control": 8002,
    "live-data": 8003,
    "mission-autonomy": 8004,
}


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


def _service(prefix: str, service_name: str) -> ServiceConfig:
    default_port = _DEFAULT_PORTS[service_name]
    return ServiceConfig(
        service_name=service_name,
        host=os.environ.get(f"{prefix}_HOST", "localhost"),
        port=_int(f"{prefix}_PORT", default_port),
        use_plaintext=_bool(f"{prefix}_USE_PLAINTEXT", True),
        use_stork=_bool(f"{prefix}_USE_STORK", False),
        stork_service_name=os.environ.get(f"{prefix}_STORK_NAME", f"{service_name}-service"),
        load_balancer_type=LoadBalancerType(
            os.environ.get(f"{prefix}_LOAD_BALANCER", LoadBalancerType.ROUND_ROBIN.value)
        ),
    )


def _resilience() -> ResilienceConfig:
    return ResilienceConfig(
        max_retry_attempts=_int("ZEQUENT_MAX_RETRY_ATTEMPTS", 3),
        retry_delay_millis=_int("ZEQUENT_RETRY_DELAY_MS", 1000),
        circuit_breaker_failure_threshold=_int("ZEQUENT_CIRCUIT_BREAKER_THRESHOLD", 5),
        circuit_breaker_wait_duration_millis=_int("ZEQUENT_CIRCUIT_BREAKER_WAIT_MS", 30000),
        connection_timeout_seconds=_int("ZEQUENT_CONNECTION_TIMEOUT_SEC", 30),
        request_timeout_seconds=_int("ZEQUENT_REQUEST_TIMEOUT_SEC", 60),
    )


def load_from_env(cls: "Type[ZequentClient]") -> "ZequentClient":
    return cls(
        remote_control_config=_service("REMOTE_CONTROL_SERVICE", "remote-control"),
        mission_autonomy_config=_service("MISSION_AUTONOMY_SERVICE", "mission-autonomy"),
        live_data_config=_service("LIVE_DATA_SERVICE", "live-data"),
        resilience=_resilience(),
    )

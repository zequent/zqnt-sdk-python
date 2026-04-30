"""Global resilience settings. Mirrors Java GrpcClientConfig resilience block."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ResilienceConfig:
    max_retry_attempts: int = 3
    retry_delay_millis: int = 1000
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_wait_duration_millis: int = 30000
    connection_timeout_seconds: int = 30
    request_timeout_seconds: int = 60

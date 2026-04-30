"""Factory for ``grpc.aio`` channels.

Mirrors the Java ``ChannelFactory`` while staying idiomatic for Python:
- async channels (``grpc.aio.Channel``)
- load-balancing policy supplied via gRPC service config JSON
- keep-alive + retry options exposed through channel options
- Stork service discovery is a Java-ecosystem feature; in Python we
  fall back to a plain DNS target and document this in the SDK README.
"""

from __future__ import annotations

import json
import logging

import grpc
import grpc.aio

from ..config.service_config import LoadBalancerType, ServiceConfig

logger = logging.getLogger(__name__)


_LB_POLICY_MAP: dict[LoadBalancerType, str] = {
    LoadBalancerType.ROUND_ROBIN: "round_robin",
    # gRPC core has no native "random" or "least_request" – fall back to
    # round_robin which is the closest stateless equivalent.
    LoadBalancerType.RANDOM: "round_robin",
    LoadBalancerType.LEAST_REQUESTS: "round_robin",
}


def _service_config_json(policy: str) -> str:
    """Return a gRPC service config JSON enabling the chosen LB policy."""
    return json.dumps({"loadBalancingConfig": [{policy: {}}]})


def _channel_options(config: ServiceConfig) -> list[tuple[str, object]]:
    options: list[tuple[str, object]] = [
        ("grpc.keepalive_time_ms", 30_000),
        ("grpc.keepalive_timeout_ms", 30_000),
        ("grpc.keepalive_permit_without_calls", 1),
        ("grpc.enable_retries", 1),
        (
            "grpc.service_config",
            _service_config_json(_LB_POLICY_MAP[config.load_balancer_type]),
        ),
    ]
    if config.max_inbound_message_size > 0:
        options.append(
            ("grpc.max_receive_message_length", config.max_inbound_message_size)
        )
    return options


def create_channel(config: ServiceConfig) -> grpc.aio.Channel:
    """Build a ``grpc.aio.Channel`` from a :class:`ServiceConfig`."""
    if config.use_stork and config.stork_service_name:
        # Stork is Java-only. In Python a Kubernetes headless Service +
        # DNS-based round-robin gives the equivalent behaviour.
        target = f"dns:///{config.stork_service_name}"
        logger.info(
            "Creating channel with DNS service discovery: %s (Stork-equivalent)",
            target,
        )
    else:
        target = f"{config.host}:{config.port}"
        logger.info("Creating direct channel: %s", target)

    options = _channel_options(config)

    if config.use_plaintext:
        channel = grpc.aio.insecure_channel(target, options=options)
    else:
        credentials = grpc.ssl_channel_credentials()
        channel = grpc.aio.secure_channel(target, credentials, options=options)

    logger.info("Channel created successfully for service: %s", config.service_name)
    return channel

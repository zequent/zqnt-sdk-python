"""gRPC infrastructure (channel factory, retry / circuit-breaker helpers)."""

from .channel_factory import create_channel

__all__ = ["create_channel"]

"""Public exception hierarchy for the Zequent client SDK.

Keep this module **small**. Only raise typed errors for cases where
callers will plausibly want to react differently than to a generic gRPC
failure. Everything else continues to surface as the underlying
``grpc.aio.AioRpcError`` so users keep full diagnostic detail.
"""

from __future__ import annotations


class ZequentClientError(Exception):
    """Base class for all errors raised by the Zequent client SDK."""


class ZequentRetryExhaustedError(ZequentClientError):
    """Raised when a unary RPC fails on every retry attempt.

    The original transport-level error (typically
    :class:`grpc.aio.AioRpcError`) is preserved as ``__cause__`` so callers
    can still inspect the underlying status code and metadata.
    """

    def __init__(self, message: str, attempts: int) -> None:
        super().__init__(message)
        self.attempts = attempts


__all__ = [
    "ZequentClientError",
    "ZequentRetryExhaustedError",
]

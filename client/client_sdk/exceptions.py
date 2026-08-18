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


class MissionAutonomyError(ZequentClientError):
    """Raised when an Application/SkillExecution RPC completes but reports ``has_errors``.

    Unlike ``RemoteControlResponse``/``LiveDataResponse``, the Application and SkillExecution
    RPCs return the raw payload DTO directly on success (``ApplicationProtoDTO``,
    ``SkillExecutionProtoDTO``, ...) rather than a wrapping response dataclass with a
    ``success`` flag — there is nowhere to carry a failure inline, so failures raise instead,
    mirroring ``MissionAutonomyClientException`` in the Java client SDK.
    """

    def __init__(self, operation: str, error_code: str | None, error_message: str | None) -> None:
        super().__init__(f"{operation}: {error_message or error_code or 'unknown error'}")
        self.operation = operation
        self.error_code = error_code
        self.error_message = error_message


class ConnectorError(ZequentClientError):
    """Raised when a Connector RPC completes but reports ``has_errors``.

    Mirrors :class:`MissionAutonomyError`'s rationale — most Connector RPCs return the raw
    payload DTO directly (``AssetProtoDTO``, ``SkillContractProtoDTO``, ...) rather than a
    wrapping response dataclass with a ``success`` flag, so failures raise instead.
    """

    def __init__(self, operation: str, error_code: str | None, error_message: str | None) -> None:
        super().__init__(f"{operation}: {error_message or error_code or 'unknown error'}")
        self.operation = operation
        self.error_code = error_code
        self.error_message = error_message


class LegacyOperationRemovedError(ZequentClientError):
    """Raised by the Mission/Task RPCs the platform has fully retired.

    No backend RPC exists for these anymore (mirrors
    ``MissionAutonomyImpl.removedLegacyOperation`` in the Java client SDK) —
    the method signatures are kept only so old call sites fail with a clear,
    actionable message instead of an ``AttributeError``/``ImportError`` deep
    in a proto converter.
    """

    def __init__(self, operation: str) -> None:
        super().__init__(f"{operation} was removed; use the Application/SkillExecution APIs instead")
        self.operation = operation


__all__ = [
    "ConnectorError",
    "LegacyOperationRemovedError",
    "MissionAutonomyError",
    "ZequentClientError",
    "ZequentRetryExhaustedError",
]

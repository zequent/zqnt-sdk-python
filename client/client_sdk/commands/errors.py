"""The error a v3 command call raises."""

from __future__ import annotations

import grpc
import grpc.aio
from zqnt_utils.generated.zqnt.capability.v3 import command_pb2
from zqnt_utils.generated.zqnt.common.v3 import common_pb2

from ..exceptions import ZequentClientError, ZequentRetryExhaustedError

_CATEGORY_BY_STATUS: dict[grpc.StatusCode, int] = {
    grpc.StatusCode.INVALID_ARGUMENT: common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
    grpc.StatusCode.OUT_OF_RANGE: common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT,
    grpc.StatusCode.PERMISSION_DENIED: common_pb2.ERROR_CATEGORY_PERMISSION_DENIED,
    grpc.StatusCode.UNAUTHENTICATED: common_pb2.ERROR_CATEGORY_PERMISSION_DENIED,
    grpc.StatusCode.FAILED_PRECONDITION: common_pb2.ERROR_CATEGORY_PRECONDITION_FAILED,
    grpc.StatusCode.ABORTED: common_pb2.ERROR_CATEGORY_PRECONDITION_FAILED,
    grpc.StatusCode.ALREADY_EXISTS: common_pb2.ERROR_CATEGORY_PRECONDITION_FAILED,
    grpc.StatusCode.NOT_FOUND: common_pb2.ERROR_CATEGORY_NOT_FOUND,
    grpc.StatusCode.UNIMPLEMENTED: common_pb2.ERROR_CATEGORY_NOT_FOUND,
    grpc.StatusCode.DEADLINE_EXCEEDED: common_pb2.ERROR_CATEGORY_TIMEOUT,
}

_RETRYABLE_STATUSES = frozenset(
    {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.RESOURCE_EXHAUSTED}
)


_REJECTED = ("was rejected", common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT)

_OUTCOME_BY_STATE: dict[int, tuple[str, int]] = {
    command_pb2.COMMAND_STATE_FAILED: ("failed", common_pb2.ERROR_CATEGORY_ASSET),
    command_pb2.COMMAND_STATE_CANCELLED: ("was cancelled", common_pb2.ERROR_CATEGORY_UNSPECIFIED),
    command_pb2.COMMAND_STATE_TIMED_OUT: ("timed out", common_pb2.ERROR_CATEGORY_TIMEOUT),
}


class CommandError(ZequentClientError):
    """A command call the platform refused, a command it ``REJECTED`` before it started, or (from
    ``execute_and_wait``) a run that ended ``FAILED``, ``CANCELLED`` or ``TIMED_OUT``.

    ``category`` is a ``zqnt.common.v3.ErrorCategory`` value (compare with
    ``common_pb2.ERROR_CATEGORY_INVALID_ARGUMENT`` etc., or read ``category_name``), ``code`` the
    stable machine-readable code (e.g. ``command.invalid_params``), ``status`` the gRPC status the
    platform answered with (``None`` for a rejected command), ``result`` the command's final result
    (``None`` when the call itself was refused or the watch ended without one).
    """

    def __init__(
        self,
        message: str,
        *,
        category: int,
        code: str = "",
        retryable: bool = False,
        status: grpc.StatusCode | None = None,
        result: command_pb2.CommandResult | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.retryable = retryable
        self.status = status
        self.result = result

    @property
    def category_name(self) -> str:
        return common_pb2.ErrorCategory.Name(self.category)

    @classmethod
    def rejected(cls, result: command_pb2.CommandResult) -> CommandError:
        return cls.of(result)

    @classmethod
    def of(cls, result: command_pb2.CommandResult) -> CommandError:
        """A command that did not succeed, from its final result: ``REJECTED``, ``FAILED``,
        ``CANCELLED`` or ``TIMED_OUT``. Without a category on the error, a rejection counts as
        ``INVALID_ARGUMENT``, a failure as ``ASSET``, a timeout as ``TIMEOUT``."""
        error = result.error
        outcome, category = _OUTCOME_BY_STATE.get(result.state, _REJECTED)
        return cls(
            error.message or f"{result.command_id} {outcome}",
            category=error.category or category,
            code=error.code,
            retryable=error.retryable,
            result=result,
        )

    @classmethod
    def from_exception(cls, exc: BaseException) -> CommandError:
        if isinstance(exc, CommandError):
            return exc
        if isinstance(exc, ZequentRetryExhaustedError) and isinstance(exc.__cause__, grpc.aio.AioRpcError):
            exc = exc.__cause__
        if isinstance(exc, grpc.aio.AioRpcError):
            code = exc.code()
            error = cls(
                exc.details() or code.name,
                category=_CATEGORY_BY_STATUS.get(code, common_pb2.ERROR_CATEGORY_SERVICE),
                code=code.name,
                retryable=code in _RETRYABLE_STATUSES,
                status=code,
            )
        else:
            error = cls(str(exc) or type(exc).__name__, category=common_pb2.ERROR_CATEGORY_SERVICE, retryable=True)
        error.__cause__ = exc
        return error

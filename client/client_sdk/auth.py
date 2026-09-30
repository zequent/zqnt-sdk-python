"""The client credential a customer application calls the Zequent platform with.

Every core service refuses a call that carries no credential. An organization administrator issues
one in the console (Deploy -> Access & Integrations -> Credentials, kind "client"); it is shown
once, acts for that one organization, and reaches only that organization's assets, Applications
and runs.

Hand it to the SDK as ``ZequentClient(..., client_token=...)`` or through the
``ZQNT_CLIENT_TOKEN`` environment variable (``ZequentClient.from_env()`` and the constructor both
read it when no token is passed). It is sent as ``authorization: Bearer <token>`` on every call.

A refusal still raises :class:`grpc.aio.AioRpcError` (so existing ``except`` clauses keep working),
as the subclass :class:`ZequentAuthError` whose ``details()`` says what to do about it.
"""

from __future__ import annotations

import os

import grpc
import grpc.aio

from .exceptions import ZequentClientError

ENV_VAR = "ZQNT_CLIENT_TOKEN"
"""The environment variable read when no token is passed explicitly."""

_AUTHORIZATION = "authorization"


def resolve_token(explicit: str | None = None) -> str | None:
    """The explicit token if one is given, else ``ZQNT_CLIENT_TOKEN``; ``None`` when neither is set."""
    for candidate in (explicit, os.environ.get(ENV_VAR)):
        if candidate is not None and candidate.strip():
            return candidate.strip()
    return None


class ZequentAuthError(grpc.aio.AioRpcError, ZequentClientError):
    """The platform refused the call: ``UNAUTHENTICATED`` (no, expired or revoked credential) or
    ``PERMISSION_DENIED`` (outside what a client credential may do). Same ``code()`` as the original
    error; ``details()`` explains; the original is kept as ``__cause__``."""


def explain(error: BaseException) -> BaseException:
    """``error`` with an actionable message if it is an authentication/authorization refusal."""
    if not isinstance(error, grpc.aio.AioRpcError) or isinstance(error, ZequentAuthError):
        return error
    code = error.code()
    original = error.details() or ""
    cause = f" ({original})" if original else ""
    if code == grpc.StatusCode.UNAUTHENTICATED:
        advice = (
            f"no client credential was sent, or it is expired, revoked or not issued by this installation. "
            f"Set {ENV_VAR} or pass ZequentClient(client_token=...); an organization administrator issues one "
            "in the console (Access & Integrations > Credentials, kind 'client')"
        )
    elif code == grpc.StatusCode.PERMISSION_DENIED:
        advice = (
            "this client credential may not do this - it reaches only its own organization's assets, "
            "Applications and runs, and never administration"
        )
    else:
        return error
    explained = ZequentAuthError(
        code,
        error.initial_metadata(),
        error.trailing_metadata(),
        details=f"Zequent refused the call: {advice}{cause}",
        debug_error_string=error.debug_error_string(),
    )
    explained.__cause__ = error
    return explained


def _with_token(details: grpc.aio.ClientCallDetails, token: str) -> grpc.aio.ClientCallDetails:
    metadata = grpc.aio.Metadata()
    if details.metadata:
        for key, value in details.metadata:
            if key.lower() != _AUTHORIZATION:
                metadata.add(key, value)
    metadata.add(_AUTHORIZATION, f"Bearer {token}")
    return grpc.aio.ClientCallDetails(
        method=details.method,
        timeout=details.timeout,
        metadata=metadata,
        credentials=details.credentials,
        wait_for_ready=details.wait_for_ready,
    )


class _BearerUnaryUnary(grpc.aio.UnaryUnaryClientInterceptor):
    def __init__(self, token: str) -> None:
        self._token = token

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(_with_token(client_call_details, self._token), request)


class _BearerUnaryStream(grpc.aio.UnaryStreamClientInterceptor):
    def __init__(self, token: str) -> None:
        self._token = token

    async def intercept_unary_stream(self, continuation, client_call_details, request):
        return await continuation(_with_token(client_call_details, self._token), request)


class _BearerStreamUnary(grpc.aio.StreamUnaryClientInterceptor):
    def __init__(self, token: str) -> None:
        self._token = token

    async def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return await continuation(_with_token(client_call_details, self._token), request_iterator)


class _BearerStreamStream(grpc.aio.StreamStreamClientInterceptor):
    def __init__(self, token: str) -> None:
        self._token = token

    async def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        return await continuation(_with_token(client_call_details, self._token), request_iterator)


def bearer_interceptors(token: str | None) -> list[grpc.aio.ClientInterceptor]:
    """Interceptors that send ``token`` on every kind of call; none without a token."""
    if not token:
        return []
    return [_BearerUnaryUnary(token), _BearerUnaryStream(token), _BearerStreamUnary(token), _BearerStreamStream(token)]


__all__ = ["ENV_VAR", "ZequentAuthError", "bearer_interceptors", "explain", "resolve_token"]

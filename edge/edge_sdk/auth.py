"""
Platform <-> adapter authentication
====================================

Both directions of an adapter's gRPC traffic carry a bearer token (2026-09-30 security review,
GRPC-1 / SAST-3):

* **Adapter -> platform.** Core refuses calls without a credential. An adapter is configured with
  an *edge credential* (``ZQNT_EDGE_TOKEN``) issued in the console (``POST
  /api/admin-console/edge-credentials``) or by ``core/scripts/mint-edge-credential.py``. Every
  channel the SDK opens to connector / live-data / mission-autonomy attaches it
  (:func:`platform_channel`). It reaches only the device-facing RPCs, for the organization it was
  issued to.

* **Platform -> adapter.** The platform signs a short-lived *service token* (audience
  ``zqnt-edge``) for every command it sends. :class:`EdgeServer` verifies it with the platform's
  service public key (``ZQNT_PLATFORM_PUBLIC_KEY``, alias ``SERVICE_AUTH_PUBLIC_KEY``) and refuses
  everything else, so only the platform can command the device.

``ZQNT_EDGE_AUTH_DISABLED=true`` turns the inbound check off — for a local SITL/simulator stack
only. Without a public key and without that switch the server refuses every call (fail closed).

Token contract (must match ``core/components/tenancy/.../ServiceTokens.java``): compact JWS,
``alg=EdDSA`` (Ed25519), ``iss=zqnt-service``, ``aud=zqnt-edge``, ``scope`` contains
``platform``, ``exp`` in the future.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import os
import time
from typing import Any

import grpc

logger = logging.getLogger(__name__)

ISSUER = "zqnt-service"
AUDIENCE_EDGE = "zqnt-edge"
SCOPE_PLATFORM = "platform"
CLOCK_SKEW_SECONDS = 30

#: Methods the server answers without a token: health probes carry none.
UNAUTHENTICATED_METHODS = frozenset({"/grpc.health.v1.Health/Check", "/grpc.health.v1.Health/Watch"})

_TRUE = {"1", "true", "yes", "on"}


class TokenVerificationError(Exception):
    """The token is missing, malformed, not signed by the platform, or not meant for an adapter."""


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _load_public_key(value: str):
    from cryptography.hazmat.primitives.serialization import load_der_public_key, load_pem_public_key

    value = value.strip()
    if value.startswith("-----BEGIN"):
        return load_pem_public_key(value.encode())
    return load_der_public_key(base64.b64decode(value))


class PlatformTokenVerifier:
    """Verifies the service token the platform puts on every call into this adapter."""

    def __init__(self, public_key: str) -> None:
        try:
            self._key = _load_public_key(public_key)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a configuration error
            raise ValueError(f"ZQNT_PLATFORM_PUBLIC_KEY is not a valid Ed25519 public key: {exc}") from exc

    def verify(self, token: str) -> dict[str, Any]:
        from cryptography.exceptions import InvalidSignature

        parts = token.split(".")
        if len(parts) != 3:
            raise TokenVerificationError("token must be a compact JWS")
        try:
            header = json.loads(_b64url_decode(parts[0]))
            payload = json.loads(_b64url_decode(parts[1]))
            signature = _b64url_decode(parts[2])
        except Exception as exc:  # noqa: BLE001
            raise TokenVerificationError("token is not well-formed") from exc
        if header.get("alg") != "EdDSA":
            raise TokenVerificationError("only EdDSA tokens are accepted")
        try:
            self._key.verify(signature, f"{parts[0]}.{parts[1]}".encode("ascii"))
        except InvalidSignature as exc:
            raise TokenVerificationError("token signature is invalid") from exc
        if payload.get("iss") != ISSUER:
            raise TokenVerificationError("unexpected token issuer")
        if payload.get("aud") != AUDIENCE_EDGE:
            raise TokenVerificationError("token is not meant for an edge adapter")
        scopes = payload.get("scope")
        if not isinstance(scopes, list) or SCOPE_PLATFORM not in scopes:
            raise TokenVerificationError("token is not a platform service token")
        exp = payload.get("exp")
        now = time.time()
        if not isinstance(exp, (int, float)) or exp + CLOCK_SKEW_SECONDS < now:
            raise TokenVerificationError("token is expired")
        iat = payload.get("iat")
        if isinstance(iat, (int, float)) and iat - CLOCK_SKEW_SECONDS > now:
            raise TokenVerificationError("token is issued in the future")
        return payload


@dataclasses.dataclass
class EdgeAuthConfig:
    """
    Authentication settings for an adapter.

    Attributes:
        edge_token:          Credential for calls INTO the platform (``ZQNT_EDGE_TOKEN``).
        platform_public_key: Key the platform's commands are verified with
                             (``ZQNT_PLATFORM_PUBLIC_KEY`` / ``SERVICE_AUTH_PUBLIC_KEY``).
        disabled:            Skip the inbound check (``ZQNT_EDGE_AUTH_DISABLED``) — local SITL only.
    """

    edge_token: str | None = None
    platform_public_key: str | None = None
    disabled: bool = False

    @classmethod
    def from_env(cls) -> "EdgeAuthConfig":
        return cls(
            edge_token=os.getenv("ZQNT_EDGE_TOKEN") or None,
            platform_public_key=os.getenv("ZQNT_PLATFORM_PUBLIC_KEY") or os.getenv("SERVICE_AUTH_PUBLIC_KEY") or None,
            disabled=os.getenv("ZQNT_EDGE_AUTH_DISABLED", "").strip().lower() in _TRUE,
        )


def default_edge_token() -> str | None:
    """The adapter's platform credential from the environment, if any."""
    return os.getenv("ZQNT_EDGE_TOKEN") or None


# ---------------------------------------------------------------------------
# Outbound: attach the edge credential
# ---------------------------------------------------------------------------


class _Bearer:
    """Appends the edge credential to a call's metadata, keeping whatever the call already carries."""

    def __init__(self, token: str) -> None:
        self._header = ("authorization", f"Bearer {token}")

    def _details(self, details):
        metadata = list(details.metadata or [])
        metadata.append(self._header)
        return details._replace(metadata=metadata)


# One class per call type, each inheriting exactly ONE grpc.aio base. grpc.aio files every channel
# interceptor under a single call type with an if/elif chain on its base class (unary-unary is
# checked first), so one class inheriting all four bases was applied to unary-unary calls only:
# every streaming call -- ProduceTelemetry/ProduceDetection/ProduceNotification included -- went
# out without the credential and live-data refused it (dev, 2026-10-01).


class _BearerUnaryUnary(_Bearer, grpc.aio.UnaryUnaryClientInterceptor):
    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(self._details(client_call_details), request)


class _BearerUnaryStream(_Bearer, grpc.aio.UnaryStreamClientInterceptor):
    async def intercept_unary_stream(self, continuation, client_call_details, request):
        return await continuation(self._details(client_call_details), request)


class _BearerStreamUnary(_Bearer, grpc.aio.StreamUnaryClientInterceptor):
    async def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return await continuation(self._details(client_call_details), request_iterator)


class _BearerStreamStream(_Bearer, grpc.aio.StreamStreamClientInterceptor):
    async def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        return await continuation(self._details(client_call_details), request_iterator)


def bearer_interceptors(token: str) -> list:
    """Interceptors that put ``token`` on every call type of a grpc.aio channel."""
    return [
        _BearerUnaryUnary(token),
        _BearerUnaryStream(token),
        _BearerStreamUnary(token),
        _BearerStreamStream(token),
    ]


def platform_channel(host: str, port: int, token: str | None) -> grpc.aio.Channel:
    """
    A channel to a core service that carries ``token`` on every call. Without a token the calls go
    out bare, and the platform refuses all but claim redemption — logged once per channel.
    """
    target = f"{host}:{port}"
    if not token:
        logger.warning(
            "No ZQNT_EDGE_TOKEN: calls to %s carry no credential and the platform will refuse them "
            "(issue one in the console under Edge Credentials)",
            target,
        )
        return grpc.aio.insecure_channel(target)
    return grpc.aio.insecure_channel(target, interceptors=bearer_interceptors(token))


# ---------------------------------------------------------------------------
# Inbound: verify the platform's token
# ---------------------------------------------------------------------------


class PlatformAuthServerInterceptor(grpc.aio.ServerInterceptor):
    """Refuses every call into the adapter that does not carry a valid platform service token."""

    def __init__(self, config: EdgeAuthConfig) -> None:
        self._disabled = config.disabled
        self._verifier: PlatformTokenVerifier | None = None
        self._misconfigured: str | None = None
        if self._disabled:
            logger.warning(
                "ZQNT_EDGE_AUTH_DISABLED is set: this adapter accepts commands from ANYONE who can reach "
                "its port. Local SITL/simulator use only."
            )
        elif not config.platform_public_key:
            self._misconfigured = "ZQNT_PLATFORM_PUBLIC_KEY is not configured"
            logger.error(
                "ZQNT_PLATFORM_PUBLIC_KEY is not set: every platform command will be refused. Set it to the "
                "platform's SERVICE_AUTH_PUBLIC_KEY (or ZQNT_EDGE_AUTH_DISABLED=true for local SITL)."
            )
        else:
            self._verifier = PlatformTokenVerifier(config.platform_public_key)

    def check(self, method: str, metadata) -> tuple[grpc.StatusCode, str] | None:
        """``None`` when the call may proceed, else the status to refuse it with."""
        if self._disabled or method in UNAUTHENTICATED_METHODS:
            return None
        if self._verifier is None:
            return grpc.StatusCode.UNAUTHENTICATED, self._misconfigured or "authentication is not configured"
        header = None
        for key, value in metadata or ():
            if key.lower() == "authorization":
                header = value
                break
        if not header or not header.startswith("Bearer "):
            return grpc.StatusCode.UNAUTHENTICATED, "authentication required"
        try:
            self._verifier.verify(header[len("Bearer ") :])
        except TokenVerificationError as exc:
            logger.warning("Refused %s: %s", method, exc)
            return grpc.StatusCode.UNAUTHENTICATED, str(exc)
        return None

    async def intercept_service(self, continuation, handler_call_details):
        refusal = self.check(handler_call_details.method, handler_call_details.invocation_metadata)
        handler = await continuation(handler_call_details)
        if refusal is None or handler is None:
            return handler
        code, details = refusal

        async def abort(_request, context):
            await context.abort(code, details)

        kwargs = {
            "request_deserializer": handler.request_deserializer,
            "response_serializer": handler.response_serializer,
        }
        if handler.request_streaming and handler.response_streaming:
            return grpc.stream_stream_rpc_method_handler(abort, **kwargs)
        if handler.request_streaming:
            return grpc.stream_unary_rpc_method_handler(abort, **kwargs)
        if handler.response_streaming:
            return grpc.unary_stream_rpc_method_handler(abort, **kwargs)
        return grpc.unary_unary_rpc_method_handler(abort, **kwargs)

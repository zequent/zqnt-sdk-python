"""
Internal TLS: reaching the platform over the installation's own CA
==================================================================

An installation with internal TLS (``ZQNT_INTERNAL_TLS=true`` on the core services) serves every
core gRPC API over TLS on a second port with a certificate from one CA per installation. An adapter
running inside such an installation sets the same two variables and every channel it opens to the
core (:func:`edge_sdk.auth.platform_channel`) is then TLS, the server certificate verified against
that CA and the dialled host name. Nothing else changes: the edge credential keeps authenticating
the adapter, and no client certificate is presented.

    ZQNT_INTERNAL_TLS      true/1/yes/on switches it on (default: off, plaintext as before)
    ZQNT_INTERNAL_TLS_CA   the CA certificate, PEM (default: /etc/zqnt/internal-tls/ca.crt)

The same CA verifies the platform's key set when ``ZQNT_PLATFORM_KEYS_URL`` is ``https://`` and
Redis when ``REDIS_URL`` is ``rediss://``. With the switch on and the CA file unreadable the
adapter fails at the first channel instead of silently talking plaintext.
"""

from __future__ import annotations

import dataclasses
import os
import ssl
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import grpc
import grpc.aio

ENABLED_ENV = "ZQNT_INTERNAL_TLS"
CA_ENV = "ZQNT_INTERNAL_TLS_CA"
DEFAULT_CA_FILE = "/etc/zqnt/internal-tls/ca.crt"

_TRUE = {"1", "true", "yes", "on"}


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE


@dataclasses.dataclass(frozen=True)
class InternalTls:
    """
    Whether channels into the platform use TLS, and the CA that vouches for the platform.

    Attributes:
        enabled:  TLS to the core services (``ZQNT_INTERNAL_TLS``).
        ca_file:  The installation's CA certificate, PEM (``ZQNT_INTERNAL_TLS_CA``).
    """

    enabled: bool = False
    ca_file: str = DEFAULT_CA_FILE

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "InternalTls":
        source = os.environ if env is None else env
        return cls(
            enabled=_is_true(source.get(ENABLED_ENV)),
            ca_file=(source.get(CA_ENV) or "").strip() or DEFAULT_CA_FILE,
        )

    @classmethod
    def off(cls) -> "InternalTls":
        return cls(enabled=False)

    def ca_bytes(self) -> bytes:
        """The CA certificate; a clear error when the file is not there."""
        try:
            with open(self.ca_file, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise FileNotFoundError(
                f"{ENABLED_ENV} is on but the CA certificate {self.ca_file} ({CA_ENV}) cannot be read: {exc}"
            ) from exc
        if b"-----BEGIN CERTIFICATE-----" not in data:
            raise ValueError(f"{self.ca_file} ({CA_ENV}) is not a PEM certificate")
        return data

    def channel_credentials(self) -> grpc.ChannelCredentials:
        """Channel credentials trusting the installation's CA (server verification only)."""
        return grpc.ssl_channel_credentials(root_certificates=self.ca_bytes())

    def aio_channel(
        self,
        target: str,
        options: Sequence[tuple[str, Any]] | None = None,
        interceptors: Sequence[grpc.aio.ClientInterceptor] | None = None,
    ) -> grpc.aio.Channel:
        """A channel to ``target``: TLS with the CA when enabled, plaintext otherwise."""
        if not self.enabled:
            return grpc.aio.insecure_channel(target, options=options, interceptors=interceptors)
        return grpc.aio.secure_channel(target, self.channel_credentials(), options=options, interceptors=interceptors)

    def ssl_context(self) -> ssl.SSLContext | None:
        """An SSL context trusting the system roots and the installation's CA; None when off."""
        if not self.enabled:
            return None
        context = ssl.create_default_context()
        try:
            context.load_verify_locations(cafile=self.ca_file)
        except (OSError, ssl.SSLError) as exc:
            raise FileNotFoundError(
                f"{ENABLED_ENV} is on but the CA certificate {self.ca_file} ({CA_ENV}) cannot be loaded: {exc}"
            ) from exc
        return context

    def redis_kwargs(self, url: str) -> dict[str, Any]:
        """Extra ``redis.asyncio.from_url`` arguments: the CA as trust root for a ``rediss://`` URL."""
        if self.enabled and urlsplit(url).scheme == "rediss":
            return {"ssl_ca_certs": self.ca_file}
        return {}

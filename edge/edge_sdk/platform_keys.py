"""
The platform's published signing keys
=====================================

Core signs its service tokens with rotating keys and publishes the public half of every key version
that is not retired as a JWK set (``GET /api/admin-console/auth/service-keys``). A token's ``kid``
header (``<name>:v<n>``, e.g. ``service-token:v2``) names its key; the key listed without ``kid`` is
the one tokens without ``kid`` are signed with.

:class:`PlatformKeySet` keeps that set in memory: it fetches it at start (retrying until the first
success), refreshes it periodically, and on demand when a token names a key it does not know yet,
at most once per ``min_refresh_spacing``. A failed refresh keeps the keys it has.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

logger = logging.getLogger(__name__)


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def parse_jwks(document: Any) -> dict[str | None, Ed25519PublicKey]:
    """The Ed25519 signing keys of a JWK set by ``kid`` (``None`` for the key without one)."""
    if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
        raise ValueError("not a JWK set")
    keys: dict[str | None, Ed25519PublicKey] = {}
    for entry in document["keys"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("kty") != "OKP" or entry.get("crv") != "Ed25519":
            continue
        if entry.get("alg") not in (None, "EdDSA") or entry.get("use") not in (None, "sig"):
            continue
        kid = entry.get("kid")
        if kid is not None and not isinstance(kid, str):
            continue
        try:
            raw = _b64url_decode(entry["x"])
            if len(raw) != 32:
                continue
            keys[kid] = Ed25519PublicKey.from_public_bytes(raw)
        except (KeyError, TypeError, ValueError, binascii.Error):
            continue
    return keys


def _http_get_json(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-configured URL
        return json.loads(response.read())


class PlatformKeySet:
    """The platform's public signing keys, fetched from its JWK set URL and kept fresh."""

    def __init__(
        self,
        url: str,
        *,
        refresh_interval: float = 300.0,
        min_refresh_spacing: float = 30.0,
        timeout: float = 5.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        fetch: Callable[[str, float], Any] = _http_get_json,
    ) -> None:
        self._url = url
        self._refresh_interval = refresh_interval
        self._min_refresh_spacing = min_refresh_spacing
        self._timeout = timeout
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._clock = clock
        self._fetch = fetch
        self._keys: dict[str | None, Ed25519PublicKey] = {}
        self._lock = threading.Lock()
        self._last_attempt: float | None = None
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return self._url

    def key(self, kid: str | None) -> Ed25519PublicKey | None:
        return self._keys.get(kid)

    def kids(self) -> list[str | None]:
        return list(self._keys)

    def refresh(self) -> bool:
        """Fetch the set now. ``False`` (keeping the cached keys) when it cannot be read."""
        with self._lock:
            return self._refresh_locked()

    def refresh_if_due(self) -> bool:
        """Fetch the set unless the last attempt was less than ``min_refresh_spacing`` ago."""
        with self._lock:
            if self._last_attempt is not None and self._clock() - self._last_attempt < self._min_refresh_spacing:
                return False
            return self._refresh_locked()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="zqnt-platform-keys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self._timeout + 1)

    def _refresh_locked(self) -> bool:
        self._last_attempt = self._clock()
        try:
            keys = parse_jwks(self._fetch(self._url, self._timeout))
        except Exception as exc:  # noqa: BLE001 - any failure keeps the cached keys
            logger.warning("Could not read the platform's signing keys from %s: %s", self._url, exc)
            return False
        if set(keys) != set(self._keys):
            logger.info("Platform signing keys: %s", sorted(k or "(no kid)" for k in keys))
        self._keys = keys
        return True

    def _run(self) -> None:
        backoff = self._initial_backoff
        while not self._stopped.is_set() and not self.refresh():
            if self._stopped.wait(backoff):
                return
            backoff = min(backoff * 2, self._max_backoff)
        while not self._stopped.wait(self._refresh_interval):
            self.refresh()

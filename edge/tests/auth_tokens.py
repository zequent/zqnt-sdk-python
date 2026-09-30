"""Helpers that mint tokens the way core does (ServiceTokenCodec.java), for the auth tests."""

import base64
import json
import time
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_b64(key: Ed25519PrivateKey) -> str:
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def token(
    key: Ed25519PrivateKey,
    *,
    aud: str = "zqnt-edge",
    scope: list[str] | None = None,
    iss: str = "zqnt-service",
    ttl: int = 300,
    alg: str = "EdDSA",
) -> str:
    now = int(time.time())
    header = {"alg": alg, "typ": "JWT"}
    payload = {
        "iss": iss,
        "sub": "svc:remote-control-service",
        "aud": aud,
        "scope": scope if scope is not None else ["platform"],
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    signing_input = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(payload).encode())
    return signing_input + "." + _b64url(key.sign(signing_input.encode("ascii")))

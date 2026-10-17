"""Helpers that mint tokens and serve a JWK set the way core does (ServiceTokenCodec.java), for the auth tests."""

import base64
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def public_key_b64(key: Ed25519PrivateKey) -> str:
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def jwk(key: Ed25519PrivateKey, kid: str | None = None) -> dict:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    entry = {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "use": "sig", "x": _b64url(raw)}
    if kid is not None:
        entry["kid"] = kid
    return entry


def token(
    key: Ed25519PrivateKey,
    *,
    aud: str = "zqnt-edge",
    scope: list[str] | None = None,
    iss: str = "zqnt-service",
    ttl: int = 300,
    alg: str = "EdDSA",
    kid: str | None = None,
) -> str:
    now = int(time.time())
    header = {"alg": alg, "typ": "JWT"}
    if kid is not None:
        header["kid"] = kid
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


class FakeJwksServer:
    def __init__(self) -> None:
        self.keys: list[dict] = []
        self.status = 200
        self.requests = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                server.requests += 1
                body = json.dumps({"keys": server.keys}).encode()
                self.send_response(server.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}/api/admin-console/auth/service-keys"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

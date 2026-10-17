"""The platform's published key set (edge_sdk.platform_keys) against a fake JWK set server."""

import time

import grpc
import pytest

from edge_sdk.auth import (
    EdgeAuthConfig,
    PlatformAuthServerInterceptor,
    PlatformTokenVerifier,
    TokenVerificationError,
    UnknownSigningKeyError,
)
from edge_sdk.platform_keys import PlatformKeySet, parse_jwks
from tests.auth_tokens import FakeJwksServer, jwk, new_key, public_key_b64, token

V1 = new_key()
V2 = new_key()
ENV_KEY = new_key()
STRANGER = new_key()
METHOD = "/zqnt.EdgeAdapterService/TakeOff"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def jwks():
    server = FakeJwksServer()
    yield server
    server.close()


@pytest.fixture
def clock():
    return FakeClock()


def _key_set(jwks, clock) -> PlatformKeySet:
    return PlatformKeySet(jwks.url, clock=clock)


class TestRotation:
    def test_a_new_key_version_is_fetched_and_the_old_one_stays_valid(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        assert keys.refresh()
        verifier = PlatformTokenVerifier(key_set=keys)
        assert verifier.verify(token(V1, kid="service-token:v1"))["sub"]

        jwks.keys = [jwk(V1, "service-token:v1"), jwk(V2, "service-token:v2")]
        clock.now += 30
        assert verifier.verify(token(V2, kid="service-token:v2"))["sub"]
        assert verifier.verify(token(V1, kid="service-token:v1"))["sub"]
        assert jwks.requests == 2

    async def test_the_interceptor_follows_a_rotation(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        interceptor = PlatformAuthServerInterceptor(EdgeAuthConfig(), key_set=keys)
        jwks.keys = [jwk(V1, "service-token:v1"), jwk(V2, "service-token:v2")]
        clock.now += 31
        bearer = (("authorization", f"Bearer {token(V2, kid='service-token:v2')}"),)
        assert await interceptor.check(METHOD, bearer) is None

    def test_a_key_signed_by_someone_else_under_a_known_kid_is_refused(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        with pytest.raises(TokenVerificationError, match="signature"):
            PlatformTokenVerifier(key_set=keys).verify(token(STRANGER, kid="service-token:v1"))


class TestUnknownKey:
    def test_an_unknown_kid_is_refused_after_a_refresh(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        clock.now += 60
        with pytest.raises(UnknownSigningKeyError, match="service-token:v9"):
            PlatformTokenVerifier(key_set=keys).verify(token(STRANGER, kid="service-token:v9"))
        assert jwks.requests == 2

    def test_a_kid_without_a_key_set_is_refused(self):
        verifier = PlatformTokenVerifier(public_key_b64(V1))
        with pytest.raises(TokenVerificationError, match="ZQNT_PLATFORM_KEYS_URL"):
            verifier.verify(token(V1, kid="service-token:v1"))

    def test_refreshes_on_unknown_kids_are_spaced_30_seconds_apart(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        verifier = PlatformTokenVerifier(key_set=keys)
        clock.now += 30
        for _ in range(2):
            with pytest.raises(UnknownSigningKeyError):
                verifier.verify(token(STRANGER, kid="service-token:v9"))
        assert jwks.requests == 2

        clock.now += 29
        with pytest.raises(UnknownSigningKeyError):
            verifier.verify(token(STRANGER, kid="service-token:v9"))
        assert jwks.requests == 2

        clock.now += 1
        with pytest.raises(UnknownSigningKeyError):
            verifier.verify(token(STRANGER, kid="service-token:v9"))
        assert jwks.requests == 3


class TestWithoutKid:
    def test_the_static_key_verifies_tokens_without_kid(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        verifier = PlatformTokenVerifier(public_key_b64(ENV_KEY), keys)
        assert verifier.verify(token(ENV_KEY))["sub"]
        assert verifier.verify(token(V1, kid="service-token:v1"))["sub"]

    def test_the_key_listed_without_kid_verifies_tokens_without_kid(self, jwks, clock):
        jwks.keys = [jwk(ENV_KEY), jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        assert PlatformTokenVerifier(key_set=keys).verify(token(ENV_KEY))["sub"]

    def test_without_static_key_and_kid_less_jwk_a_token_without_kid_is_refused(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        with pytest.raises(TokenVerificationError, match="no key without kid"):
            PlatformTokenVerifier(key_set=keys).verify(token(V1))


class TestFetching:
    def test_a_failed_refresh_keeps_the_cached_keys(self, jwks, clock):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = _key_set(jwks, clock)
        keys.refresh()
        jwks.status = 503
        assert not keys.refresh()
        assert keys.key("service-token:v1") is not None

    def test_the_first_fetch_is_retried_until_the_platform_answers(self, jwks):
        jwks.status = 503
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = PlatformKeySet(jwks.url, initial_backoff=0.01, max_backoff=0.02, refresh_interval=60)
        keys.start()
        try:
            deadline = time.monotonic() + 5
            while jwks.requests < 3 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert keys.key("service-token:v1") is None
            jwks.status = 200
            while keys.key("service-token:v1") is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert keys.key("service-token:v1") is not None
        finally:
            keys.stop()

    def test_the_set_is_refreshed_periodically(self, jwks):
        jwks.keys = [jwk(V1, "service-token:v1")]
        keys = PlatformKeySet(jwks.url, refresh_interval=0.02)
        keys.start()
        try:
            deadline = time.monotonic() + 5
            while jwks.requests < 3 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert jwks.requests >= 3
        finally:
            keys.stop()

    def test_unusable_entries_are_skipped(self):
        keys = parse_jwks(
            {
                "keys": [
                    jwk(V1, "service-token:v1"),
                    {**jwk(V2, "rsa:v1"), "kty": "RSA"},
                    {**jwk(V2, "enc:v1"), "use": "enc"},
                    {**jwk(V2, "es:v1"), "alg": "ES256"},
                    {**jwk(V2, "short:v1"), "x": "AAAA"},
                    {"kty": "OKP", "crv": "Ed25519", "kid": "nox:v1"},
                    "garbage",
                ]
            }
        )
        assert list(keys) == ["service-token:v1"]

    def test_a_document_that_is_no_key_set_is_an_error(self):
        with pytest.raises(ValueError):
            parse_jwks({"keys": "nope"})


class TestConfig:
    def test_the_url_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ZQNT_PLATFORM_KEYS_URL", "http://admin-console:8005/api/admin-console/auth/service-keys")
        assert EdgeAuthConfig.from_env().platform_keys_url.endswith("/service-keys")

    async def test_a_url_alone_is_enough(self, jwks):
        jwks.keys = [jwk(V1, "service-token:v1")]
        interceptor = PlatformAuthServerInterceptor(EdgeAuthConfig(platform_keys_url=jwks.url))
        bearer = (("authorization", f"Bearer {token(V1, kid='service-token:v1')}"),)
        assert await interceptor.check(METHOD, bearer) is None
        interceptor.close()

    async def test_neither_url_nor_key_refuses_everything(self):
        code, details = await PlatformAuthServerInterceptor(EdgeAuthConfig()).check(
            METHOD, (("authorization", f"Bearer {token(V1)}"),)
        )
        assert code == grpc.StatusCode.UNAUTHENTICATED
        assert "ZQNT_PLATFORM_KEYS_URL" in details and "ZQNT_PLATFORM_PUBLIC_KEY" in details

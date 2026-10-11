"""Platform <-> adapter authentication (edge_sdk.auth) — 2026-09-30 security review SAST-3."""

import grpc
import pytest

from edge_sdk.auth import (
    EdgeAuthConfig,
    PlatformAuthServerInterceptor,
    PlatformTokenVerifier,
    TokenVerificationError,
    _BearerUnaryUnary,
)
from tests.auth_tokens import new_key, public_key_b64, token

KEY = new_key()
OTHER_KEY = new_key()
METHOD = "/zqnt.EdgeAdapterService/TakeOff"


def _interceptor(**kwargs) -> PlatformAuthServerInterceptor:
    return PlatformAuthServerInterceptor(EdgeAuthConfig(**kwargs))


def _bearer(value: str):
    return (("authorization", f"Bearer {value}"),)


class TestVerifier:
    def test_a_platform_token_verifies(self):
        claims = PlatformTokenVerifier(public_key_b64(KEY)).verify(token(KEY))
        assert claims["sub"] == "svc:remote-control-service"

    @pytest.mark.parametrize(
        "bad",
        [
            token(OTHER_KEY),  # not signed by the platform
            token(KEY, aud="zqnt-platform"),  # a token meant for core
            token(KEY, scope=["edge"]),  # another adapter's credential
            token(KEY, iss="zqnt-admin-console"),  # a user token
            token(KEY, ttl=-120),  # expired
            "not.a.token",
            "abc",
        ],
    )
    def test_anything_else_is_refused(self, bad):
        with pytest.raises(TokenVerificationError):
            PlatformTokenVerifier(public_key_b64(KEY)).verify(bad)

    def test_alg_none_is_refused(self):
        forged = token(KEY, alg="none").rsplit(".", 1)[0] + "."
        with pytest.raises(TokenVerificationError):
            PlatformTokenVerifier(public_key_b64(KEY)).verify(forged)

    def test_a_bad_key_is_a_configuration_error(self):
        with pytest.raises(ValueError):
            PlatformTokenVerifier("not-a-key")


class TestServerInterceptor:
    def test_no_token_is_refused(self):
        code, _ = _interceptor(platform_public_key=public_key_b64(KEY)).check(METHOD, ())
        assert code == grpc.StatusCode.UNAUTHENTICATED

    def test_a_valid_token_passes(self):
        assert _interceptor(platform_public_key=public_key_b64(KEY)).check(METHOD, _bearer(token(KEY))) is None

    def test_a_forged_token_is_refused(self):
        code, _ = _interceptor(platform_public_key=public_key_b64(KEY)).check(METHOD, _bearer(token(OTHER_KEY)))
        assert code == grpc.StatusCode.UNAUTHENTICATED

    def test_without_a_public_key_everything_is_refused(self):
        code, details = _interceptor().check(METHOD, _bearer(token(KEY)))
        assert code == grpc.StatusCode.UNAUTHENTICATED
        assert "ZQNT_PLATFORM_PUBLIC_KEY" in details

    def test_health_probes_need_no_token(self):
        assert _interceptor().check("/grpc.health.v1.Health/Check", ()) is None

    def test_the_dev_switch_lets_everything_through(self):
        assert _interceptor(disabled=True).check(METHOD, ()) is None


class TestConfig:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("ZQNT_EDGE_TOKEN", "edge-token")
        monkeypatch.setenv("SERVICE_AUTH_PUBLIC_KEY", "alias-key")
        monkeypatch.delenv("ZQNT_PLATFORM_PUBLIC_KEY", raising=False)
        monkeypatch.setenv("ZQNT_EDGE_AUTH_DISABLED", "true")
        config = EdgeAuthConfig.from_env()
        assert config.edge_token == "edge-token"
        assert config.platform_public_key == "alias-key"
        assert config.disabled is True

    def test_disabled_needs_an_explicit_true(self, monkeypatch):
        monkeypatch.setenv("ZQNT_EDGE_AUTH_DISABLED", "maybe")
        assert EdgeAuthConfig.from_env().disabled is False


class TestClientInterceptor:
    async def test_the_edge_token_is_attached(self):
        seen = {}

        async def continuation(details, request):
            seen["metadata"] = details.metadata
            return "ok"

        details = grpc.aio.ClientCallDetails("/zqnt.LiveDataService/ProduceTelemetry", None, None, None, None)
        result = await _BearerUnaryUnary("edge-token").intercept_unary_unary(continuation, details, object())
        assert result == "ok"
        assert ("authorization", "Bearer edge-token") in seen["metadata"]

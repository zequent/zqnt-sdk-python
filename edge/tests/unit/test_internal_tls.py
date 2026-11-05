"""ZQNT_INTERNAL_TLS / ZQNT_INTERNAL_TLS_CA: how an adapter is told to reach the platform over TLS."""

import ssl

import grpc
import pytest

from edge_sdk.internal_tls import DEFAULT_CA_FILE, InternalTls
from tests.certs import write_self_signed


class TestFromEnv:
    def test_nothing_set_is_plaintext(self):
        tls = InternalTls.from_env({})
        assert tls == InternalTls(enabled=False, ca_file=DEFAULT_CA_FILE)
        assert not tls.enabled

    @pytest.mark.parametrize("value", ["true", "TRUE", " 1 ", "yes", "On"])
    def test_the_switch(self, value):
        assert InternalTls.from_env({"ZQNT_INTERNAL_TLS": value}).enabled

    @pytest.mark.parametrize("value", ["", "false", "0", "maybe"])
    def test_anything_else_stays_off(self, value):
        assert not InternalTls.from_env({"ZQNT_INTERNAL_TLS": value}).enabled

    def test_the_ca_path(self):
        tls = InternalTls.from_env({"ZQNT_INTERNAL_TLS": "true", "ZQNT_INTERNAL_TLS_CA": " /pki/ca.pem "})
        assert tls.ca_file == "/pki/ca.pem"

    def test_an_empty_ca_path_is_the_default(self):
        assert InternalTls.from_env({"ZQNT_INTERNAL_TLS_CA": ""}).ca_file == DEFAULT_CA_FILE

    def test_the_process_environment(self, monkeypatch):
        monkeypatch.setenv("ZQNT_INTERNAL_TLS", "true")
        monkeypatch.setenv("ZQNT_INTERNAL_TLS_CA", "/pki/ca.pem")
        assert InternalTls.from_env() == InternalTls(enabled=True, ca_file="/pki/ca.pem")


class TestCredentials:
    def test_a_missing_ca_file_fails_with_the_variable_named(self, tmp_path):
        tls = InternalTls(enabled=True, ca_file=str(tmp_path / "nope.crt"))
        with pytest.raises(FileNotFoundError, match="ZQNT_INTERNAL_TLS_CA"):
            tls.channel_credentials()
        with pytest.raises(FileNotFoundError, match="ZQNT_INTERNAL_TLS_CA"):
            tls.aio_channel("localhost:1")

    def test_a_file_that_is_no_certificate_fails(self, tmp_path):
        bogus = tmp_path / "ca.crt"
        bogus.write_text("not a certificate")
        with pytest.raises(ValueError, match="ZQNT_INTERNAL_TLS_CA"):
            InternalTls(enabled=True, ca_file=str(bogus)).channel_credentials()

    def test_credentials_from_a_generated_ca(self, tmp_path):
        cert, _ = write_self_signed(tmp_path)
        assert isinstance(InternalTls(enabled=True, ca_file=str(cert)).channel_credentials(), grpc.ChannelCredentials)

    async def test_off_is_a_plaintext_channel_without_touching_the_file(self, tmp_path):
        channel = InternalTls(enabled=False, ca_file=str(tmp_path / "nope.crt")).aio_channel("localhost:1")
        assert isinstance(channel, grpc.aio.Channel)
        await channel.close()


class TestSslContext:
    def test_off_is_none(self):
        assert InternalTls.off().ssl_context() is None

    def test_on_trusts_the_ca_next_to_the_system_roots(self, tmp_path):
        cert, _ = write_self_signed(tmp_path)
        context = InternalTls(enabled=True, ca_file=str(cert)).ssl_context()
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        subjects = [dict(x[0] for x in c["subject"]) for c in context.get_ca_certs()]
        assert {"commonName": "localhost"} in subjects

    def test_on_with_a_missing_file_fails(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="ZQNT_INTERNAL_TLS_CA"):
            InternalTls(enabled=True, ca_file=str(tmp_path / "nope.crt")).ssl_context()


class TestRedis:
    def test_rediss_gets_the_ca(self):
        tls = InternalTls(enabled=True, ca_file="/pki/ca.pem")
        assert tls.redis_kwargs("rediss://:secret@redis:6380") == {"ssl_ca_certs": "/pki/ca.pem"}

    def test_redis_stays_as_it_is(self):
        assert InternalTls(enabled=True, ca_file="/pki/ca.pem").redis_kwargs("redis://redis:6379") == {}

    def test_off_adds_nothing_even_for_rediss(self):
        assert InternalTls.off().redis_kwargs("rediss://redis:6380") == {}

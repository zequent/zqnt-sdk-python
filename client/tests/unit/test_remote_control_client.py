"""Unit tests for ``RemoteControlClient``.

The gRPC stub is monkey-patched with a fake whose RPC methods return a
prebuilt proto, so the tests exercise the full request-build / response-
parse path without a live server.
"""

from __future__ import annotations

from typing import Any

import pytest

from client_sdk.config.resilience import ResilienceConfig
from client_sdk.generated import (
    common_pb2,
    remote_control_pb2,
)
from client_sdk.models import (
    DockOperationRequest,
    GoToRequest,
    LookAtRequest,
    ManualControlRequest,
    ReturnToHomeRequest,
    TakeoffRequest,
)


def _ok_response(message: str = "ok") -> remote_control_pb2.RemoteControlResponse:
    from google.protobuf import empty_pb2

    return remote_control_pb2.RemoteControlResponse(
        hasErrors=False,
        tid="tid-123",
        sn="DOCK-001",
        responseMessage=message,
        empty=empty_pb2.Empty(),
    )


def _error_response() -> remote_control_pb2.RemoteControlResponse:
    return remote_control_pb2.RemoteControlResponse(
        hasErrors=True,
        tid="tid-err",
        sn="DOCK-001",
        error=common_pb2.GlobalErrorMessage(
            errorMessage="boom",
            errorCode=common_pb2.ASSET_ERROR,
        ),
    )


class _FakeStub:
    """Records the last request per RPC and returns a configured response."""

    def __init__(self, response: remote_control_pb2.RemoteControlResponse) -> None:
        self._response = response
        self.calls: dict[str, Any] = {}

    def _make(self, name: str):
        async def _rpc(request, timeout=None):  # noqa: ANN001 - stub signature
            self.calls[name] = (request, timeout)
            return self._response

        return _rpc

    def __getattr__(self, name: str):
        return self._make(name)


@pytest.fixture
def client_with_fake_stub():
    def _factory(response=None):
        from client_sdk.remote_control import client as client_mod

        stub = _FakeStub(response or _ok_response())
        # Bypass __init__ so we don't need a real grpc channel.
        rc = client_mod.RemoteControlClient.__new__(client_mod.RemoteControlClient)
        rc._channel = None
        rc._resilience = ResilienceConfig()
        from client_sdk.grpc_.resilience import GrpcResilience

        rc._resilience_helper = GrpcResilience(rc._resilience)
        rc._stub = stub
        return rc, stub

    return _factory


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_takeoff_rejects_blank_sn(client_with_fake_stub) -> None:
    rc, _ = client_with_fake_stub()
    with pytest.raises(ValueError, match="SN must not"):
        await rc.takeoff(TakeoffRequest(sn="", latitude=0, longitude=0, altitude=10))


@pytest.mark.asyncio
async def test_takeoff_rejects_invalid_latitude(client_with_fake_stub) -> None:
    rc, _ = client_with_fake_stub()
    with pytest.raises(ValueError, match="Latitude"):
        await rc.takeoff(TakeoffRequest(sn="DOCK-001", latitude=99.0, longitude=0.0, altitude=10.0))


@pytest.mark.asyncio
async def test_enter_manual_control_rejects_blank_client_id(client_with_fake_stub) -> None:
    rc, _ = client_with_fake_stub()
    with pytest.raises(ValueError, match="clientId"):
        await rc.enter_manual_control(ManualControlRequest(sn="DOCK-001", client_id="", user_id="u", session_id="s"))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_takeoff_builds_proto_and_parses_response(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    resp = await rc.takeoff(TakeoffRequest(sn="DOCK-001", latitude=47.5, longitude=8.5, altitude=120.0))
    sent, _timeout = stub.calls["TakeOff"]
    assert sent.base.sn == "DOCK-001"
    assert sent.base.tid  # uuid auto-generated
    assert sent.request.latitude == pytest.approx(47.5)
    assert sent.request.longitude == pytest.approx(8.5)
    assert sent.request.altitude == pytest.approx(120.0)

    assert resp.success is True
    assert resp.sn == "DOCK-001"
    assert resp.tid == "tid-123"
    assert resp.message == "ok"
    assert resp.error is None


@pytest.mark.asyncio
async def test_go_to_passes_through_coordinates(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.go_to(GoToRequest(sn="DOCK-001", latitude=10.0, longitude=20.0, altitude=30.0))
    sent, _ = stub.calls["GoTo"]
    assert (sent.request.latitude, sent.request.longitude, sent.request.altitude) == (
        pytest.approx(10.0),
        pytest.approx(20.0),
        pytest.approx(30.0),
    )


@pytest.mark.asyncio
async def test_return_to_home_optional_altitude(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.return_to_home(ReturnToHomeRequest(sn="DOCK-001"))
    sent, _ = stub.calls["ReturnToHome"]
    assert sent.request.HasField("altitude") is False

    await rc.return_to_home(ReturnToHomeRequest(sn="DOCK-001", altitude=50.0))
    sent, _ = stub.calls["ReturnToHome"]
    assert sent.request.altitude == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_look_at_calls_correct_rpc(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.look_at(LookAtRequest(sn="DOCK-001", latitude=1.0, longitude=2.0, altitude=3.0))
    assert "LookAt" in stub.calls


@pytest.mark.asyncio
async def test_enter_and_exit_manual_control_call_correct_rpcs(
    client_with_fake_stub,
) -> None:
    rc, stub = client_with_fake_stub()
    request = ManualControlRequest(sn="DOCK-001", client_id="c1", user_id="u1", session_id="s1", reason="test")
    await rc.enter_manual_control(request)
    await rc.exit_manual_control(request)
    assert "EnterManualControl" in stub.calls
    assert "ExitManualControl" in stub.calls
    sent, _ = stub.calls["EnterManualControl"]
    assert sent.request.clientId == "c1"
    assert sent.request.reason == "test"


@pytest.mark.asyncio
async def test_close_cover_force_flag(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.close_cover(DockOperationRequest(sn="DOCK-001", value=True))
    sent, _ = stub.calls["CloseCover"]
    assert sent.force is True


@pytest.mark.asyncio
async def test_dock_and_asset_ops_send_only_base(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    req = DockOperationRequest(sn="DOCK-001")
    await rc.open_cover(req)
    await rc.start_charging(req)
    await rc.stop_charging(req)
    await rc.reboot_asset(req)
    await rc.change_ac_mode(req)
    for name in (
        "OpenCover",
        "StartCharging",
        "StopCharging",
        "RebootAsset",
        "ChangeAcMode",
    ):
        assert name in stub.calls
        sent, _ = stub.calls[name]
        assert sent.base.sn == "DOCK-001"


@pytest.mark.asyncio
async def test_boot_sub_asset_passes_value(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.boot_sub_asset(DockOperationRequest(sn="DOCK-001", value=True))
    sent, _ = stub.calls["BootSubAsset"]
    assert sent.boot is True


@pytest.mark.asyncio
async def test_debug_mode_passes_value(client_with_fake_stub) -> None:
    rc, stub = client_with_fake_stub()
    await rc.debug_mode(DockOperationRequest(sn="DOCK-001", value=True))
    sent, _ = stub.calls["EnterOrCloseRemoteDebugMode"]
    assert sent.enabled is True


# ---------------------------------------------------------------------------
# Error response parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_response_is_decoded(client_with_fake_stub) -> None:
    rc, _ = client_with_fake_stub(response=_error_response())
    resp = await rc.takeoff(TakeoffRequest(sn="DOCK-001", latitude=0.0, longitude=0.0, altitude=10.0))
    assert resp.success is False
    assert resp.error is not None
    assert resp.error.error_code == "ASSET_ERROR"
    assert resp.error.error_message == "boom"

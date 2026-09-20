"""
Integration tests for EdgeServer.

A real gRPC server is started in-process on a random port.
No gRPC mocks – this validates the full stack: proto serialisation,
servicer routing, status codes, and exception handling.
"""

import grpc
import grpc.aio
import pytest
from zqnt_utils.generated.zqnt import common_pb2, edge_pb2_grpc  # type: ignore[import]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base(tid: str = "test-tid", sn: str = "TEST-001"):
    from google.protobuf import timestamp_pb2

    ts = timestamp_pb2.Timestamp()
    ts.GetCurrentTime()
    return common_pb2.RequestBase(tid=tid, sn=sn, timestamp=ts)


# ---------------------------------------------------------------------------
# GetCapabilities
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_capabilities_returns_response(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.GetCapabilities(common_pb2.AssetCapabilitiesRequest(sn="TEST-001"))
    assert resp.HasField("capabilities") or resp.HasField("error") is False


@pytest.mark.asyncio
async def test_get_capabilities_start_task_available(server_port):
    """_TestAdapter overrides start_task → must be available=True."""
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.GetCapabilities(common_pb2.AssetCapabilitiesRequest(sn="TEST-001"))

    caps_by_command = {
        c.command_id: c.state == common_pb2.CAPABILITY_STATE_AVAILABLE for c in resp.capabilities.capabilities
    }
    assert caps_by_command.get("mission.start") is True
    assert caps_by_command.get("flight.takeoff") is False
    assert caps_by_command.get("dock.open_cover") is False


# ---------------------------------------------------------------------------
# Supported method → OK response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_task_returns_ok(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.StartTask(common_pb2.TaskCommandRequest(base=_base(), task_id="task-42"))
    assert resp.has_errors is False or resp.has_errors is None


@pytest.mark.asyncio
async def test_start_task_reports_external_execution_id(server_port):
    """EdgeResponse.external_execution_id must reach meta.external_id on the wire —
    it's what mission-autonomy correlates later cancellation/completion events by."""
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.StartTask(common_pb2.TaskCommandRequest(base=_base(), task_id="task-42"))
    assert resp.meta.external_id == "vendor-task-42"


@pytest.mark.asyncio
async def test_send_custom_command_reports_external_execution_id(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.SendCustomCommand(
            common_pb2.CustomCommandRequest(base=_base(), command_id="mission.waypoint.execute")
        )
    assert resp.meta.external_id == "vendor-mission.waypoint.execute"


# ---------------------------------------------------------------------------
# Not-overridden method → UNIMPLEMENTED gRPC status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_off_not_implemented_returns_unimplemented(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.TakeOff(
                common_pb2.CoordinateCommandRequest(
                    base=_base(),
                    coordinate=common_pb2.GeoCoordinate(latitude=47.5, longitude=9.7, altitude=10.0),
                )
            )
    assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_open_cover_not_implemented_returns_unimplemented(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.OpenCover(common_pb2.EmptyCommandRequest(base=_base()))
    assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED


# ---------------------------------------------------------------------------
# Adapter exception → error response (no server crash)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_exception_returns_error_not_crash(crashing_server_port):
    """
    _CrashingAdapter.start_task raises RuntimeError.
    The server must return an error response, NOT crash or return INTERNAL.
    """
    async with grpc.aio.insecure_channel(f"localhost:{crashing_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.StartTask(common_pb2.TaskCommandRequest(base=_base(), task_id="boom"))
    assert resp.has_errors is True
    assert resp.error.error_message != ""


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_serving(server_port):
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = health_pb2_grpc.HealthStub(ch)
        resp = await stub.Check(health_pb2.HealthCheckRequest(service=""))
    assert resp.status == health_pb2.HealthCheckResponse.SERVING


@pytest.mark.asyncio
async def test_health_check_edge_adapter_service(server_port):
    from grpc_health.v1 import health_pb2, health_pb2_grpc

    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = health_pb2_grpc.HealthStub(ch)
        resp = await stub.Check(health_pb2.HealthCheckRequest(service="EdgeAdapterService"))
    assert resp.status == health_pb2.HealthCheckResponse.SERVING


# ---------------------------------------------------------------------------
# Registration-only adapter: advertised must equal executable
#
# The servicer used to gate every RPC on "did a subclass override this method", which a
# register_command declaration never does — so an adapter built the 2.0 way advertised commands
# its own server then refused with UNIMPLEMENTED (edge-mavlink's mission.waypoint.execute being
# the reported case). These run against an adapter that overrides nothing but get_capabilities.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registered_command_is_dispatched_over_grpc(registry_server_port, registry_adapter):
    async with grpc.aio.insecure_channel(f"localhost:{registry_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.SendCustomCommand(
            common_pb2.CustomCommandRequest(base=_base(), command_id="mission.waypoint.execute")
        )
    assert resp.has_errors is False
    assert registry_adapter.calls, "handler was never reached"


@pytest.mark.asyncio
async def test_registered_command_backs_its_typed_rpc(registry_server_port, registry_adapter):
    """A handler registered for flight.takeoff also serves the TakeOff RPC, via _delegate."""
    async with grpc.aio.insecure_channel(f"localhost:{registry_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.TakeOff(
            common_pb2.CoordinateCommandRequest(
                base=_base(),
                coordinate=common_pb2.GeoCoordinate(latitude=52.5, longitude=13.4, altitude=30.0),
            )
        )
    assert resp.has_errors is False
    assert registry_adapter.calls, "handler was never reached"


@pytest.mark.asyncio
async def test_unknown_command_answers_with_error_not_abort(registry_server_port):
    """
    An id the adapter cannot place comes back as a failed response, not a gRPC abort.

    mission-autonomy's default dispatch branch reads response.getHasErrors(); an UNIMPLEMENTED
    abort surfaces as a transport failure instead, which it reports as an unreachable asset
    rather than an unsupported command.
    """
    async with grpc.aio.insecure_channel(f"localhost:{registry_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.SendCustomCommand(
            common_pb2.CustomCommandRequest(base=_base(), command_id="vendor.nope.nothing")
        )
    assert resp.has_errors is True


@pytest.mark.asyncio
async def test_unregistered_typed_rpc_still_unimplemented(registry_server_port):
    """The gate still closes for a command that is neither overridden nor registered."""
    async with grpc.aio.insecure_channel(f"localhost:{registry_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.OpenCover(common_pb2.EmptyCommandRequest(base=_base()))
    assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_capabilities_carry_skill_and_display_name(registry_server_port):
    async with grpc.aio.insecure_channel(f"localhost:{registry_server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.GetCapabilities(common_pb2.AssetCapabilitiesRequest(sn="TEST-001"))

    by_id = {c.command_id: c for c in resp.capabilities.capabilities}
    assert by_id["mission.waypoint.execute"].skill_id == "mission"
    assert by_id["mission.waypoint.execute"].display_name == "Fly waypoint mission"
    # Grouped by meaning, not by the id's leading segment.
    assert by_id["flight.manual.enter"].skill_id == "manual_control"
    assert by_id["flight.takeoff"].skill_id == "flight"

"""
Integration tests for EdgeServer.

A real gRPC server is started in-process on a random port.
No gRPC mocks – this validates the full stack: proto serialisation,
servicer routing, status codes, and exception handling.
"""

import grpc
import grpc.aio
import pytest

from edge_sdk.generated import common_pb2, edge_pb2, edge_pb2_grpc  # type: ignore[import]

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
        resp = await stub.GetCapabilities(edge_pb2.EdgeGetCapabilitiesRequest(sn="TEST-001"))
    assert resp.HasField("capabilities") or resp.HasField("error") is False


@pytest.mark.asyncio
async def test_get_capabilities_start_task_available(server_port):
    """_TestAdapter overrides start_task → must be available=True."""
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.GetCapabilities(edge_pb2.EdgeGetCapabilitiesRequest(sn="TEST-001"))

    caps_by_command = {c.command: c.available for c in resp.capabilities.capabilities}
    assert caps_by_command.get("StartTask") is True
    assert caps_by_command.get("TakeOff") is False
    assert caps_by_command.get("OpenCover") is False


# ---------------------------------------------------------------------------
# Supported method → OK response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_task_returns_ok(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.StartTask(edge_pb2.EdgeStartTaskRequest(base=_base(), taskId="task-42"))
    assert resp.hasErrors is False or resp.hasErrors is None


# ---------------------------------------------------------------------------
# Not-overridden method → UNIMPLEMENTED gRPC status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_off_not_implemented_returns_unimplemented(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.TakeOff(
                edge_pb2.EdgeTakeOffRequest(
                    base=_base(),
                    request=common_pb2.Coordinates(latitude=47.5, longitude=9.7, altitude=10.0),
                )
            )
    assert exc_info.value.code() == grpc.StatusCode.UNIMPLEMENTED


@pytest.mark.asyncio
async def test_open_cover_not_implemented_returns_unimplemented(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await stub.OpenCover(edge_pb2.EdgeOpenCoverRequest(base=_base()))
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
        resp = await stub.StartTask(edge_pb2.EdgeStartTaskRequest(base=_base(), taskId="boom"))
    assert resp.hasErrors is True
    assert resp.error.errorMessage != ""


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

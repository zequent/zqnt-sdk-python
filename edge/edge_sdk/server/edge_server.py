"""
EdgeServer – wraps the generated EdgeAdapterService gRPC servicer and
delegates every call to the user's EdgeAdapter implementation.

Usage (minimal)::

    server = EdgeServer(adapter=MyAdapter(), port=50051)
    asyncio.run(server.serve())

Usage with automatic service discovery registration::

    server = EdgeServer(
        adapter=MyAdapter(),
        port=50051,
        registration=RegistrationConfig(
            endpoint="grpc://my-adapter.internal:50051",
            asset_type=AssetType.DOCK,
            asset_vendor=AssetVendor.DJI,
            redis_url="redis://redis:6379",
        ),
    )
    asyncio.run(server.serve())
"""

import asyncio
import dataclasses
import json
import logging
from typing import Any

import grpc
import grpc.aio

from ..adapter.base import EdgeAdapter

# Generated modules – populated after running scripts/generate_protos.sh
try:
    from google.protobuf import empty_pb2, timestamp_pb2

    from ..generated import (  # type: ignore[import]
        common_pb2,  # type: ignore[import]
        edge_pb2,
        edge_pb2_grpc,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError("Protobuf stubs not found. Run  scripts/generate_protos.sh  first.") from exc

from ..models.common import (
    AssetAirConditionerState,
    AssetType,
    AssetVendor,
    EdgeResponse,
    ErrorCode,
    ErrorMessage,
    RequestContext,
)
from ._converters import (
    capabilities_to_proto,
    edge_response_to_proto,
    proto_to_asset,
    proto_to_change_lens,
    proto_to_change_zoom,
    proto_to_coordinates,
    proto_to_live_stream_start,
    proto_to_live_stream_stop,
    proto_to_manual_control_input,
    proto_to_manual_control_request,
    proto_to_request_context,
    proto_to_return_to_home,
)


@dataclasses.dataclass
class RegistrationConfig:
    """
    Configuration for automatic edge endpoint registration in Redis on startup.

    The SDK registers an ``EdgeEndpointDTO`` in Redis when the server starts
    (``online=True``) and marks it offline when the server stops (``online=False``).
    This makes the adapter discoverable by the platform's client-side load balancer.

    Args:
        endpoint:     The gRPC endpoint other services use to reach this adapter
                      (e.g. ``"grpc://my-adapter.internal:50051"``).
        asset_type:   Type of asset this adapter manages.
        asset_vendor: Vendor of the asset.
        redis_url:    Redis connection URL (e.g. ``"redis://redis:6379"``).

    Redis key format (matches Java CacheKeys.EDGE_ENDPOINTS)::

        edge-endpoints:{VENDOR}   e.g. "edge-endpoints:DJI"

    Environment variable alternative — use :meth:`from_env` to read everything
    from environment variables (recommended for Kubernetes deployments)::

        registration=RegistrationConfig.from_env()

    Expected env vars::

        EDGE_ENDPOINT   grpc://my-adapter.internal:50051
        ASSET_TYPE      SENSOR          # must match AssetType enum name
        ASSET_VENDOR    ROS             # must match AssetVendor enum name
        REDIS_URL       redis://redis:6379
    """

    endpoint: str
    asset_type: AssetType
    asset_vendor: AssetVendor
    redis_url: str

    @classmethod
    def from_env(cls) -> "RegistrationConfig":
        """Build from environment variables (recommended for Kubernetes)."""
        import os

        return cls(
            endpoint=os.environ["EDGE_ENDPOINT"],
            asset_type=AssetType[os.environ["ASSET_TYPE"]],
            asset_vendor=AssetVendor[os.environ["ASSET_VENDOR"]],
            redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379"),
        )


logger = logging.getLogger(__name__)


def _ok_or_error(response: EdgeResponse, ctx_tid: str, ctx_sn: str):
    return edge_response_to_proto(response, edge_pb2, timestamp_pb2, empty_pb2, common_pb2)


def _error_proto(tid: str, sn: str, exc: Exception):
    resp = EdgeResponse.fail(tid, sn, ErrorMessage(str(exc), ErrorCode.ASSET_ERROR))
    return edge_response_to_proto(resp, edge_pb2, timestamp_pb2, empty_pb2, common_pb2)


class _EdgeAdapterServicer(edge_pb2_grpc.EdgeAdapterServiceServicer):
    """gRPC servicer that delegates to the user-supplied EdgeAdapter."""

    def __init__(self, adapter: EdgeAdapter) -> None:
        self._adapter = adapter

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _assert_supported(self, method_name: str, context) -> None:
        """Abort with UNIMPLEMENTED if the adapter has not overridden *method_name*."""
        base = getattr(EdgeAdapter, method_name, None)
        impl = getattr(type(self._adapter), method_name, None)
        if base is impl:
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                f"{method_name} is not supported by this adapter",
            )

    async def _handle_call(self, ctx: RequestContext, coro: Any):
        """
        Await *coro*, convert the result to a proto EdgeResponse.
        Any exception from the adapter is caught and returned as an error response
        instead of crashing the gRPC call.
        """
        try:
            result = await coro
            return _ok_or_error(result, ctx.tid, ctx.sn)
        except Exception as exc:
            logger.exception("Adapter error [tid=%s sn=%s]", ctx.tid, ctx.sn)
            return _error_proto(ctx.tid, ctx.sn, exc)

    # ------------------------------------------------------------------
    # Capability
    # ------------------------------------------------------------------

    async def GetCapabilities(self, request, context):
        try:
            caps = await self._adapter.get_capabilities(
                sn=request.sn,
                asset_id=request.assetId if request.HasField("assetId") else None,
            )
            return edge_pb2.EdgeGetCapabilitiesResponse(
                capabilities=capabilities_to_proto(caps, common_pb2, timestamp_pb2),
            )
        except Exception as exc:
            logger.exception("GetCapabilities error")
            return edge_pb2.EdgeGetCapabilitiesResponse(
                error=common_pb2.GlobalErrorMessage(
                    errorMessage=str(exc),
                    errorCode=int(ErrorCode.SDK_ERROR),
                )
            )

    # ------------------------------------------------------------------
    # Flight control
    # ------------------------------------------------------------------

    async def TakeOff(self, request, context):
        await self._assert_supported("take_off", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.take_off(ctx, proto_to_coordinates(request.request)))

    async def GoTo(self, request, context):
        await self._assert_supported("go_to", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.go_to(ctx, proto_to_coordinates(request.request)))

    async def ReturnToHome(self, request, context):
        await self._assert_supported("return_to_home", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.return_to_home(ctx, proto_to_return_to_home(request.request)),
        )

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------

    async def EnterManualControl(self, request, context):
        await self._assert_supported("enter_manual_control", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.enter_manual_control(ctx, proto_to_manual_control_request(request.request)),
        )

    async def ExitManualControl(self, request, context):
        await self._assert_supported("exit_manual_control", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.exit_manual_control(ctx, proto_to_manual_control_request(request.request)),
        )

    async def ManualControlInput(self, request_iterator, context):
        await self._assert_supported("manual_control_input", context)
        ctx = None

        async def _input_gen():
            nonlocal ctx
            async for req in request_iterator:
                if ctx is None:
                    ctx = proto_to_request_context(req.base)
                yield proto_to_manual_control_input(req.request)

        try:
            gen = _input_gen()
            result = await self._adapter.manual_control_input(ctx or _dummy_ctx(), gen)
            return _ok_or_error(result, ctx.tid if ctx else "", ctx.sn if ctx else "")
        except Exception as exc:
            tid = ctx.tid if ctx else ""
            sn = ctx.sn if ctx else ""
            logger.exception("Adapter error in ManualControlInput [tid=%s sn=%s]", tid, sn)
            return _error_proto(tid, sn, exc)

    # ------------------------------------------------------------------
    # Gimbal & camera
    # ------------------------------------------------------------------

    async def LookAt(self, request, context):
        await self._assert_supported("look_at", context)
        ctx = proto_to_request_context(request.base)
        payload_index = request.payloadIndex if request.HasField("payloadIndex") else None
        locked = request.locked if request.HasField("locked") else None
        return await self._handle_call(
            ctx,
            self._adapter.look_at(ctx, proto_to_coordinates(request.request), payload_index, locked),
        )

    async def TakePhoto(self, request, context):
        await self._assert_supported("take_photo", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.take_photo(ctx))

    async def EnableGimbalTracking(self, request, context):
        await self._assert_supported("enable_gimbal_tracking", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.enable_gimbal_tracking(ctx, request.enabled))

    # ------------------------------------------------------------------
    # Detection  (server-streaming)
    # ------------------------------------------------------------------

    async def GetDetections(self, request, context):
        await self._assert_supported("get_detections", context)
        ctx = proto_to_request_context(request.base)
        stream_url = request.streamUrl if request.HasField("streamUrl") else None
        try:
            async for detection in self._adapter.get_detections(ctx, stream_url):
                results = [
                    edge_pb2.EdgeDetectionResponse.DetectionResult(
                        objectId=d.object_id,
                        objectType=d.object_type,
                        confidence=d.confidence,
                        boundingBox=edge_pb2.EdgeDetectionResponse.DetectionResult.BoundingBox(
                            x=d.bounding_box.x,
                            y=d.bounding_box.y,
                            width=d.bounding_box.width,
                            height=d.bounding_box.height,
                        ),
                    )
                    for d in detection.detections
                ]
                yield edge_pb2.EdgeDetectionResponse(base=request.base, detections=results)
        except NotImplementedError:
            await context.abort(
                grpc.StatusCode.UNIMPLEMENTED,
                "GetDetections is not supported by this adapter",
            )
        except Exception as exc:
            logger.exception("Error in GetDetections [tid=%s]", ctx.tid)
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    # ------------------------------------------------------------------
    # Dock operations
    # ------------------------------------------------------------------

    async def OpenCover(self, request, context):
        await self._assert_supported("open_cover", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.open_cover(ctx))

    async def CloseCover(self, request, context):
        await self._assert_supported("close_cover", context)
        ctx = proto_to_request_context(request.base)
        force = request.force if request.HasField("force") else None
        return await self._handle_call(ctx, self._adapter.close_cover(ctx, force))

    async def StartCharging(self, request, context):
        await self._assert_supported("start_charging", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.start_charging(ctx))

    async def StopCharging(self, request, context):
        await self._assert_supported("stop_charging", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.stop_charging(ctx))

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    async def RebootAsset(self, request, context):
        await self._assert_supported("reboot_asset", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.reboot_asset(ctx))

    async def BootUpSubAsset(self, request, context):
        await self._assert_supported("boot_up_sub_asset", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.boot_up_sub_asset(ctx))

    async def BootDownSubAsset(self, request, context):
        await self._assert_supported("boot_down_sub_asset", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.boot_down_sub_asset(ctx))

    async def RegisterAsset(self, request, context):
        await self._assert_supported("register_asset", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.register_asset(ctx, proto_to_asset(request.assetDTO)))

    async def DeRegisterAsset(self, request, context):
        await self._assert_supported("deregister_asset", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.deregister_asset(ctx))

    # ------------------------------------------------------------------
    # Debug & maintenance
    # ------------------------------------------------------------------

    async def EnterOrCloseRemoteDebugMode(self, request, context):
        await self._assert_supported("enter_or_close_remote_debug_mode", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.enter_or_close_remote_debug_mode(ctx, request.enabled),
        )

    async def ChangeAcMode(self, request, context):
        await self._assert_supported("change_ac_mode", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.change_ac_mode(ctx, AssetAirConditionerState(request.mode)),
        )

    # ------------------------------------------------------------------
    # Live stream
    # ------------------------------------------------------------------

    async def StartLiveStream(self, request, context):
        await self._assert_supported("start_live_stream", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.start_live_stream(ctx, proto_to_live_stream_start(request.request)),
        )

    async def StopLiveStream(self, request, context):
        await self._assert_supported("stop_live_stream", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(
            ctx,
            self._adapter.stop_live_stream(ctx, proto_to_live_stream_stop(request.request)),
        )

    async def ChangeLens(self, request, context):
        await self._assert_supported("change_lens", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.change_lens(ctx, proto_to_change_lens(request.request)))

    async def ChangeZoom(self, request, context):
        await self._assert_supported("change_zoom", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.change_zoom(ctx, proto_to_change_zoom(request.request)))

    async def CapturePhoto(self, request, context):
        await self._assert_supported("capture_photo", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.capture_photo(ctx))

    async def StartRecording(self, request, context):
        await self._assert_supported("start_recording", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.start_recording(ctx))

    async def StopRecording(self, request, context):
        await self._assert_supported("stop_recording", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.stop_recording(ctx))

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def PrepareTask(self, request, context):
        await self._assert_supported("prepare_task", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.prepare_task(ctx, request.taskId))

    async def StartTask(self, request, context):
        await self._assert_supported("start_task", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.start_task(ctx, request.taskId))

    async def StopTask(self, request, context):
        await self._assert_supported("stop_task", context)
        ctx = proto_to_request_context(request.base)
        return await self._handle_call(ctx, self._adapter.stop_task(ctx, request.taskId))


def _dummy_ctx() -> RequestContext:
    from datetime import datetime, timezone

    return RequestContext(tid="", sn="", timestamp=datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Public server class
# ---------------------------------------------------------------------------


class EdgeServer:
    """
    gRPC server that exposes your EdgeAdapter implementation as an
    ``EdgeAdapterService`` endpoint.

    Also registers the standard gRPC health check service
    (``grpc.health.v1.Health``) so Kubernetes liveness/readiness probes work
    out of the box.

    If *registration* is provided, the server automatically registers the
    adapter endpoint in Redis on startup and marks it offline on stop —
    no manual steps needed in the adapter implementation.

    Args:
        adapter:       Your :class:`~edge_sdk.EdgeAdapter` subclass instance.
        port:          TCP port to listen on (default 50051).
        host:          Bind address (default ``[::]`` = all interfaces).
        registration:  Optional :class:`RegistrationConfig` for automatic
                       service-discovery registration in Redis.

    Example::

        server = EdgeServer(
            adapter=MyAdapter(),
            port=50051,
            registration=RegistrationConfig(
                endpoint="grpc://my-adapter.internal:50051",
                asset_type=AssetType.DOCK,
                asset_vendor=AssetVendor.DJI,
                redis_url="redis://redis:6379",
            ),
        )
        asyncio.run(server.serve())
    """

    def __init__(
        self,
        adapter: EdgeAdapter,
        port: int = 50051,
        host: str = "[::]",
        registration: RegistrationConfig | None = None,
    ) -> None:
        self._adapter = adapter
        self._port = port
        self._host = host
        self._registration = registration
        self._server: grpc.aio.Server | None = None
        self._health_servicer = None

    async def serve(self) -> None:
        """Start the server and block until it is terminated."""
        self._server = grpc.aio.server()

        # Register EdgeAdapterService
        edge_pb2_grpc.add_EdgeAdapterServiceServicer_to_server(_EdgeAdapterServicer(self._adapter), self._server)

        # Register standard gRPC health check (used by k8s probes)
        try:
            from grpc_health.v1 import health, health_pb2, health_pb2_grpc

            self._health_servicer = health.HealthServicer()
            health_pb2_grpc.add_HealthServicer_to_server(self._health_servicer, self._server)
            self._health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
            self._health_servicer.set("EdgeAdapterService", health_pb2.HealthCheckResponse.SERVING)
            logger.debug("gRPC health check service registered")
        except ImportError:
            logger.warning(
                "grpcio-health-checking not installed – health check unavailable. "
                "Add grpcio-health-checking to your dependencies."
            )

        listen_addr = f"{self._host}:{self._port}"
        self._server.add_insecure_port(listen_addr)
        await self._server.start()
        logger.info("EdgeServer listening on %s", listen_addr)

        if self._registration:
            await self._register(online=True)
        try:
            await self._server.wait_for_termination()
        except (asyncio.CancelledError, KeyboardInterrupt):
            await self.stop()

    async def stop(self, grace: float = 5.0) -> None:
        """Gracefully stop the server."""
        if self._registration:
            await self._register(online=False)

        if self._health_servicer is not None:
            try:
                from grpc_health.v1 import health_pb2

                self._health_servicer.set("", health_pb2.HealthCheckResponse.NOT_SERVING)
                self._health_servicer.set("EdgeAdapterService", health_pb2.HealthCheckResponse.NOT_SERVING)
            except ImportError:
                pass
        if self._server:
            await self._server.stop(grace)
            logger.info("EdgeServer stopped")

    async def _register(self, *, online: bool) -> None:
        """
        Write (or update) the EdgeEndpointDTO in Redis via CachingService.

        Uses key ``edge-endpoints:{vendor}`` — matches Java CacheKeys.EDGE_ENDPOINTS
        so the platform's client-side load balancer can resolve the endpoint.
        Falls back to a direct redis call if zqnt-utils is not installed.
        """
        cfg = self._registration  # type: ignore[union-attr]
        vendor = cfg.asset_vendor.name

        try:
            from zqnt_utils.caching import CachingService
            from zqnt_utils.core import EdgeEndpointDTO

            dto = EdgeEndpointDTO(
                endpoint=cfg.endpoint,
                online=online,
                asset_type=cfg.asset_type.name,
                asset_vendor=vendor,
            )
            async with CachingService(cfg.redis_url) as cache:
                if online:
                    await cache.register_edge_endpoint(vendor, dto)
                else:
                    await cache.deregister_edge_endpoint(vendor)

        except ImportError:
            # zqnt-utils not installed – fall back to inline implementation
            try:
                import redis.asyncio as aioredis
            except ImportError:
                logger.warning(
                    "Neither zqnt-utils nor redis package installed – "
                    "endpoint registration skipped. "
                    "Install with: pip install 'edge-python-sdk[redis]'"
                )
                return

            key = f"edge-endpoints:{vendor}"
            dto_json = json.dumps(
                {
                    "endpoint": cfg.endpoint,
                    "online": online,
                    "assetType": cfg.asset_type.name,
                    "assetVendor": vendor,
                }
            )
            try:
                async with aioredis.from_url(cfg.redis_url, decode_responses=True) as r:
                    await r.set(key, dto_json)
            except Exception as exc:
                logger.error("Edge endpoint registration failed (online=%s): %s", online, exc)
                return

        except Exception as exc:
            # Never crash the server because of a registration failure.
            logger.error("Edge endpoint registration failed (online=%s): %s", online, exc)
            return

        if online:
            logger.info(
                "Edge endpoint registered [key=edge-endpoints:%s endpoint=%s type=%s]",
                vendor,
                cfg.endpoint,
                cfg.asset_type.name,
            )
        else:
            logger.info("Edge endpoint marked offline [key=edge-endpoints:%s]", vendor)

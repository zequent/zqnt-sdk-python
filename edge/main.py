"""
Example Edge Adapter implementation.

This file shows how to subclass EdgeAdapter and wire everything up.
It does NOT contain real hardware logic – replace the stubs with your
actual drone / dock SDK calls.

Run with:
    python main.py
"""

import asyncio
import logging
from typing import AsyncIterator

from edge_sdk import (
    Asset,
    AssetTelemetry,
    AssetType,
    Capabilities,
    Capability,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    ConnectorClient,
    Coordinates,
    DetectionResponse,
    EdgeAdapter,
    EdgeResponse,
    EdgeServer,
    LiveStreamStartRequest,
    LiveStreamStopRequest,
    ManualControlInput,
    ManualControlRequest,
    RequestContext,
    ReturnToHomeRequest,
    SubAssetTelemetry,
    TelemetryPublisher,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PLATFORM_HOST = "localhost"
EDGE_SERVICE_PORT = 50051  # incoming commands from the platform
LIVE_DATA_PORT = 50052  # outgoing telemetry to the platform
CONNECTOR_PORT = 50053  # task/mission queries
ASSET_SN = "DOCK-001"


# ---------------------------------------------------------------------------
# Adapter implementation
# ---------------------------------------------------------------------------


class MyDockAdapter(EdgeAdapter):
    """
    Minimal example adapter for a DJI Dock + drone system.
    Replace every pass / comment with your actual hardware SDK calls.
    """

    def __init__(
        self, connector: ConnectorClient, publisher: TelemetryPublisher
    ) -> None:
        self._connector = connector
        self._publisher = publisher

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    async def get_capabilities(self, sn: str, asset_id: str | None) -> Capabilities:
        return Capabilities(
            asset_sn=sn,
            asset_type=AssetType.DOCK,
            capabilities=[
                Capability("TakeOff", "Launch the drone", available=True),
                Capability("GoTo", "Fly to coordinates", available=True),
                Capability("ReturnToHome", "RTH", available=True),
                Capability("OpenCover", "Open dock lid", available=True),
                Capability("CloseCover", "Close dock lid", available=True),
                Capability("StartCharging", "Begin battery charge", available=True),
                Capability("StopCharging", "End battery charge", available=True),
                Capability("StartLiveStream", "Start RTMP/RTSP stream", available=True),
                Capability("StopLiveStream", "Stop the video stream", available=True),
                Capability("StartTask", "Execute a mission task", available=True),
                Capability("StopTask", "Abort running task", available=True),
            ],
        )

    # ------------------------------------------------------------------
    # Flight control
    # ------------------------------------------------------------------

    async def take_off(
        self, ctx: RequestContext, coordinates: Coordinates
    ) -> EdgeResponse:
        logger.info(
            "[%s] TakeOff → lat=%s lon=%s alt=%s",
            ctx.sn,
            coordinates.latitude,
            coordinates.longitude,
            coordinates.altitude,
        )
        # TODO: call your drone SDK here
        return EdgeResponse.ok(ctx.tid, ctx.sn, "TakeOff initiated")

    async def go_to(
        self, ctx: RequestContext, coordinates: Coordinates
    ) -> EdgeResponse:
        logger.info("[%s] GoTo → %s", ctx.sn, coordinates)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def return_to_home(
        self, ctx: RequestContext, request: ReturnToHomeRequest
    ) -> EdgeResponse:
        logger.info("[%s] ReturnToHome alt=%s", ctx.sn, request.altitude)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------

    async def enter_manual_control(
        self, ctx: RequestContext, request: ManualControlRequest
    ) -> EdgeResponse:
        logger.info("[%s] EnterManualControl session=%s", ctx.sn, request.session_id)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def exit_manual_control(
        self, ctx: RequestContext, request: ManualControlRequest
    ) -> EdgeResponse:
        logger.info("[%s] ExitManualControl session=%s", ctx.sn, request.session_id)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def manual_control_input(
        self, ctx: RequestContext, inputs: AsyncIterator[ManualControlInput]
    ) -> EdgeResponse:
        async for inp in inputs:
            logger.debug(
                "[%s] Input roll=%s pitch=%s yaw=%s throttle=%s",
                ctx.sn,
                inp.roll,
                inp.pitch,
                inp.yaw,
                inp.throttle,
            )
            # TODO: forward to drone RC SDK
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Gimbal & camera
    # ------------------------------------------------------------------

    async def look_at(
        self,
        ctx: RequestContext,
        coordinates: Coordinates,
        payload_index: str | None,
        locked: bool | None,
    ) -> EdgeResponse:
        logger.info("[%s] LookAt %s", ctx.sn, coordinates)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def take_photo(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] TakePhoto", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def enable_gimbal_tracking(
        self, ctx: RequestContext, enabled: bool
    ) -> EdgeResponse:
        logger.info("[%s] GimbalTracking enabled=%s", ctx.sn, enabled)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Dock operations
    # ------------------------------------------------------------------

    async def open_cover(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] OpenCover", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def close_cover(
        self, ctx: RequestContext, force: bool | None
    ) -> EdgeResponse:
        logger.info("[%s] CloseCover force=%s", ctx.sn, force)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_charging(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] StartCharging", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def stop_charging(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] StopCharging", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    async def reboot_asset(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] RebootAsset", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def boot_up_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] BootUpSubAsset", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def boot_down_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] BootDownSubAsset", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def register_asset(self, ctx: RequestContext, asset: Asset) -> EdgeResponse:
        logger.info("[%s] RegisterAsset id=%s name=%s", ctx.sn, asset.id, asset.name)
        return EdgeResponse.ok(ctx.tid, ctx.sn, asset_id=asset.id)

    async def deregister_asset(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] DeRegisterAsset", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Live stream
    # ------------------------------------------------------------------

    async def start_live_stream(
        self, ctx: RequestContext, request: LiveStreamStartRequest
    ) -> EdgeResponse:
        stream_url = f"rtmp://edge-host/{request.video_id}"
        logger.info("[%s] StartLiveStream url=%s", ctx.sn, stream_url)
        return EdgeResponse.ok(
            ctx.tid,
            ctx.sn,
            stream_url=stream_url,
            video_id=request.video_id,
        )

    async def stop_live_stream(
        self, ctx: RequestContext, request: LiveStreamStopRequest
    ) -> EdgeResponse:
        logger.info("[%s] StopLiveStream video_id=%s", ctx.sn, request.video_id)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def change_lens(
        self, ctx: RequestContext, request: ChangeCameraLensRequest
    ) -> EdgeResponse:
        logger.info("[%s] ChangeLens lens=%s", ctx.sn, request.lens)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def change_zoom(
        self, ctx: RequestContext, request: ChangeCameraZoomRequest
    ) -> EdgeResponse:
        logger.info("[%s] ChangeZoom zoom=%s", ctx.sn, request.zoom)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def capture_photo(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] CapturePhoto", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_recording(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] StartRecording", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def stop_recording(self, ctx: RequestContext) -> EdgeResponse:
        logger.info("[%s] StopRecording", ctx.sn)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def prepare_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        logger.info("[%s] PrepareTask task_id=%s", ctx.sn, task_id)
        # Fetch full task definition from the platform:
        task = await self._connector.get_task(task_id)
        if task is None:
            from edge_sdk import ErrorCode, ErrorMessage

            return EdgeResponse.fail(
                ctx.tid,
                ctx.sn,
                ErrorMessage(f"Task {task_id!r} not found", ErrorCode.CLIENT_ERROR),
            )
        logger.info(
            "  type=%s waypoints=%s",
            task.task_type,
            len(task.waypoint_config.waypoints) if task.waypoint_config else 0,
        )
        # TODO: upload waypoints to drone, run pre-flight checks, etc.
        return EdgeResponse.ok(ctx.tid, ctx.sn, "Task prepared")

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        logger.info("[%s] StartTask task_id=%s", ctx.sn, task_id)
        # TODO: trigger mission execution on hardware
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def stop_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        logger.info("[%s] StopTask task_id=%s", ctx.sn, task_id)
        # TODO: abort mission on hardware
        return EdgeResponse.ok(ctx.tid, ctx.sn)


# ---------------------------------------------------------------------------
# Telemetry loop (runs in parallel with the gRPC server)
# ---------------------------------------------------------------------------


async def telemetry_loop(publisher: TelemetryPublisher) -> None:
    """Pushes simulated telemetry to the platform every second."""
    while True:
        await publisher.publish_asset_telemetry(
            AssetTelemetry(
                id=ASSET_SN,
                latitude=47.5162,
                longitude=9.7765,
                absolute_altitude=420.0,
            )
        )
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    connector = ConnectorClient(host=PLATFORM_HOST, port=CONNECTOR_PORT, sn=ASSET_SN)
    publisher = TelemetryPublisher(host=PLATFORM_HOST, port=LIVE_DATA_PORT, sn=ASSET_SN)

    await connector.connect()
    await publisher.connect()

    adapter = MyDockAdapter(connector=connector, publisher=publisher)
    server = EdgeServer(adapter=adapter, port=EDGE_SERVICE_PORT)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve(), name="grpc-server")
        tg.create_task(telemetry_loop(publisher), name="telemetry")


if __name__ == "__main__":
    asyncio.run(main())

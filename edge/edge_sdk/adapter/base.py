"""
Abstract base class that every Edge Adapter must implement.

The SDK generates a gRPC server that implements EdgeAdapterService and
delegates every incoming RPC to the corresponding method on this class.
Users extend EdgeAdapter, implement the methods for their hardware, and
pass the instance to EdgeServer.

Only ``get_capabilities`` is required.  Every other method has a default
implementation that returns "not supported" — the gRPC servicer will
automatically respond with UNIMPLEMENTED for any method not overridden.

Streaming RPCs:
  - ManualControlInput  : client-streaming  → receives AsyncIterator[ManualControlInput]
  - GetDetections       : server-streaming  → must be an async generator yielding DetectionResponse

All other RPCs are simple request/response.

Minimal example (drone-only adapter, no dock operations)::

    class MyDroneAdapter(EdgeAdapter):
        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.AIRCRAFT)

        async def take_off(self, ctx, coordinates):
            await hardware.take_off(coordinates.latitude, coordinates.longitude)
            return EdgeResponse.ok(ctx.tid, ctx.sn)

        async def start_task(self, ctx, task_id):
            task = await self._connector.get_task(task_id)
            await hardware.upload_mission(task)
            return EdgeResponse.ok(ctx.tid, ctx.sn)

    server = EdgeServer(adapter=MyDroneAdapter(), port=50051)
    asyncio.run(server.serve())
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncIterator

from ..models.asset import Asset
from ..models.common import (
    AssetAirConditionerState,
    AssetType,
    Capabilities,
    Capability,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    Coordinates,
    CustomCommandRequest,
    CustomCommandResponse,
    DetectionResponse,
    EdgeResponse,
    LiveStreamStartRequest,
    LiveStreamStopRequest,
    ManualControlInput,
    ManualControlRequest,
    RequestContext,
    ReturnToHomeRequest,
)

# Maps Python method name → (RPC command name, human description)
_CAPABILITY_MAP: dict[str, tuple[str, str]] = {
    "take_off": ("TakeOff", "Launch drone"),
    "go_to": ("GoTo", "Fly to coordinates"),
    "return_to_home": ("ReturnToHome", "Return to home position"),
    "enter_manual_control": ("EnterManualControl", "Enter manual control mode"),
    "exit_manual_control": ("ExitManualControl", "Exit manual control mode"),
    "manual_control_input": ("ManualControlInput", "Send manual control inputs"),
    "look_at": ("LookAt", "Point gimbal at coordinates"),
    "take_photo": ("TakePhoto", "Capture a photo"),
    "enable_gimbal_tracking": ("EnableGimbalTracking", "Enable gimbal auto-tracking"),
    "get_detections": ("GetDetections", "Stream AI detections"),
    "open_cover": ("OpenCover", "Open dock cover"),
    "close_cover": ("CloseCover", "Close dock cover"),
    "start_charging": ("StartCharging", "Start charging drone"),
    "stop_charging": ("StopCharging", "Stop charging drone"),
    "reboot_asset": ("RebootAsset", "Reboot main asset"),
    "boot_up_sub_asset": ("BootUpSubAsset", "Power on sub-asset"),
    "boot_down_sub_asset": ("BootDownSubAsset", "Power off sub-asset"),
    "register_asset": ("RegisterAsset", "Register asset on platform"),
    "deregister_asset": ("DeRegisterAsset", "Deregister asset from platform"),
    "enter_or_close_remote_debug_mode": (
        "EnterOrCloseRemoteDebugMode",
        "Toggle remote debug mode",
    ),
    "change_ac_mode": ("ChangeAcMode", "Change air conditioner mode"),
    "start_live_stream": ("StartLiveStream", "Start video stream"),
    "stop_live_stream": ("StopLiveStream", "Stop video stream"),
    "change_lens": ("ChangeLens", "Switch camera lens"),
    "change_zoom": ("ChangeZoom", "Change camera zoom"),
    "capture_photo": ("CapturePhoto", "Capture photo to storage"),
    "start_recording": ("StartRecording", "Start video recording"),
    "stop_recording": ("StopRecording", "Stop video recording"),
    "prepare_task": ("PrepareTask", "Prepare task for execution"),
    "start_task": ("StartTask", "Start task execution"),
    "stop_task": ("StopTask", "Stop task execution"),
    "send_custom_command": ("SendCustomCommand", "Send a vendor-specific custom command"),
}


class EdgeAdapter(ABC):
    """
    Base class for all ZQNT Edge Adapter implementations.

    Only :meth:`get_capabilities` is required.  All other methods are optional
    — unimplemented methods are automatically reported as UNIMPLEMENTED by the
    gRPC server and excluded from the capabilities reported to the platform.

    Use :meth:`_auto_capabilities` inside your ``get_capabilities`` override
    to generate the capabilities list automatically from what you have
    implemented::

        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.DOCK)
    """

    # ------------------------------------------------------------------
    # Capability management  (required)
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_capabilities(self, sn: str, asset_id: str | None) -> Capabilities:
        """Return the current capabilities of the asset identified by *sn*.

        Tip: delegate to :meth:`_auto_capabilities` to avoid maintaining
        the list manually::

            return self._auto_capabilities(sn, AssetType.DOCK)
        """
        ...

    def _auto_capabilities(self, sn: str, asset_type: AssetType) -> Capabilities:
        """
        Build a :class:`Capabilities` object by inspecting which methods this
        adapter has overridden.  Any method that has been overridden is marked
        ``available=True``; everything else is ``available=False``.
        """
        caps = [
            Capability(
                command=command,
                description=description,
                available=self._is_overridden(method_name),
            )
            for method_name, (command, description) in _CAPABILITY_MAP.items()
        ]
        return Capabilities(
            asset_sn=sn,
            asset_type=asset_type,
            capabilities=caps,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _is_overridden(self, method_name: str) -> bool:
        """Return True if *method_name* has been overridden in a subclass."""
        base = getattr(EdgeAdapter, method_name, None)
        impl = getattr(type(self), method_name, None)
        return base is not impl

    # ------------------------------------------------------------------
    # Flight control
    # ------------------------------------------------------------------

    async def take_off(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Command the drone to take off to *coordinates*."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def go_to(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Command the drone to fly to *coordinates*."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def return_to_home(self, ctx: RequestContext, request: ReturnToHomeRequest) -> EdgeResponse:
        """Command the drone to return to home."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------

    async def enter_manual_control(self, ctx: RequestContext, request: ManualControlRequest) -> EdgeResponse:
        """Establish a manual-control session for the given client."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def exit_manual_control(self, ctx: RequestContext, request: ManualControlRequest) -> EdgeResponse:
        """Terminate the manual-control session."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def manual_control_input(
        self,
        ctx: RequestContext,
        inputs: AsyncIterator[ManualControlInput],
    ) -> EdgeResponse:
        """
        Receive a stream of joystick/stick inputs.

        *inputs* is an async iterator; iterate it to consume each frame::

            async for inp in inputs:
                apply_to_drone(inp.roll, inp.pitch, inp.yaw, inp.throttle)
        """
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

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
        """Point the gimbal/camera at *coordinates*."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def take_photo(self, ctx: RequestContext) -> EdgeResponse:
        """Trigger a single photo capture."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def enable_gimbal_tracking(self, ctx: RequestContext, enabled: bool) -> EdgeResponse:
        """Enable or disable gimbal auto-tracking."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Detection  (server-streaming – optional)
    # ------------------------------------------------------------------

    async def get_detections(self, ctx: RequestContext, stream_url: str | None) -> AsyncIterator[DetectionResponse]:
        """
        Stream detection results back to the caller.

        Override this method and implement it as an ``async def`` generator
        that ``yield``s :class:`DetectionResponse` objects::

            async def get_detections(self, ctx, stream_url):
                while True:
                    results = await my_ai.detect(stream_url)
                    yield DetectionResponse(detections=results)
        """
        raise NotImplementedError
        if False:  # pragma: no cover
            yield  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Dock operations
    # ------------------------------------------------------------------

    async def open_cover(self, ctx: RequestContext) -> EdgeResponse:
        """Open the dock cover."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def close_cover(self, ctx: RequestContext, force: bool | None) -> EdgeResponse:
        """Close the dock cover. *force=True* maps to ForceCloseCover."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def start_charging(self, ctx: RequestContext) -> EdgeResponse:
        """Start charging the drone inside the dock."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def stop_charging(self, ctx: RequestContext) -> EdgeResponse:
        """Stop charging the drone inside the dock."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    async def reboot_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Reboot the main asset (dock)."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def boot_up_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Power on the sub-asset (drone)."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def boot_down_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Power off the sub-asset (drone)."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def register_asset(self, ctx: RequestContext, asset: Asset) -> EdgeResponse:
        """Notify the adapter that an asset has been registered on the platform."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def deregister_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Notify the adapter that the asset has been removed from the platform."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Debug & maintenance
    # ------------------------------------------------------------------

    async def enter_or_close_remote_debug_mode(self, ctx: RequestContext, enabled: bool) -> EdgeResponse:
        """Toggle remote debug mode. Override if your hardware supports it."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def change_ac_mode(self, ctx: RequestContext, mode: AssetAirConditionerState) -> EdgeResponse:
        """Change the dock air-conditioner mode. Override if your hardware supports it."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Live stream
    # ------------------------------------------------------------------

    async def start_live_stream(self, ctx: RequestContext, request: LiveStreamStartRequest) -> EdgeResponse:
        """Start a live video stream."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def stop_live_stream(self, ctx: RequestContext, request: LiveStreamStopRequest) -> EdgeResponse:
        """Stop the live stream identified by ``request.video_id``."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def change_lens(self, ctx: RequestContext, request: ChangeCameraLensRequest) -> EdgeResponse:
        """Switch the active camera lens."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def change_zoom(self, ctx: RequestContext, request: ChangeCameraZoomRequest) -> EdgeResponse:
        """Change the camera zoom level."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def capture_photo(self, ctx: RequestContext) -> EdgeResponse:
        """Capture a photo and save it to storage."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def start_recording(self, ctx: RequestContext) -> EdgeResponse:
        """Start video recording."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def stop_recording(self, ctx: RequestContext) -> EdgeResponse:
        """Stop video recording."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def prepare_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Prepare a task for execution (pre-flight checks, upload waypoints, etc.)."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Start executing the previously prepared task."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def stop_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Stop / abort the currently running task."""
        return EdgeResponse.not_supported(ctx.tid, ctx.sn)

    async def send_custom_command(self, ctx: RequestContext, request: CustomCommandRequest) -> CustomCommandResponse:
        """Send a vendor-specific custom command.

        Override this method to handle arbitrary commands identified by
        ``request.command_type``.  Parameters are passed as a plain dict in
        ``request.params``.  Return a :class:`CustomCommandResponse` with an
        optional ``result`` dict to send structured data back to the caller.
        """
        return CustomCommandResponse.not_supported(ctx.tid, ctx.sn, request.command_type)

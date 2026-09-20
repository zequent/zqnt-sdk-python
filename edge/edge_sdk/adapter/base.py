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
from typing import AsyncIterator, Awaitable, Callable

from ..models.asset import Asset
from ..models.common import (
    AssetAirConditionerState,
    AssetType,
    Capabilities,
    Capability,
    CapabilityState,
    CapabilityTarget,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    Coordinates,
    CustomCommandRequest,
    CustomCommandResponse,
    DetectionResponse,
    EdgeResponse,
    ErrorCode,
    ErrorMessage,
    LiveStreamStartRequest,
    LiveStreamStopRequest,
    LiveStreamType,
    ManualControlInput,
    ManualControlRequest,
    RequestContext,
    ReturnToHomeRequest,
)
from .commands import CATALOG, CommandHandler, RegisteredCommand, spec_for

# Maps Python method name → the dotted command id that method implements.
#
# These are the platform's own ids (see edge_sdk.adapter.commands.CATALOG): the same strings
# core's EdgeExecutionNodeDispatcher routes and ExecutionSafetyGate checks an asset for. Before
# 2.0 this map held PascalCase RPC names ("TakeOff"), which nothing on the platform side ever
# matched -- an adapter built on this SDK advertised capabilities no Application could reference.
_METHOD_COMMANDS: dict[str, str] = {
    "take_off": "flight.takeoff",
    "go_to": "navigation.go_to",
    "return_to_home": "flight.return_to_home",
    "enter_manual_control": "flight.manual.enter",
    "exit_manual_control": "flight.manual.exit",
    "manual_control_input": "flight.manual.input",
    "look_at": "gimbal.look_at",
    "enable_gimbal_tracking": "gimbal.tracking",
    "take_photo": "camera.take_photo",
    "capture_photo": "camera.capture_photo",
    "change_lens": "camera.change_lens",
    "change_zoom": "camera.change_zoom",
    "start_recording": "camera.start_recording",
    "stop_recording": "camera.stop_recording",
    "start_live_stream": "stream.start",
    "stop_live_stream": "stream.stop",
    "get_detections": "detections.stream",
    "open_cover": "dock.open_cover",
    "close_cover": "dock.close_cover",
    "start_charging": "dock.start_charging",
    "stop_charging": "dock.stop_charging",
    "reboot_asset": "asset.reboot",
    "boot_up_sub_asset": "asset.boot_sub_asset",
    "boot_down_sub_asset": "asset.boot_sub_asset",
    "enter_or_close_remote_debug_mode": "asset.remote_debug",
    "change_ac_mode": "asset.change_ac_mode",
    # register_asset/deregister_asset are deliberately absent: they are lifecycle callbacks the
    # platform makes when an asset is added or removed, not commands anyone invokes from a
    # capability graph. Advertising them would put two un-runnable blocks in the console's command
    # palette. edge-dji, the reference adapter, does not advertise them either.
    "prepare_task": "mission.prepare",
    "start_task": "mission.start",
    "stop_task": "mission.stop",
}

# Streaming RPCs are advertised like any other capability but are never dispatched through
# send_custom_command -- collapsing them into the command envelope would cost a round trip per
# frame, which is why the 2.0 plan deliberately leaves ManualControlInput/GetDetections typed.
_STREAMING_COMMANDS = frozenset({"flight.manual.input", "detections.stream"})


def _coordinate_params(coordinates: Coordinates) -> dict:
    """Params shape shared by the coordinate-taking commands, matching their catalog schema."""
    return {
        "latitude": coordinates.latitude,
        "longitude": coordinates.longitude,
        "altitude": coordinates.altitude,
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

    def register_command(
        self,
        command_id: str,
        handler: CommandHandler | None = None,
        *,
        description: str | None = None,
        display_name: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        schema_version: str | None = None,
        target: CapabilityTarget | None = None,
        skill_id: str | None = None,
        state: CapabilityState = CapabilityState.AVAILABLE,
        unavailable_reason: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """
        Declare one command this adapter can run.

        A single registration produces BOTH halves of the contract: the command appears in
        :meth:`_auto_capabilities` (so the platform can discover it, render a parameter form
        from ``input_schema`` and let the safety gate verify the asset advertises it) and, when
        *handler* is given, :meth:`send_custom_command` dispatches to it. That is the whole
        point -- advertising and executing can no longer drift apart, because they are no longer
        two lists maintained by hand.

        ``description``/``input_schema``/``output_schema``/``schema_version`` default to the
        platform catalog entry for *command_id* when there is one, so registering a well-known
        command is a one-liner::

            self.register_command("mission.waypoint.execute", self._fly_mission)

        A hardware-specific command supplies its own contract and belongs under a ``vendor.``
        prefix, which the catalog deliberately leaves free::

            self.register_command(
                "vendor.acme.spray",
                self._spray,
                description="Run the spray boom for N seconds",
                input_schema=schema({"seconds": {"type": "number"}}, ["seconds"]),
            )

        Registering the same id twice replaces the earlier entry, so an adapter can re-register
        with a narrower state (for example TEMPORARILY_UNAVAILABLE while a payload is detached).

        ``display_name``/``skill_id`` likewise default to the catalog entry. A ``vendor.*`` command
        has no catalog entry, so pass ``skill_id`` to file it alongside the commands it belongs
        with -- otherwise the console groups it under the literal segment ``vendor``, together with
        every unrelated vendor command in the fleet.
        """
        spec = spec_for(command_id)
        self._commands[command_id] = RegisteredCommand(
            command_id=command_id,
            description=description if description is not None else (spec.description if spec else ""),
            display_name=display_name if display_name is not None else (spec.display_name if spec else None),
            handler=handler,
            input_schema=input_schema if input_schema is not None else (spec.input_schema if spec else None),
            output_schema=output_schema if output_schema is not None else (spec.output_schema if spec else None),
            schema_version=schema_version if schema_version is not None else (spec.schema_version if spec else None),
            target=target,
            skill_id=skill_id if skill_id is not None else (spec.skill_id if spec else None),
            state=state,
            unavailable_reason=unavailable_reason,
            metadata=dict(metadata or {}),
        )

    @property
    def _commands(self) -> dict[str, RegisteredCommand]:
        """Commands registered through :meth:`register_command`, keyed by command id."""
        registry = self.__dict__.get("_registered_commands")
        if registry is None:
            registry = {}
            self.__dict__["_registered_commands"] = registry
        return registry

    def registered_commands(self) -> dict[str, RegisteredCommand]:
        """Read-only view of what this adapter has registered (useful in tests)."""
        return dict(self._commands)

    def _auto_capabilities(self, sn: str, asset_type: AssetType) -> Capabilities:
        """
        Build a :class:`Capabilities` snapshot from what this adapter actually implements.

        Two sources, merged: the platform catalog (:data:`~edge_sdk.adapter.commands.CATALOG`),
        with each command marked available when the subclass overrides the typed method that
        implements it (mapped through :data:`_METHOD_COMMANDS`), and everything passed to
        :meth:`register_command`. A registration wins over the derived entry for the same id, so
        an adapter can attach a richer contract to a command it also implements typed.

        Commands that are neither overridden nor registered are reported UNSUPPORTED rather than
        omitted, which is what lets the platform tell "this asset cannot do that" apart from
        "this asset has not reported yet".
        """
        derived: dict[str, Capability] = {}
        # Walk the whole catalog, not only the ids that have a typed method. A catalog command
        # with no typed equivalent (mission.waypoint.execute, mission.pause, mission.resume) used
        # to be missing from the snapshot altogether unless the adapter registered it, so the
        # platform could not tell "this asset cannot fly a waypoint mission" from "this asset has
        # not reported yet" -- the exact distinction this method exists to make.
        for command_id, spec in CATALOG.items():
            # boot_up_sub_asset/boot_down_sub_asset share one command id: available if either is.
            overridden = any(
                self._is_overridden(method_name)
                for method_name, mapped in _METHOD_COMMANDS.items()
                if mapped == command_id
            )
            derived[command_id] = Capability(
                command_id=command_id,
                description=spec.description,
                display_name=spec.display_name,
                state=CapabilityState.AVAILABLE if overridden else CapabilityState.UNSUPPORTED,
                input_schema=spec.input_schema,
                output_schema=spec.output_schema,
                schema_version=spec.schema_version,
                skill_id=spec.skill_id,
                target=CapabilityTarget(),
            )

        for command_id, registered in self._commands.items():
            derived[command_id] = Capability(
                command_id=command_id,
                description=registered.description,
                display_name=registered.display_name,
                state=registered.state,
                unavailable_reason=registered.unavailable_reason,
                metadata=dict(registered.metadata),
                input_schema=registered.input_schema,
                output_schema=registered.output_schema,
                target=registered.target or CapabilityTarget(),
                schema_version=registered.schema_version,
                skill_id=registered.skill_id,
            )

        return Capabilities(
            asset_sn=sn,
            asset_type=asset_type,
            capabilities=list(derived.values()),
            timestamp=datetime.now(tz=timezone.utc),
        )

    async def _dispatch_registered(
        self, ctx: RequestContext, command_id: str, params: dict
    ) -> CustomCommandResponse | None:
        """Run the handler registered for *command_id*, or return None if there is none."""
        registered = self._commands.get(command_id)
        if registered is None or registered.handler is None:
            return None
        return await registered.handler(ctx, params)

    async def _dispatch_typed(self, ctx: RequestContext, command_id: str, params: dict) -> CustomCommandResponse | None:
        """
        Run a built-in command id against the typed method that implements it.

        The mirror image of :meth:`_delegate`, and the reason both exist: an adapter may declare a
        command either way round. A new adapter registers handlers and the typed RPCs delegate into
        them; an adapter that already implements the typed methods (which is every adapter that
        predates the registry) gets its advertised ids routed the other way, here. Either way the
        rule holds -- everything advertised is executable by id, which is what lets core's
        hand-maintained dotted-id-to-typed-stub table eventually go away.

        Returns ``None`` when *command_id* is not a built-in, so the caller keeps routing.
        """
        builder = _TYPED_DISPATCH.get(command_id)
        if builder is None:
            return None
        response = await builder(self, ctx, params)
        if response.success:
            return CustomCommandResponse.ok(
                ctx.tid, ctx.sn, command_id, external_execution_id=response.external_execution_id
            )
        return CustomCommandResponse.fail(
            ctx.tid,
            ctx.sn,
            command_id,
            response.error or ErrorMessage(message=f"{command_id} failed", code=ErrorCode.ASSET_ERROR),
        )

    async def _delegate(self, ctx: RequestContext, command_id: str, params: dict) -> EdgeResponse:
        """
        Default body for a typed RPC: run the registered handler for the equivalent command id.

        This is what keeps the two surfaces in step while the typed RPCs still exist. An adapter
        that registers ``flight.takeoff`` serves both ``TakeOff`` and
        ``SendCustomCommand{command_id: "flight.takeoff"}`` without writing either twice, so
        adapters can convert one command at a time and the typed RPCs can later be deleted as a
        pure proto change rather than a flag day.
        """
        response = await self._dispatch_registered(ctx, command_id, params)
        if response is None:
            return EdgeResponse.not_supported(ctx.tid, ctx.sn)
        if not response.success:
            return EdgeResponse.fail(
                ctx.tid,
                ctx.sn,
                response.error or ErrorMessage(message=f"{command_id} failed", code=ErrorCode.ASSET_ERROR),
            )
        return EdgeResponse.ok(ctx.tid, ctx.sn, external_execution_id=response.external_execution_id)

    def _is_overridden(self, method_name: str) -> bool:
        """Return True if *method_name* has been overridden in a subclass."""
        base = getattr(EdgeAdapter, method_name, None)
        impl = getattr(type(self), method_name, None)
        return base is not impl

    def supports_method(self, method_name: str) -> bool:
        """
        Return True if this adapter can actually serve the RPC backed by *method_name*.

        This is what the gRPC servicer gates on, and it is deliberately wider than
        :meth:`_is_overridden`. A command declared through :meth:`register_command` is served by
        the inherited method body (which delegates to the registered handler), so the method is
        never overridden and an override check alone reports it unimplemented -- the adapter then
        advertises a command in ``get_capabilities`` that its own server refuses with
        UNIMPLEMENTED. That split is the exact drift the registry exists to remove, so the gate
        has to see registrations too.

        ``send_custom_command`` is always supported: its inherited body routes registered handlers
        *and* built-in ids onto the typed methods (:meth:`_dispatch_typed`), and for an id it
        cannot place it answers with a not-supported *response* rather than aborting the call,
        which is what mission-autonomy's dispatcher reads (``response.getHasErrors()``).
        """
        if method_name == "send_custom_command":
            return True
        if self._is_overridden(method_name):
            return True
        command_id = _METHOD_COMMANDS.get(method_name)
        if command_id is None:
            return False
        registered = self._commands.get(command_id)
        return registered is not None and registered.dispatchable

    # ------------------------------------------------------------------
    # Flight control
    # ------------------------------------------------------------------

    async def take_off(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Command the drone to take off to *coordinates*."""
        return await self._delegate(ctx, "flight.takeoff", _coordinate_params(coordinates))

    async def go_to(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Command the drone to fly to *coordinates*."""
        return await self._delegate(ctx, "navigation.go_to", _coordinate_params(coordinates))

    async def return_to_home(self, ctx: RequestContext, request: ReturnToHomeRequest) -> EdgeResponse:
        """Command the drone to return to home."""
        return await self._delegate(ctx, "flight.return_to_home", {"altitude": request.altitude})

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------

    async def enter_manual_control(self, ctx: RequestContext, request: ManualControlRequest) -> EdgeResponse:
        """Establish a manual-control session for the given client."""
        return await self._delegate(ctx, "flight.manual.enter", {})

    async def exit_manual_control(self, ctx: RequestContext, request: ManualControlRequest) -> EdgeResponse:
        """Terminate the manual-control session."""
        return await self._delegate(ctx, "flight.manual.exit", {})

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
        return await self._delegate(
            ctx,
            "gimbal.look_at",
            {
                **_coordinate_params(coordinates),
                "payloadIndex": payload_index,
                "locked": locked,
            },
        )

    async def take_photo(self, ctx: RequestContext) -> EdgeResponse:
        """Trigger a single photo capture."""
        return await self._delegate(ctx, "camera.take_photo", {})

    async def enable_gimbal_tracking(self, ctx: RequestContext, enabled: bool) -> EdgeResponse:
        """Enable or disable gimbal auto-tracking."""
        return await self._delegate(ctx, "gimbal.tracking", {"enabled": enabled})

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
        return await self._delegate(ctx, "dock.open_cover", {})

    async def close_cover(self, ctx: RequestContext, force: bool | None) -> EdgeResponse:
        """Close the dock cover. *force=True* maps to ForceCloseCover."""
        return await self._delegate(ctx, "dock.close_cover", {"force": bool(force)})

    async def start_charging(self, ctx: RequestContext) -> EdgeResponse:
        """Start charging the drone inside the dock."""
        return await self._delegate(ctx, "dock.start_charging", {})

    async def stop_charging(self, ctx: RequestContext) -> EdgeResponse:
        """Stop charging the drone inside the dock."""
        return await self._delegate(ctx, "dock.stop_charging", {})

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    async def reboot_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Reboot the main asset (dock)."""
        return await self._delegate(ctx, "asset.reboot", {})

    async def boot_up_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Power on the sub-asset (drone)."""
        return await self._delegate(ctx, "asset.boot_sub_asset", {"enabled": True})

    async def boot_down_sub_asset(self, ctx: RequestContext) -> EdgeResponse:
        """Power off the sub-asset (drone)."""
        return await self._delegate(ctx, "asset.boot_sub_asset", {"enabled": False})

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
        return await self._delegate(ctx, "asset.remote_debug", {"enabled": enabled})

    async def change_ac_mode(self, ctx: RequestContext, mode: AssetAirConditionerState) -> EdgeResponse:
        """Change the dock air-conditioner mode. Override if your hardware supports it."""
        return await self._delegate(ctx, "asset.change_ac_mode", {"mode": mode.name})

    # ------------------------------------------------------------------
    # Live stream
    # ------------------------------------------------------------------

    async def start_live_stream(self, ctx: RequestContext, request: LiveStreamStartRequest) -> EdgeResponse:
        """Start a live video stream."""
        return await self._delegate(
            ctx, "stream.start", {"videoId": request.video_id, "streamServer": request.stream_server}
        )

    async def stop_live_stream(self, ctx: RequestContext, request: LiveStreamStopRequest) -> EdgeResponse:
        """Stop the live stream identified by ``request.video_id``."""
        return await self._delegate(ctx, "stream.stop", {"videoId": request.video_id})

    async def change_lens(self, ctx: RequestContext, request: ChangeCameraLensRequest) -> EdgeResponse:
        """Switch the active camera lens."""
        return await self._delegate(ctx, "camera.change_lens", {"lens": request.lens})

    async def change_zoom(self, ctx: RequestContext, request: ChangeCameraZoomRequest) -> EdgeResponse:
        """Change the camera zoom level."""
        return await self._delegate(ctx, "camera.change_zoom", {"lens": request.lens, "zoom": request.zoom})

    async def capture_photo(self, ctx: RequestContext) -> EdgeResponse:
        """Capture a photo and save it to storage."""
        return await self._delegate(ctx, "camera.capture_photo", {})

    async def start_recording(self, ctx: RequestContext) -> EdgeResponse:
        """Start video recording."""
        return await self._delegate(ctx, "camera.start_recording", {})

    async def stop_recording(self, ctx: RequestContext) -> EdgeResponse:
        """Stop video recording."""
        return await self._delegate(ctx, "camera.stop_recording", {})

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def prepare_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Prepare a task for execution (pre-flight checks, upload waypoints, etc.)."""
        return await self._delegate(ctx, "mission.prepare", {"taskId": task_id})

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Start executing the previously prepared task."""
        return await self._delegate(ctx, "mission.start", {"taskId": task_id})

    async def stop_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Stop / abort the currently running task."""
        return await self._delegate(ctx, "mission.stop", {"taskId": task_id})

    async def send_custom_command(self, ctx: RequestContext, request: CustomCommandRequest) -> CustomCommandResponse:
        """Run the command identified by ``request.command_type``.

        The default implementation dispatches to whatever :meth:`register_command` has been
        given a handler for, so most adapters never override this method — they register their
        commands and get advertisement and dispatch from the one declaration.

        Overriding is still supported for an adapter that routes commands dynamically (a
        protocol bridge forwarding an arbitrary id downstream, say). Call
        ``await super().send_custom_command(ctx, request)`` first to let registered handlers win,
        then fall back to your own routing.
        """
        params = request.params or {}
        response = await self._dispatch_registered(ctx, request.command_type, params)
        if response is not None:
            return response
        typed = await self._dispatch_typed(ctx, request.command_type, params)
        if typed is not None:
            return typed
        return CustomCommandResponse.not_supported(ctx.tid, ctx.sn, request.command_type)


# Built-in command id → how to call the typed method that implements it. Params follow the same
# JSON Schemas the catalog publishes for these commands, so one id means one thing across the
# Python and Java SDKs (see edge-java-sdk's BuiltInCommandDispatch, which does this in Java).
# The two streaming commands are absent on purpose: routing a frame per round trip would be a real
# performance regression, so ManualControlInput/GetDetections stay typed-only.
def _num(params: dict, key: str, default: float | None = None) -> float | None:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _coords(params: dict) -> Coordinates:
    # An absent component becomes NaN, not 0.0 — the platform's own convention for "not provided,
    # use the current position or your default" (see mission-autonomy's
    # EdgeExecutionNodeDispatcher#number). 0.0 would be Null Island, a real place off the coast of
    # Ghana, and adapters cannot tell it apart from an omitted value.
    missing = float("nan")
    return Coordinates(
        latitude=_num(params, "latitude", missing),
        longitude=_num(params, "longitude", missing),
        altitude=_num(params, "altitude", missing),
    )


def _ac_mode(params: dict) -> AssetAirConditionerState:
    mode = params.get("mode")
    if isinstance(mode, str):
        try:
            return AssetAirConditionerState[mode.upper()]
        except KeyError:
            return AssetAirConditionerState.IDLE
    return AssetAirConditionerState(int(mode)) if isinstance(mode, int) else AssetAirConditionerState.IDLE


_TYPED_DISPATCH: dict[str, Callable[["EdgeAdapter", RequestContext, dict], Awaitable[EdgeResponse]]] = {
    "flight.takeoff": lambda a, ctx, p: a.take_off(ctx, _coords(p)),
    "navigation.go_to": lambda a, ctx, p: a.go_to(ctx, _coords(p)),
    "flight.return_to_home": lambda a, ctx, p: a.return_to_home(ctx, ReturnToHomeRequest(altitude=_num(p, "altitude"))),
    "flight.manual.enter": lambda a, ctx, p: a.enter_manual_control(ctx, _manual_request(p)),
    "flight.manual.exit": lambda a, ctx, p: a.exit_manual_control(ctx, _manual_request(p)),
    "gimbal.look_at": lambda a, ctx, p: a.look_at(ctx, _coords(p), p.get("payloadIndex"), p.get("locked")),
    "gimbal.tracking": lambda a, ctx, p: a.enable_gimbal_tracking(ctx, bool(p.get("enabled"))),
    "camera.take_photo": lambda a, ctx, p: a.take_photo(ctx),
    "camera.capture_photo": lambda a, ctx, p: a.capture_photo(ctx),
    "camera.change_lens": lambda a, ctx, p: a.change_lens(ctx, ChangeCameraLensRequest(lens=p.get("lens"))),
    "camera.change_zoom": lambda a, ctx, p: a.change_zoom(
        ctx, ChangeCameraZoomRequest(lens=p.get("lens"), zoom=int(_num(p, "zoom") or 0))
    ),
    "camera.start_recording": lambda a, ctx, p: a.start_recording(ctx),
    "camera.stop_recording": lambda a, ctx, p: a.stop_recording(ctx),
    "stream.start": lambda a, ctx, p: a.start_live_stream(ctx, _live_stream_start(p)),
    "stream.stop": lambda a, ctx, p: a.stop_live_stream(ctx, LiveStreamStopRequest(video_id=p.get("videoId", ""))),
    "dock.open_cover": lambda a, ctx, p: a.open_cover(ctx),
    "dock.close_cover": lambda a, ctx, p: a.close_cover(ctx, bool(p.get("force"))),
    "dock.start_charging": lambda a, ctx, p: a.start_charging(ctx),
    "dock.stop_charging": lambda a, ctx, p: a.stop_charging(ctx),
    "asset.reboot": lambda a, ctx, p: a.reboot_asset(ctx),
    # One id, two typed methods — the params decide which, exactly as the published schema says.
    "asset.boot_sub_asset": lambda a, ctx, p: (
        a.boot_up_sub_asset(ctx) if p.get("enabled") else a.boot_down_sub_asset(ctx)
    ),
    "asset.remote_debug": lambda a, ctx, p: a.enter_or_close_remote_debug_mode(ctx, bool(p.get("enabled"))),
    "asset.change_ac_mode": lambda a, ctx, p: a.change_ac_mode(ctx, _ac_mode(p)),
    "mission.prepare": lambda a, ctx, p: a.prepare_task(ctx, str(p.get("taskId", ""))),
    "mission.start": lambda a, ctx, p: a.start_task(ctx, str(p.get("taskId", ""))),
    "mission.stop": lambda a, ctx, p: a.stop_task(ctx, str(p.get("taskId", ""))),
}


def _manual_request(params: dict) -> ManualControlRequest:
    return ManualControlRequest(
        client_id=str(params.get("clientId", "")),
        user_id=str(params.get("userId", "")),
        session_id=str(params.get("sessionId", "")),
        reason=params.get("reason"),
    )


def _live_stream_start(params: dict) -> LiveStreamStartRequest:
    return LiveStreamStartRequest(
        video_id=str(params.get("videoId", "")),
        stream_server=str(params.get("streamServer", "")),
        stream_type=LiveStreamType.RTMP,
        asset_type=AssetType.AIRCRAFT,
    )

"""
The platform's dotted command-id catalog, and the per-adapter command registry that
:class:`~edge_sdk.adapter.base.EdgeAdapter` builds its capabilities from.

Why this exists
---------------
Capability *advertisement* and command *execution* used to be derived from two unrelated
places: ``get_capabilities`` listed whichever typed SDK methods a subclass had overridden,
while ``send_custom_command`` dispatched on hand-written string comparisons. Nothing kept the
two in step, so an adapter could advertise a command it rejects (edge-dji advertised
``flight.takeoff`` but answered only mission/property commands) or answer one it never
advertises (this SDK's MAVLink adapter accepted ``mission.waypoint.execute`` while
``_auto_capabilities`` had no way to mention it). Both are the same bug, and both stop being
possible once one registration produces both the advertisement and the dispatch entry.

The catalog below is the vendor-neutral half of that: the ids the platform itself knows how to
route (see core's ``EdgeExecutionNodeDispatcher`` and ``ExecutionSafetyGate.COMMAND_ALIASES``),
with the same JSON Schemas edge-dji publishes for them so a command means the same thing
whichever adapter answers it. Anything hardware-specific belongs under a ``vendor.*`` id and is
registered by the adapter itself, never added here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..models.common import (
    CapabilityState,
    CapabilityTarget,
    CustomCommandResponse,
    RequestContext,
)

# A handler takes the calling context and the command's params, and returns the same
# CustomCommandResponse an adapter would have returned from send_custom_command.
CommandHandler = Callable[[RequestContext, dict], Awaitable[CustomCommandResponse]]

_NUMBER: dict[str, Any] = {"type": "number"}
_STRING: dict[str, Any] = {"type": "string", "minLength": 1}
_BOOL: dict[str, Any] = {"type": "boolean"}


def schema(properties: dict[str, Any], required: list[str] | None = None, *, additional: bool = False) -> dict:
    """Build the JSON Schema shape the platform expects for ``input_schema``/``output_schema``."""
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required or []),
        "additionalProperties": additional,
    }


_COORDINATE_PROPERTIES = {"latitude": _NUMBER, "longitude": _NUMBER, "altitude": _NUMBER}

# Mirrors edge-dji's waypointMissionSchema: params deserialize straight into the platform's
# WaypointTaskConfig, so only the required shape is pinned and the optional flight-behaviour
# fields (globalSpeed, rthMode, ...) ride along under additionalProperties.
_WAYPOINT_SCHEMA = schema(
    {
        "waypoints": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "latitude": _NUMBER,
                    "longitude": _NUMBER,
                    "altitude": _NUMBER,
                    "speed": _NUMBER,
                    "flyThrough": _BOOL,
                    "wpOrder": {"type": "integer"},
                    "gimbalPitch": _NUMBER,
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": True,
            },
        }
    },
    ["waypoints"],
    additional=True,
)


@dataclass(frozen=True)
class CommandSpec:
    """One entry in the vendor-neutral catalog."""

    command_id: str
    description: str
    input_schema: dict | None = None
    output_schema: dict | None = None
    schema_version: str | None = None
    skill_id: str | None = None


def _spec(command_id: str, description: str, input_schema: dict | None = None, **kwargs: Any) -> CommandSpec:
    return CommandSpec(command_id, description, input_schema, **kwargs)


# --------------------------------------------------------------------------------------------
# The catalog. Ids and schemas are kept identical to edge-dji's, which is the reference adapter.
# --------------------------------------------------------------------------------------------
CATALOG: dict[str, CommandSpec] = {
    spec.command_id: spec
    for spec in (
        # Flight
        _spec("flight.takeoff", "Take off to a target point", schema(_COORDINATE_PROPERTIES)),
        _spec("flight.return_to_home", "Return the aircraft to its home point", schema({"altitude": _NUMBER})),
        _spec("flight.manual.enter", "Enter manual control", schema({})),
        _spec("flight.manual.exit", "Exit manual control", schema({})),
        _spec(
            "flight.manual.input",
            "Send manual control input",
            schema(
                {
                    "roll": _NUMBER,
                    "pitch": _NUMBER,
                    "yaw": _NUMBER,
                    "throttle": _NUMBER,
                    "gimbalPitch": _NUMBER,
                },
                ["roll", "pitch", "yaw", "throttle"],
            ),
        ),
        # Navigation
        _spec(
            "navigation.go_to",
            "Fly to a target coordinate",
            schema(_COORDINATE_PROPERTIES, ["latitude", "longitude"]),
        ),
        # Gimbal
        _spec(
            "gimbal.look_at",
            "Point the gimbal at a coordinate",
            schema(
                {**_COORDINATE_PROPERTIES, "payloadIndex": _STRING, "locked": _BOOL},
                ["latitude", "longitude"],
            ),
        ),
        _spec("gimbal.tracking", "Enable or disable gimbal tracking", schema({"enabled": _BOOL}, ["enabled"])),
        # Camera
        _spec("camera.take_photo", "Take a photo", schema({})),
        _spec("camera.capture_photo", "Capture a photo and save it to asset storage", schema({})),
        _spec("camera.change_lens", "Change the active camera lens", schema({"lens": _STRING}, ["lens"])),
        _spec(
            "camera.change_zoom",
            "Change camera zoom",
            schema({"lens": _STRING, "zoom": _NUMBER}, ["lens", "zoom"]),
        ),
        _spec("camera.start_recording", "Start video recording", schema({})),
        _spec("camera.stop_recording", "Stop video recording", schema({})),
        # Stream
        _spec(
            "stream.start",
            "Start the camera livestream",
            schema({"videoId": _STRING, "streamServer": _STRING}, ["videoId", "streamServer"]),
        ),
        _spec("stream.stop", "Stop the camera livestream", schema({"videoId": _STRING}, ["videoId"])),
        _spec(
            "stream.split_screen",
            "Enable or disable the camera split-screen view",
            schema({"enabled": _BOOL}, ["enabled"]),
        ),
        # Audio
        _spec("audio.play_tts", "Play a text-to-speech message", schema({"text": _STRING}, ["text"])),
        # Dock
        _spec("dock.open_cover", "Open the dock cover", schema({})),
        _spec("dock.close_cover", "Close the dock cover", schema({"force": _BOOL})),
        _spec("dock.start_charging", "Start aircraft charging", schema({})),
        _spec("dock.stop_charging", "Stop aircraft charging", schema({})),
        # Asset
        _spec("asset.reboot", "Reboot the asset", schema({})),
        _spec("asset.boot_sub_asset", "Power the sub-asset on or off", schema({"enabled": _BOOL}, ["enabled"])),
        _spec("asset.remote_debug", "Enable or disable remote debug mode", schema({"enabled": _BOOL}, ["enabled"])),
        _spec("asset.change_ac_mode", "Change air conditioning mode", schema({"mode": _STRING}, ["mode"])),
        # Mission
        _spec(
            "mission.waypoint.execute",
            "Build, upload and fly a waypoint mission",
            _WAYPOINT_SCHEMA,
            output_schema=schema({"task_id": _STRING}, ["task_id"]),
            schema_version="1",
        ),
        _spec("mission.pause", "Pause the running waypoint mission", schema({})),
        _spec("mission.resume", "Resume the paused waypoint mission", schema({})),
        _spec("mission.stop", "Stop the running mission or task", schema({"taskId": _STRING})),
        _spec("mission.prepare", "Prepare a task for execution", schema({"taskId": _STRING}, ["taskId"])),
        _spec("mission.start", "Start a prepared task", schema({"taskId": _STRING}, ["taskId"])),
        # Detections (server-streaming RPC; advertised so the catalog shows it, never dispatched
        # through ExecuteCommand -- see the plan's "deliberately NOT collapsing the streaming RPCs")
        _spec("detections.stream", "Stream AI detections", schema({})),
    )
}


def spec_for(command_id: str) -> CommandSpec | None:
    """Return the catalog entry for *command_id*, or ``None`` for a vendor-specific id."""
    return CATALOG.get(command_id)


@dataclass
class RegisteredCommand:
    """One command an adapter has declared: its contract and, optionally, how to run it."""

    command_id: str
    description: str = ""
    handler: CommandHandler | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    schema_version: str | None = None
    target: CapabilityTarget | None = None
    skill_id: str | None = None
    state: CapabilityState = CapabilityState.AVAILABLE
    unavailable_reason: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def dispatchable(self) -> bool:
        return self.handler is not None

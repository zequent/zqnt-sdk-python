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
    display_name: str | None = None


def _spec(
    command_id: str,
    display_name: str,
    description: str,
    input_schema: dict | None = None,
    *,
    skill_id: str | None = None,
    **kwargs: Any,
) -> CommandSpec:
    """
    Build a catalog entry.

    *skill_id* defaults to the id's leading namespace segment, which is the same fallback
    admin-console's ``SkillCatalogService#resolveSkillId`` applies when an adapter reports no
    skill. Sending it explicitly means the grouping is the adapter's stated contract rather than
    something the console infers from string shape, and lets a command sit in a skill its prefix
    does not name -- ``flight.manual.*`` belongs with manual control, not with takeoff/RTH.
    """
    return CommandSpec(
        command_id,
        description,
        input_schema,
        skill_id=skill_id if skill_id is not None else command_id.split(".", 1)[0],
        display_name=display_name,
        **kwargs,
    )


# --------------------------------------------------------------------------------------------
# The catalog. Ids and schemas are kept identical to edge-dji's, which is the reference adapter.
# --------------------------------------------------------------------------------------------
CATALOG: dict[str, CommandSpec] = {
    spec.command_id: spec
    for spec in (
        # Flight
        _spec("flight.takeoff", "Take off", "Take off to a target point", schema(_COORDINATE_PROPERTIES)),
        _spec(
            "flight.return_to_home",
            "Return to home",
            "Return the aircraft to its home point",
            schema({"altitude": _NUMBER}),
        ),
        # The manual-control trio is its own skill: entering/leaving a piloting session and
        # streaming sticks is one coherent operator workflow, and grouping it under "flight"
        # alongside takeoff would put a per-frame streaming command in a palette of one-shot
        # flight actions.
        _spec(
            "flight.manual.enter", "Enter manual control", "Enter manual control", schema({}), skill_id="manual_control"
        ),
        _spec(
            "flight.manual.exit", "Exit manual control", "Exit manual control", schema({}), skill_id="manual_control"
        ),
        _spec(
            "flight.manual.input",
            "Manual control input",
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
            skill_id="manual_control",
        ),
        # Navigation
        _spec(
            "navigation.go_to",
            "Go to coordinate",
            "Fly to a target coordinate",
            schema(_COORDINATE_PROPERTIES, ["latitude", "longitude"]),
        ),
        # Gimbal
        _spec(
            "gimbal.look_at",
            "Look at coordinate",
            "Point the gimbal at a coordinate",
            schema(
                {**_COORDINATE_PROPERTIES, "payloadIndex": _STRING, "locked": _BOOL},
                ["latitude", "longitude"],
            ),
        ),
        _spec(
            "gimbal.tracking",
            "Gimbal tracking",
            "Enable or disable gimbal tracking",
            schema({"enabled": _BOOL}, ["enabled"]),
        ),
        # Camera
        _spec("camera.take_photo", "Take photo", "Take a photo", schema({})),
        _spec(
            "camera.capture_photo",
            "Capture photo to storage",
            "Capture a photo and save it to asset storage",
            schema({}),
        ),
        _spec(
            "camera.change_lens",
            "Change lens",
            "Change the active camera lens",
            schema({"lens": _STRING}, ["lens"]),
        ),
        _spec(
            "camera.change_zoom",
            "Change zoom",
            "Change camera zoom",
            schema({"lens": _STRING, "zoom": _NUMBER}, ["lens", "zoom"]),
        ),
        _spec("camera.start_recording", "Start recording", "Start video recording", schema({})),
        _spec("camera.stop_recording", "Stop recording", "Stop video recording", schema({})),
        # Stream
        _spec(
            "stream.start",
            "Start livestream",
            "Start the camera livestream",
            schema({"videoId": _STRING, "streamServer": _STRING}, ["videoId", "streamServer"]),
            skill_id="streaming",
        ),
        _spec(
            "stream.stop",
            "Stop livestream",
            "Stop the camera livestream",
            schema({"videoId": _STRING}, ["videoId"]),
            skill_id="streaming",
        ),
        _spec(
            "stream.split_screen",
            "Split-screen view",
            "Enable or disable the camera split-screen view",
            schema({"enabled": _BOOL}, ["enabled"]),
            skill_id="streaming",
        ),
        # Dock
        _spec("dock.open_cover", "Open cover", "Open the dock cover", schema({})),
        _spec("dock.close_cover", "Close cover", "Close the dock cover", schema({"force": _BOOL})),
        _spec("dock.start_charging", "Start charging", "Start aircraft charging", schema({})),
        _spec("dock.stop_charging", "Stop charging", "Stop aircraft charging", schema({})),
        # Asset
        _spec("asset.reboot", "Reboot asset", "Reboot the asset", schema({})),
        _spec(
            "asset.boot_sub_asset",
            "Power sub-asset",
            "Power the sub-asset on or off",
            schema({"enabled": _BOOL}, ["enabled"]),
        ),
        _spec(
            "asset.remote_debug",
            "Remote debug mode",
            "Enable or disable remote debug mode",
            schema({"enabled": _BOOL}, ["enabled"]),
        ),
        _spec(
            "asset.change_ac_mode",
            "Air conditioning mode",
            "Change air conditioning mode",
            schema({"mode": _STRING}, ["mode"]),
        ),
        # Mission
        _spec(
            "mission.waypoint.execute",
            "Fly waypoint mission",
            "Build, upload and fly a waypoint mission",
            _WAYPOINT_SCHEMA,
            output_schema=schema({"task_id": _STRING}, ["task_id"]),
            schema_version="1",
        ),
        _spec("mission.pause", "Pause mission", "Pause the running waypoint mission", schema({})),
        _spec("mission.resume", "Resume mission", "Resume the paused waypoint mission", schema({})),
        _spec("mission.stop", "Stop mission", "Stop the running mission or task", schema({"taskId": _STRING})),
        _spec(
            "mission.prepare",
            "Prepare task",
            "Prepare a task for execution",
            schema({"taskId": _STRING}, ["taskId"]),
        ),
        _spec("mission.start", "Start task", "Start a prepared task", schema({"taskId": _STRING}, ["taskId"])),
        # Detections (server-streaming RPC; advertised so the catalog shows it, never dispatched
        # through ExecuteCommand -- see the plan's "deliberately NOT collapsing the streaming RPCs")
        _spec("detections.stream", "Stream detections", "Stream AI detections", schema({}), skill_id="detection"),
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
    display_name: str | None = None
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

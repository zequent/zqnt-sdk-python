"""
The capability contract has to survive the trip onto the wire, not just exist in the model.

Before 2.0 this mapping dropped everything but command/description/state, so an adapter had no
way to tell the platform what params a command takes — which is what the console needs to build
a parameter form and what mission-autonomy needs to detect contract drift.
"""

from google.protobuf import timestamp_pb2
from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

from edge_sdk.models.common import (
    AssetType,
    Capabilities,
    Capability,
    CapabilitySource,
    CapabilityState,
    CapabilityTarget,
    CapabilityTargetType,
)
from edge_sdk.server._converters import capabilities_to_proto


def _convert(*capabilities: Capability):
    snapshot = Capabilities(asset_sn="SN-1", asset_type=AssetType.AIRCRAFT, capabilities=list(capabilities))
    proto = capabilities_to_proto(snapshot, common_pb2, timestamp_pb2)
    return {c.command_id: c for c in proto.capabilities}


def test_schemas_and_versions_reach_the_wire():
    converted = _convert(
        Capability(
            command_id="mission.waypoint.execute",
            description="Fly a waypoint mission",
            input_schema={"type": "object", "required": ["waypoints"]},
            output_schema={"type": "object", "properties": {"task_id": {"type": "string"}}},
            schema_version="1",
            skill_id="mission",
        )
    )["mission.waypoint.execute"]

    assert converted.input_schema["required"] == ["waypoints"]
    assert "task_id" in converted.output_schema["properties"]
    assert converted.schema_version == "1"
    assert converted.skill_id == "mission"


def test_target_is_mapped_including_the_payload_ref():
    converted = _convert(
        Capability(
            command_id="vendor.acme.spray",
            target=CapabilityTarget(CapabilityTargetType.PAYLOAD, "payload-1"),
        )
    )["vendor.acme.spray"]

    assert converted.target.type == common_pb2.CAPABILITY_TARGET_TYPE_PAYLOAD
    assert converted.target.target_ref == "payload-1"


def test_state_is_carried_rather_than_flattened_to_a_bool():
    converted = _convert(
        Capability(
            command_id="dock.open_cover",
            state=CapabilityState.TEMPORARILY_UNAVAILABLE,
            unavailable_reason="cover jammed",
        ),
        Capability(command_id="flight.takeoff", state=CapabilityState.UNSUPPORTED),
    )

    assert converted["dock.open_cover"].state == common_pb2.CAPABILITY_STATE_TEMPORARILY_UNAVAILABLE
    assert converted["dock.open_cover"].unavailable_reason == "cover jammed"
    assert converted["flight.takeoff"].state == common_pb2.CAPABILITY_STATE_UNSUPPORTED


def test_source_defaults_to_edge_adapter():
    converted = _convert(Capability(command_id="flight.takeoff"))["flight.takeoff"]

    assert converted.source == common_pb2.CAPABILITY_SOURCE_EDGE_ADAPTER
    assert CapabilitySource.EDGE_ADAPTER == 2


def test_snapshot_is_marked_current():
    snapshot = Capabilities(asset_sn="SN-1", asset_type=AssetType.AIRCRAFT, capabilities=[])
    proto = capabilities_to_proto(snapshot, common_pb2, timestamp_pb2)

    assert proto.snapshot_state == common_pb2.CAPABILITY_SNAPSHOT_STATE_CURRENT
    assert proto.asset_type == "AIRCRAFT"

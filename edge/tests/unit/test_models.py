"""
Unit tests for EdgeResponse factory methods and CacheKeys.
"""

from edge_sdk.models.common import (
    AssetType,
    AssetVendor,
    CustomCommandResponse,
    EdgeResponse,
    ErrorCode,
    ErrorMessage,
    proto_enum_lookup,
)

# ---------------------------------------------------------------------------
# EdgeResponse
# ---------------------------------------------------------------------------


def test_ok_sets_success_true():
    resp = EdgeResponse.ok("t1", "S1")
    assert resp.success is True
    assert resp.tid == "t1"
    assert resp.sn == "S1"
    assert resp.error is None


def test_fail_sets_success_false():
    err = ErrorMessage("boom", ErrorCode.ASSET_ERROR)
    resp = EdgeResponse.fail("t1", "S1", err)
    assert resp.success is False
    assert resp.error.code == ErrorCode.ASSET_ERROR
    assert resp.error.message == "boom"


def test_not_supported_sets_success_false_with_sdk_error():
    resp = EdgeResponse.not_supported("t1", "S1")
    assert resp.success is False
    assert resp.error is not None
    assert resp.error.code == ErrorCode.SDK_ERROR


def test_not_supported_without_args_uses_empty_strings():
    resp = EdgeResponse.not_supported()
    assert resp.tid == ""
    assert resp.sn == ""
    assert resp.success is False


def test_ok_with_optional_fields():
    resp = EdgeResponse.ok(
        "t1",
        "S1",
        message="all good",
        stream_url="rtmp://stream",
        video_id="vid-1",
    )
    assert resp.message == "all good"
    assert resp.stream_url == "rtmp://stream"
    assert resp.video_id == "vid-1"


def test_ok_defaults_external_execution_id_to_none():
    resp = EdgeResponse.ok("t1", "S1")
    assert resp.external_execution_id is None


def test_ok_sets_external_execution_id():
    resp = EdgeResponse.ok("t1", "S1", external_execution_id="vendor-123")
    assert resp.external_execution_id == "vendor-123"


# ---------------------------------------------------------------------------
# CustomCommandResponse
# ---------------------------------------------------------------------------


def test_custom_command_response_ok_sets_success_true():
    resp = CustomCommandResponse.ok("t1", "S1", "mission.waypoint.execute")
    assert resp.success is True
    assert resp.tid == "t1"
    assert resp.sn == "S1"
    assert resp.command_type == "mission.waypoint.execute"
    assert resp.error is None
    assert resp.external_execution_id is None


def test_custom_command_response_ok_sets_external_execution_id():
    resp = CustomCommandResponse.ok(
        "t1",
        "S1",
        "mission.waypoint.execute",
        result={"task_id": "task-42"},
        external_execution_id="task-42",
    )
    assert resp.result == {"task_id": "task-42"}
    assert resp.external_execution_id == "task-42"


# ---------------------------------------------------------------------------
# AssetType / AssetVendor parity with the real proto enums (zqnt-utils)
#
# This SDK carries its own plain-Python IntEnum mirrors of asset.proto's AssetTypeEnum/
# AssetVendor rather than depending on the generated protobuf classes directly (see this module's
# own docstring: "No protobuf types are exposed here"). That means every time a new value is added
# proto-side it has to be added here by hand too -- and it wasn't: this SDK's AssetType/AssetVendor
# were missing RNS (added when the RNS adapter shipped) and AssetVendor was also missing ZQNT
# (added 2026-09-02 for the Integration Hub platform bridge) until fixed alongside this test.
# Found live: rns-adapter's own RegistrationConfig.from_env() -- the only place that resolves
# ASSET_TYPE/ASSET_VENDOR env vars into these enums -- would have failed (KeyError, caught and
# logged as a skipped registration, not a crash) for exactly the values rns-adapter itself needs.
#
# These two tests compare against the real generated proto enums directly (not a hardcoded name
# list) so they catch the *next* drift automatically, not just today's.
# ---------------------------------------------------------------------------


def test_asset_type_has_every_proto_value():
    from zqnt_utils.generated.zqnt.common_pb2 import AssetTypeEnum

    proto_names = {name.removeprefix("ASSET_TYPE_") for name in AssetTypeEnum.keys()}
    sdk_names = {member.name for member in AssetType}
    assert proto_names == sdk_names


def test_asset_vendor_has_every_proto_value():
    from zqnt_utils.generated.zqnt.common_pb2 import AssetVendor as ProtoAssetVendor

    proto_names = {name.removeprefix("ASSET_VENDOR_") for name in ProtoAssetVendor.keys()}
    sdk_names = {member.name for member in AssetVendor}
    assert proto_names == sdk_names


def test_proto_enum_lookup_resolves_every_asset_type():
    from zqnt_utils.generated.zqnt.common_pb2 import AssetTypeEnum

    for proto_name in AssetTypeEnum.keys():
        proto_enum_lookup(AssetType, proto_name)  # must not raise


def test_proto_enum_lookup_resolves_every_asset_vendor():
    from zqnt_utils.generated.zqnt.common_pb2 import AssetVendor as ProtoAssetVendor

    for proto_name in ProtoAssetVendor.keys():
        proto_enum_lookup(AssetVendor, proto_name)  # must not raise

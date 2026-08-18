"""
Unit tests for EdgeResponse factory methods and CacheKeys.
"""

from edge_sdk.models.common import CustomCommandResponse, EdgeResponse, ErrorCode, ErrorMessage

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

"""
Unit tests for NotificationPublisher – no live gRPC connection required.

Primarily regression coverage for the proto builders against the 1.3.0 ``events.proto`` schema
this branch tracks: ``ProduceNotificationRequest.event`` is a ``NotificationEvent`` wrapper
(``asset_status``/``task``/``mission``) -- ``task`` (``TaskEvent``) is retired on main/2.0.0 in
favor of the vendor-neutral ``CommandExecutionEvent``, which doesn't exist at 1.3.0.
"""

import asyncio

import pytest
from zqnt_utils.generated.zqnt import events_pb2

from edge_sdk.client.notification_publisher import NotificationPublisher
from edge_sdk.models.common import MissionStatus, MissionType, TaskStatus, TaskType
from edge_sdk.models.notification import AssetStatusEvent, MissionEvent, TaskEvent


class _FakePublisher(NotificationPublisher):
    """NotificationPublisher with the queue pre-initialised; stream task bypassed."""

    def __init__(self, queue_max_size: int = 100):
        super().__init__(host="localhost", sn="TEST-001", queue_max_size=queue_max_size)
        self._queue = asyncio.Queue(maxsize=queue_max_size)
        self._closed = False


# ---------------------------------------------------------------------------
# Guard: publish before connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_asset_status_before_connect_raises():
    pub = NotificationPublisher(host="localhost", sn="TEST")
    with pytest.raises(RuntimeError, match="connect"):
        await pub.publish_asset_status(AssetStatusEvent(sn="TEST", online=True))


# ---------------------------------------------------------------------------
# Queue mechanics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_asset_status_enqueues_frame():
    pub = _FakePublisher()
    await pub.publish_asset_status(AssetStatusEvent(sn="DOCK001", online=True))
    assert pub._queue.qsize() == 1


@pytest.mark.asyncio
async def test_queue_full_drops_event_silently():
    pub = _FakePublisher(queue_max_size=1)
    await pub.publish_asset_status(AssetStatusEvent(sn="DOCK001", online=True))
    await pub.publish_asset_status(AssetStatusEvent(sn="DOCK001", online=False))  # dropped, not raised
    assert pub._queue.qsize() == 1


# ---------------------------------------------------------------------------
# Proto builders — the actual regression coverage
# ---------------------------------------------------------------------------


def test_build_asset_status_request_matches_schema():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_asset_status_request(AssetStatusEvent(sn="DOCK1", online=True, asset_id="a1", message="ok"))

    assert isinstance(req, events_pb2.ProduceNotificationRequest)
    assert req.base.sn == "DOCK1"
    assert req.event.WhichOneof("event") == "asset_status"
    assert req.event.asset_status.sn == "DOCK1"
    assert req.event.asset_status.online is True
    assert req.event.asset_status.asset_id == "a1"
    assert req.event.asset_status.message == "ok"
    assert req.event_type == events_pb2.NotificationEventType.NOTIFICATION_EVENT_ASSET_STATUS


def test_build_mission_event_request_matches_schema():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_mission_event_request(
        MissionEvent(
            mission_id="m1",
            mission_type=MissionType.STANDARD,
            status=MissionStatus.ACTIVE,
            sn="DOCK1",
            message="running",
        )
    )

    assert req.event.WhichOneof("event") == "mission"
    assert req.event.mission.mission_id == "m1"
    assert req.event.mission.status == common_status_active()
    assert req.event.mission.message == "running"
    assert req.event_type == events_pb2.NotificationEventType.NOTIFICATION_EVENT_MISSION


def test_build_task_event_request_matches_schema():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_task_event_request(
        TaskEvent(
            task_id="t1",
            task_type=TaskType.WAYPOINT,
            status=TaskStatus.RUNNING,
            sn="DOCK1",
            progress=0.5,
            message="en route",
            external_task_type="dji.wayline",
        )
    )

    assert req.event.WhichOneof("event") == "task"
    assert req.event.task.task_id == "t1"
    assert req.event.task.task_type == common_task_type_waypoint()
    assert req.event.task.status == common_task_status_running()
    assert req.event.task.progress == pytest.approx(0.5)
    assert req.event.task.message == "en route"
    assert req.event.task.external_task_type == "dji.wayline"
    assert req.event_type == events_pb2.NotificationEventType.NOTIFICATION_EVENT_TASK


def test_build_task_event_uses_critical_severity_on_error():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_task_event_request(
        TaskEvent(task_id="t2", task_type=TaskType.WAYPOINT, status=TaskStatus.ERROR, sn="DOCK1")
    )
    assert req.severity == events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_CRITICAL


def common_status_active():
    from zqnt_utils.generated.zqnt import common_pb2

    return common_pb2.MissionStatus.MISSION_STATUS_ACTIVE


def common_task_type_waypoint():
    from zqnt_utils.generated.zqnt import common_pb2

    return common_pb2.TaskTypeProto.TASK_TYPE_WAYPOINT


def common_task_status_running():
    from zqnt_utils.generated.zqnt import common_pb2

    return common_pb2.TaskStatus.TASK_RUNNING


def test_publisher_has_no_2_0_0_only_command_execution_method():
    """This branch tracks the 1.3.0 contract, where events.proto has no CommandExecutionEvent
    at all -- publish_task_event is the real, 1.3.0-accurate method (main/2.0.0 drops it in
    favor of publish_command_execution_event; see this file's own main-branch counterpart)."""
    assert hasattr(NotificationPublisher, "publish_task_event")
    assert not hasattr(NotificationPublisher, "publish_command_execution_event")

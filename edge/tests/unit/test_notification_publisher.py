"""
Unit tests for NotificationPublisher – no live gRPC connection required.

Primarily regression coverage for the proto builders against the current ``events.proto``
schema (``ProduceNotificationRequest.event`` is a ``NotificationEvent`` wrapper, not flat
``asset_status``/``task_event``/``operation_event`` fields; ``task`` notifications are retired
in favor of ``command_execution``, and ``operation`` was renamed ``mission``).
"""

import asyncio

import pytest
from zqnt_utils.generated.zqnt import events_pb2

from edge_sdk.client.notification_publisher import NotificationPublisher
from edge_sdk.models.common import CommandExecutionStatus, MissionStatus, MissionType
from edge_sdk.models.notification import AssetStatusEvent, CommandExecutionEvent, MissionEvent


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


def test_build_command_execution_event_request_matches_schema():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_command_execution_event_request(
        CommandExecutionEvent(
            external_execution_id="exec-1",
            status=CommandExecutionStatus.SUCCEEDED,
            sn="DOCK1",
            command_id="dock.open_cover",
            progress=1.0,
            message="done",
        )
    )

    assert req.event.WhichOneof("event") == "command_execution"
    assert req.event.command_execution.external_execution_id == "exec-1"
    assert req.event.command_execution.command_id == "dock.open_cover"
    assert req.event.command_execution.asset_sn == "DOCK1"
    assert req.event.command_execution.status == events_pb2.CommandExecutionStatus.COMMAND_EXECUTION_STATUS_SUCCEEDED
    assert req.event_type == events_pb2.NotificationEventType.NOTIFICATION_EVENT_COMMAND_EXECUTION


def test_build_command_execution_event_uses_critical_severity_on_failure():
    pub = NotificationPublisher(host="localhost", sn="DOCK1")
    req = pub._build_command_execution_event_request(
        CommandExecutionEvent(external_execution_id="exec-2", status=CommandExecutionStatus.FAILED, sn="DOCK1")
    )
    assert req.severity == events_pb2.NotificationSeverity.NOTIFICATION_SEVERITY_CRITICAL


def common_status_active():
    from zqnt_utils.generated.zqnt import common_pb2

    return common_pb2.MissionStatus.MISSION_STATUS_ACTIVE


def test_publisher_has_no_legacy_task_event_method():
    assert not hasattr(NotificationPublisher, "publish_task_event")
    assert not hasattr(NotificationPublisher, "publish_operation_event")

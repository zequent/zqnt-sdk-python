"""Unit tests for the ``LiveDataService`` facade — lifecycle + dispatch, no live gRPC connection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from edge_sdk.client.live_data_service import LiveDataService
from edge_sdk.models.common import MissionStatus, MissionType, TaskStatus, TaskType
from edge_sdk.models.notification import AssetStatusEvent, MissionEvent, TaskEvent
from edge_sdk.models.telemetry import AssetTelemetry, SubAssetTelemetry


def _service() -> LiveDataService:
    svc = LiveDataService(host="localhost", sn="DOCK-1")
    svc.telemetry.connect = AsyncMock()
    svc.telemetry.close = AsyncMock()
    svc.telemetry.publish_asset_telemetry = AsyncMock()
    svc.telemetry.publish_subasset_telemetry = AsyncMock()
    svc.detection.connect = AsyncMock()
    svc.detection.close = AsyncMock()
    svc.detection.publish_detection_batch = AsyncMock()
    svc.notification.connect = AsyncMock()
    svc.notification.close = AsyncMock()
    svc.notification.publish_asset_status = AsyncMock()
    svc.notification.publish_mission_event = AsyncMock()
    svc.notification.publish_task_event = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_connect_opens_all_three_streams() -> None:
    svc = _service()
    await svc.connect()
    svc.telemetry.connect.assert_awaited_once()
    svc.detection.connect.assert_awaited_once()
    svc.notification.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_closes_all_three_streams() -> None:
    svc = _service()
    await svc.close()
    svc.telemetry.close.assert_awaited_once()
    svc.detection.close.assert_awaited_once()
    svc.notification.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_context_manager_connects_and_closes() -> None:
    svc = _service()
    async with svc:
        svc.telemetry.connect.assert_awaited_once()
    svc.telemetry.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_produce_telemetry_dispatches_by_type() -> None:
    svc = _service()
    asset_t = AssetTelemetry(id="DOCK-1")
    sub_t = SubAssetTelemetry(id="DRONE-1")

    await svc.produce_telemetry(asset_t)
    svc.telemetry.publish_asset_telemetry.assert_awaited_once_with(asset_t)

    await svc.produce_telemetry(sub_t)
    svc.telemetry.publish_subasset_telemetry.assert_awaited_once_with(sub_t)


@pytest.mark.asyncio
async def test_produce_notification_dispatches_by_type() -> None:
    svc = _service()

    status = AssetStatusEvent(sn="DOCK-1", online=True)
    await svc.produce_notification(status)
    svc.notification.publish_asset_status.assert_awaited_once_with(status)

    mission = MissionEvent(mission_id="m1", mission_type=MissionType.STANDARD, status=MissionStatus.ACTIVE)
    await svc.produce_notification(mission)
    svc.notification.publish_mission_event.assert_awaited_once_with(mission)

    task = TaskEvent(task_id="t1", task_type=TaskType.WAYPOINT, status=TaskStatus.RUNNING)
    await svc.produce_notification(task)
    svc.notification.publish_task_event.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_produce_notification_rejects_unknown_type() -> None:
    svc = _service()
    with pytest.raises(TypeError):
        await svc.produce_notification(object())  # type: ignore[arg-type]

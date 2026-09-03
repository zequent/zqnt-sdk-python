"""MissionAutonomy sub-client — unary RPCs over MissionAutonomyService.

This branch tracks the 1.3.0 wire contract: Mission/Task CRUD + lifecycle (Start/Stop/Pause/
Resume) + Scheduler CRUD (Mission/Task-based, not the mission-free shape main uses) -- mirroring
``com.zqnt.sdk.client.missionautonomy.application.MissionAutonomy`` and ``client-go-sdk``'s
``missionautonomy`` package for the same RPCs, adapted for ``asyncio`` + ``grpc.aio``.

Application/SkillExecution (main/2.0.0's replacement for Mission/Task, via
``capability-execution-*.proto``) don't exist at 1.3.0 at all -- this branch has none of that
surface. See zqnt-protos' README "Versioning" section, and this file's own main-branch
counterpart for the mirror-image cut (Mission/Task stubbed there raising
:class:`~client_sdk.exceptions.LegacyOperationRemovedError`, Application/SkillExecution real).
"""

from __future__ import annotations

import logging
from typing import Any

import grpc.aio

from ..config.resilience import ResilienceConfig
from ..exceptions import MissionAutonomyError
from ..grpc_.resilience import GrpcResilience
from ..models._converters import build_request_base
from ..models._validation import validate_non_blank
from ..models.mission_autonomy import (
    MissionDTO,
    MissionResponse,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
)
from ._converters import (
    mission_to_proto,
    proto_to_mission_response,
    proto_to_scheduler_response,
    proto_to_task_response,
    scheduler_to_proto,
    task_to_proto,
)

logger = logging.getLogger(__name__)


# Sentinel SN for non-asset-scoped management RPCs (Mission/Task/Scheduler CRUD).
_DEFAULT_SN = "client-sdk"


class MissionAutonomyClient:
    """Async client for the ``MissionAutonomyService`` gRPC API."""

    def __init__(
        self,
        channel: grpc.aio.Channel,
        resilience: ResilienceConfig,
    ) -> None:
        try:
            from zqnt_utils.generated.zqnt import mission_autonomy_pb2_grpc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - generation step
            raise ImportError("Protobuf stubs not found. Run scripts/generate_protos.sh first.") from exc

        self._channel = channel
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)
        self._stub = mission_autonomy_pb2_grpc.MissionAutonomyServiceStub(channel)

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    async def _call(self, rpc_name: str, request):
        rpc = getattr(self._stub, rpc_name)
        return await self._resilience_helper.execute(lambda: rpc(request, timeout=self._timeout))

    @staticmethod
    def _unwrap(operation: str, proto, payload_field: str):
        """Return ``getattr(proto, payload_field)`` on success, else raise :class:`MissionAutonomyError`."""
        if bool(getattr(proto, "has_errors", False)):
            err = proto.error
            raise MissionAutonomyError(operation, err.error_code, err.error_message)
        return getattr(proto, payload_field)

    # ------------------------------------------------------------------
    # Mission CRUD
    # ------------------------------------------------------------------

    async def create_mission(self, mission: MissionDTO) -> MissionResponse:
        validate_non_blank("mission.name", mission.name)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateMission: name=%s", mission.name)
        req = mission_autonomy_contracts_pb2.CreateMissionRequest(
            base=build_request_base(_DEFAULT_SN), mission=mission_to_proto(mission)
        )
        proto = await self._call("CreateMission", req)
        return proto_to_mission_response(proto)

    async def update_mission(self, mission_id: str, mission: MissionDTO) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("UpdateMission: id=%s", mission_id)
        req = mission_autonomy_contracts_pb2.UpdateMissionRequest(
            base=build_request_base(_DEFAULT_SN), mission_id=mission_id, mission=mission_to_proto(mission)
        )
        proto = await self._call("UpdateMission", req)
        return proto_to_mission_response(proto)

    async def get_mission(self, mission_id: str) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("GetMission: id=%s", mission_id)
        req = mission_autonomy_contracts_pb2.GetMissionRequest(
            base=build_request_base(_DEFAULT_SN), mission_id=mission_id
        )
        proto = await self._call("GetMission", req)
        return proto_to_mission_response(proto)

    async def delete_mission(self, mission_id: str) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteMission: id=%s", mission_id)
        req = mission_autonomy_contracts_pb2.DeleteMissionRequest(
            base=build_request_base(_DEFAULT_SN), mission_id=mission_id
        )
        proto = await self._call("DeleteMission", req)
        return proto_to_mission_response(proto)

    # ------------------------------------------------------------------
    # Task CRUD + lifecycle
    # ------------------------------------------------------------------

    async def create_task(self, task: TaskDTO) -> TaskResponse:
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateTask: name=%s", task.name)
        req = mission_autonomy_contracts_pb2.CreateTaskRequest(
            base=build_request_base(_DEFAULT_SN), task=task_to_proto(task)
        )
        proto = await self._call("CreateTask", req)
        return proto_to_task_response(proto)

    async def update_task(self, task_id: str, task: TaskDTO) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("UpdateTask: id=%s", task_id)
        req = mission_autonomy_contracts_pb2.UpdateTaskRequest(
            base=build_request_base(_DEFAULT_SN), task_id=task_id, task=task_to_proto(task)
        )
        proto = await self._call("UpdateTask", req)
        return proto_to_task_response(proto)

    async def get_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("GetTask: id=%s", task_id)
        req = mission_autonomy_contracts_pb2.GetTaskRequest(base=build_request_base(_DEFAULT_SN), task_id=task_id)
        proto = await self._call("GetTask", req)
        return proto_to_task_response(proto)

    async def get_task_by_flight_id(self, flight_id: str) -> TaskResponse:
        validate_non_blank("flightId", flight_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("GetTaskByFlightId: flightId=%s", flight_id)
        req = mission_autonomy_contracts_pb2.GetTaskByFlightIdRequest(
            base=build_request_base(_DEFAULT_SN), flight_id=flight_id
        )
        proto = await self._call("GetTaskByFlightId", req)
        return proto_to_task_response(proto)

    async def delete_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteTask: id=%s", task_id)
        req = mission_autonomy_contracts_pb2.DeleteTaskRequest(base=build_request_base(_DEFAULT_SN), task_id=task_id)
        proto = await self._call("DeleteTask", req)
        return proto_to_task_response(proto)

    async def _task_lifecycle(self, rpc_name: str, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("%s: id=%s", rpc_name, task_id)
        req = mission_autonomy_contracts_pb2.TaskLifecycleRequest(base=build_request_base(_DEFAULT_SN), task_id=task_id)
        proto = await self._call(rpc_name, req)
        return proto_to_task_response(proto)

    async def start_task(self, task_id: str) -> TaskResponse:
        return await self._task_lifecycle("StartTask", task_id)

    async def stop_task(self, task_id: str) -> TaskResponse:
        return await self._task_lifecycle("StopTask", task_id)

    async def pause_task(self, task_id: str) -> TaskResponse:
        return await self._task_lifecycle("PauseTask", task_id)

    async def resume_task(self, task_id: str) -> TaskResponse:
        return await self._task_lifecycle("ResumeTask", task_id)

    # ------------------------------------------------------------------
    # Scheduler CRUD
    # ------------------------------------------------------------------

    async def create_scheduler(self, scheduler: SchedulerDTO) -> SchedulerResponse:
        validate_non_blank("scheduler.name", scheduler.name)
        validate_non_blank("scheduler.cronExpression", scheduler.cron_expression)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateScheduler: name=%s", scheduler.name)
        req = mission_autonomy_contracts_pb2.CreateSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            scheduler=scheduler_to_proto(scheduler),
        )
        proto = await self._call("CreateScheduler", req)
        return proto_to_scheduler_response(proto)

    async def update_scheduler(self, scheduler_id: str, scheduler: SchedulerDTO) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("UpdateScheduler: id=%s", scheduler_id)
        req = mission_autonomy_contracts_pb2.UpdateSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            scheduler=scheduler_to_proto(scheduler),
            scheduler_id=scheduler_id,
        )
        proto = await self._call("UpdateScheduler", req)
        return proto_to_scheduler_response(proto)

    async def get_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("GetScheduler: id=%s", scheduler_id)
        req = mission_autonomy_contracts_pb2.GetSchedulerRequest(
            base=build_request_base(_DEFAULT_SN), scheduler_id=scheduler_id
        )
        proto = await self._call("GetScheduler", req)
        return proto_to_scheduler_response(proto)

    async def delete_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteScheduler: id=%s", scheduler_id)
        req = mission_autonomy_contracts_pb2.DeleteSchedulerRequest(
            base=build_request_base(_DEFAULT_SN), scheduler_id=scheduler_id
        )
        proto = await self._call("DeleteScheduler", req)
        return proto_to_scheduler_response(proto)

    async def list_schedulers(self, task_id: str | None = None) -> SchedulerResponse:
        """Fetch all schedulers, optionally filtered to one task's. Result is in
        :attr:`SchedulerResponse.schedulers`. ``task_id`` filtering is 1.3.0-only -- reserved on
        the wire at main/2.0.0 along with the rest of the Mission/Task model."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("ListSchedulers")
        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if task_id:
            kwargs["task_id"] = task_id
        proto = await self._call("ListSchedulers", mission_autonomy_contracts_pb2.ListSchedulersRequest(**kwargs))
        return proto_to_scheduler_response(proto)

    async def create_schedulers(self, schedulers: list[SchedulerDTO]) -> SchedulerResponse:
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateSchedulers: count=%d", len(schedulers))
        req = mission_autonomy_contracts_pb2.CreateSchedulersRequest(
            base=build_request_base(_DEFAULT_SN),
            schedulers=[scheduler_to_proto(s) for s in schedulers],
        )
        proto = await self._call("CreateSchedulers", req)
        return proto_to_scheduler_response(proto)

    async def delete_schedulers(self, scheduler_ids: list[str]) -> SchedulerResponse:
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteSchedulers: count=%d", len(scheduler_ids))
        req = mission_autonomy_contracts_pb2.DeleteSchedulersRequest(
            base=build_request_base(_DEFAULT_SN),
            scheduler_ids=list(scheduler_ids),
        )
        proto = await self._call("DeleteSchedulers", req)
        return proto_to_scheduler_response(proto)

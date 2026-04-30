"""MissionAutonomy sub-client – unary RPCs over MissionAutonomyService.

Mirrors :java:`com.zqnt.sdk.client.missionautonomy.application.MissionAutonomy`
adapted for ``asyncio`` + ``grpc.aio``.
"""

from __future__ import annotations

import logging

import grpc.aio

from ..config.resilience import ResilienceConfig
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


# Sentinel SN for non-asset-scoped management RPCs.
_DEFAULT_SN = "client-sdk"


class MissionAutonomyClient:
    """Async client for the ``MissionAutonomyService`` gRPC API."""

    def __init__(
        self,
        channel: grpc.aio.Channel,
        resilience: ResilienceConfig,
    ) -> None:
        try:
            from ..generated import mission_autonomy_pb2_grpc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - generation step
            raise ImportError(
                "Protobuf stubs not found. Run scripts/generate_protos.sh first."
            ) from exc

        self._channel = channel
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)
        self._stub = mission_autonomy_pb2_grpc.MissionAutonomyServiceStub(channel)

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    # ------------------------------------------------------------------
    # Mission CRUD
    # ------------------------------------------------------------------

    async def create_mission(self, mission: MissionDTO) -> MissionResponse:
        validate_non_blank("mission.name", mission.name)
        logger.info("CreateMission: name=%s", mission.name)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.CreateMissionRequest(
            base=build_request_base(_DEFAULT_SN),
            missionDTO=mission_to_proto(mission),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.CreateMission(req, timeout=self._timeout)
        )
        return proto_to_mission_response(proto)

    async def update_mission(
        self, mission_id: str, mission: MissionDTO
    ) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        validate_non_blank("mission.name", mission.name)
        logger.info("UpdateMission: id=%s", mission_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.UpdateMissionRequest(
            base=build_request_base(_DEFAULT_SN),
            missionDTO=mission_to_proto(mission),
            missionId=mission_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.UpdateMission(req, timeout=self._timeout)
        )
        return proto_to_mission_response(proto)

    async def get_mission(self, mission_id: str) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        logger.info("GetMission: id=%s", mission_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.GetMissionRequest(
            base=build_request_base(_DEFAULT_SN),
            missionId=mission_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.GetMission(req, timeout=self._timeout)
        )
        return proto_to_mission_response(proto)

    async def delete_mission(self, mission_id: str) -> MissionResponse:
        validate_non_blank("missionId", mission_id)
        logger.info("DeleteMission: id=%s", mission_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.DeleteMissionRequest(
            base=build_request_base(_DEFAULT_SN),
            missionId=mission_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.DeleteMission(req, timeout=self._timeout)
        )
        return proto_to_mission_response(proto)

    # ------------------------------------------------------------------
    # Task CRUD + start/stop
    # ------------------------------------------------------------------

    async def create_task(self, task: TaskDTO) -> TaskResponse:
        logger.info("CreateTask: name=%s", task.name)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.CreateTaskRequest(
            base=build_request_base(task.sn_number or _DEFAULT_SN),
            taskDTO=task_to_proto(task),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.CreateTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def update_task(self, task_id: str, task: TaskDTO) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        logger.info("UpdateTask: id=%s", task_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.UpdateTaskRequest(
            base=build_request_base(task.sn_number or _DEFAULT_SN),
            taskId=task_id,
            taskDTO=task_to_proto(task),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.UpdateTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def get_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        logger.info("GetTask: id=%s", task_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.GetTaskRequest(
            base=build_request_base(_DEFAULT_SN),
            taskId=task_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.GetTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def get_task_by_flight_id(self, flight_id: str) -> TaskResponse:
        validate_non_blank("flightId", flight_id)
        logger.info("GetTaskByFlightId: flightId=%s", flight_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.GetTaskRequest(
            base=build_request_base(_DEFAULT_SN),
            flightId=flight_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.GetTaskByFlightId(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def delete_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        logger.info("DeleteTask: id=%s", task_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.DeleteTaskRequest(
            base=build_request_base(_DEFAULT_SN),
            taskId=task_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.DeleteTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def start_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        logger.info("StartTask: id=%s", task_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.StartTaskRequest(
            base=build_request_base(_DEFAULT_SN),
            taskId=task_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StartTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    async def stop_task(self, task_id: str) -> TaskResponse:
        validate_non_blank("taskId", task_id)
        logger.info("StopTask: id=%s", task_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.StopTaskRequest(
            base=build_request_base(_DEFAULT_SN),
            taskId=task_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StopTask(req, timeout=self._timeout)
        )
        return proto_to_task_response(proto)

    # ------------------------------------------------------------------
    # Scheduler CRUD
    # ------------------------------------------------------------------

    async def create_scheduler(self, scheduler: SchedulerDTO) -> SchedulerResponse:
        validate_non_blank("scheduler.name", scheduler.name)
        validate_non_blank("scheduler.cronExpression", scheduler.cron_expression)
        logger.info("CreateScheduler: name=%s", scheduler.name)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.CreateSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            schedulerDTO=scheduler_to_proto(scheduler),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.CreateScheduler(req, timeout=self._timeout)
        )
        return proto_to_scheduler_response(proto)

    async def update_scheduler(
        self, scheduler_id: str, scheduler: SchedulerDTO
    ) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        logger.info("UpdateScheduler: id=%s", scheduler_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.UpdateSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            schedulerDTO=scheduler_to_proto(scheduler),
            schedulerId=scheduler_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.UpdateScheduler(req, timeout=self._timeout)
        )
        return proto_to_scheduler_response(proto)

    async def get_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        logger.info("GetScheduler: id=%s", scheduler_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.GetSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            schedulerId=scheduler_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.GetScheduler(req, timeout=self._timeout)
        )
        return proto_to_scheduler_response(proto)

    async def delete_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        logger.info("DeleteScheduler: id=%s", scheduler_id)

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.DeleteSchedulerRequest(
            base=build_request_base(_DEFAULT_SN),
            schedulerId=scheduler_id,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.DeleteScheduler(req, timeout=self._timeout)
        )
        return proto_to_scheduler_response(proto)

    async def get_all_schedulers(self) -> SchedulerResponse:
        """Fetch all schedulers. Result is in :attr:`SchedulerResponse.schedulers`."""
        logger.info("GetAllSchedulers")

        from ..generated import mission_autonomy_pb2  # type: ignore[import]

        req = mission_autonomy_pb2.GetTaskRequest(
            base=build_request_base(_DEFAULT_SN),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.GetAllSchedulers(req, timeout=self._timeout)
        )
        return proto_to_scheduler_response(proto)

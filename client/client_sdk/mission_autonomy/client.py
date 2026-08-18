"""MissionAutonomy sub-client — unary RPCs over MissionAutonomyService.

Covers capability package administration (Application), the full execution lifecycle
(SkillExecution: create, start, pause, resume, cancel, signal), and Scheduler CRUD — mirroring
``com.zqnt.sdk.client.missionautonomy.application.MissionAutonomy`` and ``client-go-sdk``'s
``missionautonomy`` package for the same RPCs, adapted for ``asyncio`` + ``grpc.aio``.

Mission/Task RPCs (``createMission``, ``createTask``, ``startTask``, ...) no longer exist on any
current backend at all — replaced entirely by Application/SkillExecution. Their method names are
kept below as stubs that raise :class:`~client_sdk.exceptions.LegacyOperationRemovedError`,
mirroring ``MissionAutonomyImpl.removedLegacyOperation`` in the Java client SDK, so old call
sites fail with a clear message instead of an ``AttributeError`` deep in a proto converter.
"""

from __future__ import annotations

import logging
from typing import Any

import grpc.aio

from ..config.resilience import ResilienceConfig
from ..exceptions import LegacyOperationRemovedError, MissionAutonomyError
from ..grpc_.resilience import GrpcResilience
from ..models._converters import build_request_base, dict_to_struct, struct_to_dict
from ..models._validation import validate_non_blank
from ..models.mission_autonomy import (
    MissionDTO,
    MissionResponse,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
)
from ._converters import application_spec, proto_to_scheduler_response, scheduler_to_proto, simple_spec

logger = logging.getLogger(__name__)


# Sentinel SN for non-asset-scoped management RPCs (Application admin, Scheduler CRUD).
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
    # Application admin
    # ------------------------------------------------------------------

    async def upsert_application(self, application, expected_revision: str | None = None):
        """Create or update a capability package. ``application`` is an ``ApplicationProtoDTO``."""
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN), "application": application}
        if expected_revision:
            kwargs["expected_revision"] = expected_revision
        logger.info("UpsertApplication: id=%s", getattr(application, "id", None))
        proto = await self._call("UpsertApplication", exc.UpsertApplicationRequest(**kwargs))
        return self._unwrap("UpsertApplication", proto, "application")

    async def get_application(self, application_id: str, version: str | None = None):
        validate_non_blank("applicationId", application_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN), "application_id": application_id}
        if version:
            kwargs["version"] = version
        logger.info("GetApplication: id=%s", application_id)
        proto = await self._call("GetApplication", exc.GetApplicationRequest(**kwargs))
        return self._unwrap("GetApplication", proto, "application")

    async def list_applications(
        self,
        scope=None,
        enabled_only: bool | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> tuple[list, str]:
        """``scope`` is an ``ApplicationScopeProtoDTO`` (``None`` = every scope)."""
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if scope is not None:
            kwargs["scope"] = scope
        if enabled_only is not None:
            kwargs["enabled_only"] = enabled_only
        if page_size:
            kwargs["page_size"] = page_size
        if page_token:
            kwargs["page_token"] = page_token
        logger.info("ListApplications")
        proto = await self._call("ListApplications", exc.ListApplicationsRequest(**kwargs))
        result = self._unwrap("ListApplications", proto, "result")
        return list(result.applications), result.next_page_token

    async def delete_application(
        self,
        application_id: str,
        version: str | None = None,
        expected_revision: str | None = None,
    ) -> None:
        validate_non_blank("applicationId", application_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN), "application_id": application_id}
        if version:
            kwargs["version"] = version
        if expected_revision:
            kwargs["expected_revision"] = expected_revision
        logger.info("DeleteApplication: id=%s", application_id)
        proto = await self._call("DeleteApplication", exc.DeleteApplicationRequest(**kwargs))
        if bool(getattr(proto, "has_errors", False)):
            err = proto.error
            raise MissionAutonomyError("DeleteApplication", err.error_code, err.error_message)

    async def get_application_environments(self, application_id: str) -> list:
        validate_non_blank("applicationId", application_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        logger.info("GetApplicationEnvironments: id=%s", application_id)
        proto = await self._call(
            "GetApplicationEnvironments",
            exc.GetApplicationEnvironmentsRequest(base=build_request_base(_DEFAULT_SN), application_id=application_id),
        )
        result = self._unwrap("GetApplicationEnvironments", proto, "result")
        return list(result.pointers)

    async def promote_application_version(self, application_id: str, version: str, environment) -> list:
        """``environment`` is an ``ApplicationEnvironmentProto`` enum value (int)."""
        validate_non_blank("applicationId", application_id)
        validate_non_blank("version", version)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        logger.info("PromoteApplicationVersion: id=%s, version=%s", application_id, version)
        proto = await self._call(
            "PromoteApplicationVersion",
            exc.PromoteApplicationVersionRequest(
                base=build_request_base(_DEFAULT_SN),
                application_id=application_id,
                version=version,
                environment=environment,
            ),
        )
        result = self._unwrap("PromoteApplicationVersion", proto, "result")
        return list(result.pointers)

    # ------------------------------------------------------------------
    # SkillExecution — low-level (raw spec/options proto)
    # ------------------------------------------------------------------

    async def create_skill_execution(
        self,
        asset_sn: str,
        spec,
        options=None,
        idempotency_key: str = "",
        organization_id: str | None = None,
        location_id: str | None = None,
        theatre_id: str | None = None,
    ):
        return await self._create_or_execute(
            "CreateSkillExecution", asset_sn, spec, options, idempotency_key, organization_id, location_id, theatre_id
        )

    async def execute_skill(
        self,
        asset_sn: str,
        spec,
        options=None,
        idempotency_key: str = "",
        organization_id: str | None = None,
        location_id: str | None = None,
        theatre_id: str | None = None,
    ):
        return await self._create_or_execute(
            "ExecuteSkill", asset_sn, spec, options, idempotency_key, organization_id, location_id, theatre_id
        )

    async def _create_or_execute(
        self, rpc_name, asset_sn, spec, options, idempotency_key, organization_id, location_id, theatre_id
    ):
        validate_non_blank("sn", asset_sn)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]
        from zqnt_utils.generated.zqnt import capability_execution_dto_pb2 as execdto  # type: ignore[import]

        kwargs: dict[str, Any] = {
            "base": build_request_base(asset_sn),
            "spec": spec,
            "options": options if options is not None else execdto.SkillExecutionOptionsProto(),
            "idempotency_key": idempotency_key,
        }
        if organization_id:
            kwargs["organization_id"] = organization_id
        if location_id:
            kwargs["location_id"] = location_id
        if theatre_id:
            kwargs["theatre_id"] = theatre_id
        request_cls = exc.CreateSkillExecutionRequest if rpc_name == "CreateSkillExecution" else exc.ExecuteSkillRequest
        logger.info("%s: sn=%s", rpc_name, asset_sn)
        proto = await self._call(rpc_name, request_cls(**kwargs))
        return self._unwrap(rpc_name, proto, "execution")

    # ------------------------------------------------------------------
    # SkillExecution — convenience wrappers (mirror client-go-sdk's Create/ExecuteSimple and
    # Create/ExecuteApplication helpers)
    # ------------------------------------------------------------------

    async def create_simple_execution(
        self, asset_sn: str, command_id: str, parameters: dict | None = None, idempotency_key: str = ""
    ):
        """Create (but do not start) a single ad-hoc command execution."""
        return await self.create_skill_execution(
            asset_sn, simple_spec(command_id, parameters), idempotency_key=idempotency_key
        )

    async def execute_simple(
        self, asset_sn: str, command_id: str, parameters: dict | None = None, idempotency_key: str = ""
    ):
        """Create and atomically start a single ad-hoc command execution."""
        return await self.execute_skill(asset_sn, simple_spec(command_id, parameters), idempotency_key=idempotency_key)

    async def create_application_execution(
        self,
        asset_sn: str,
        application_id: str,
        skill_id: str,
        application_version: str | None = None,
        parameters: dict | None = None,
        idempotency_key: str = "",
    ):
        """Create (but do not start) an execution of one named Skill from a deployed Application."""
        return await self.create_skill_execution(
            asset_sn,
            application_spec(application_id, skill_id, application_version, parameters),
            idempotency_key=idempotency_key,
        )

    async def execute_application(
        self,
        asset_sn: str,
        application_id: str,
        skill_id: str,
        application_version: str | None = None,
        parameters: dict | None = None,
        idempotency_key: str = "",
    ):
        """Create and atomically start an execution of one named Skill from a deployed Application."""
        return await self.execute_skill(
            asset_sn,
            application_spec(application_id, skill_id, application_version, parameters),
            idempotency_key=idempotency_key,
        )

    # ------------------------------------------------------------------
    # SkillExecution — query + lifecycle
    # ------------------------------------------------------------------

    async def get_skill_execution(self, execution_id: str):
        validate_non_blank("executionId", execution_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        logger.info("GetSkillExecution: id=%s", execution_id)
        proto = await self._call(
            "GetSkillExecution",
            exc.GetSkillExecutionRequest(base=build_request_base(_DEFAULT_SN), execution_id=execution_id),
        )
        return self._unwrap("GetSkillExecution", proto, "execution")

    async def list_skill_executions(
        self,
        asset_sn: str | None = None,
        organization_id: str | None = None,
        status=None,
        application_id: str | None = None,
        skill_id: str | None = None,
        theatre_id: str | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> tuple[list, str]:
        """``status`` is a ``SkillExecutionStatusProto`` enum value (int), if filtering by status."""
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if asset_sn:
            kwargs["asset_sn"] = asset_sn
        if organization_id:
            kwargs["organization_id"] = organization_id
        if status is not None:
            kwargs["status"] = status
        if application_id:
            kwargs["application_id"] = application_id
        if skill_id:
            kwargs["skill_id"] = skill_id
        if theatre_id:
            kwargs["theatre_id"] = theatre_id
        if page_size:
            kwargs["page_size"] = page_size
        if page_token:
            kwargs["page_token"] = page_token
        logger.info("ListSkillExecutions")
        proto = await self._call("ListSkillExecutions", exc.ListSkillExecutionsRequest(**kwargs))
        result = self._unwrap("ListSkillExecutions", proto, "result")
        return list(result.executions), result.next_page_token

    async def _lifecycle(self, rpc_name: str, execution_id: str, reason: str | None, idempotency_key: str | None):
        validate_non_blank("executionId", execution_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN), "execution_id": execution_id}
        if reason:
            kwargs["reason"] = reason
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key
        logger.info("%s: id=%s", rpc_name, execution_id)
        proto = await self._call(rpc_name, exc.SkillExecutionLifecycleRequest(**kwargs))
        return self._unwrap(rpc_name, proto, "execution")

    async def start_skill_execution(
        self, execution_id: str, reason: str | None = None, idempotency_key: str | None = None
    ):
        return await self._lifecycle("StartSkillExecution", execution_id, reason, idempotency_key)

    async def pause_skill_execution(
        self, execution_id: str, reason: str | None = None, idempotency_key: str | None = None
    ):
        return await self._lifecycle("PauseSkillExecution", execution_id, reason, idempotency_key)

    async def resume_skill_execution(
        self, execution_id: str, reason: str | None = None, idempotency_key: str | None = None
    ):
        return await self._lifecycle("ResumeSkillExecution", execution_id, reason, idempotency_key)

    async def cancel_skill_execution(
        self, execution_id: str, reason: str | None = None, idempotency_key: str | None = None
    ):
        return await self._lifecycle("CancelSkillExecution", execution_id, reason, idempotency_key)

    async def signal_skill_execution(
        self,
        execution_id: str,
        node_id: str | None = None,
        event_type: str | None = None,
        data: dict | None = None,
        approved: bool | None = None,
        idempotency_key: str | None = None,
    ):
        """Resume an EVENT_WAIT or HUMAN_APPROVAL node.

        ``event_type`` is required for event waits; ``approved`` is required for human approvals.
        """
        validate_non_blank("executionId", execution_id)
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        kwargs: dict[str, Any] = {
            "base": build_request_base(_DEFAULT_SN),
            "execution_id": execution_id,
            "data": dict_to_struct(data),
        }
        if node_id:
            kwargs["node_id"] = node_id
        if event_type:
            kwargs["event_type"] = event_type
        if approved is not None:
            kwargs["approved"] = approved
        if idempotency_key:
            kwargs["idempotency_key"] = idempotency_key
        logger.info("SignalSkillExecution: id=%s", execution_id)
        proto = await self._call("SignalSkillExecution", exc.SignalSkillExecutionRequest(**kwargs))
        return self._unwrap("SignalSkillExecution", proto, "execution")

    async def resolve_execution_config(self, context, keys: list[str] | None = None) -> dict:
        """``context`` is an ``ExecutionConfigContextProto``. Returns the resolved config as a dict."""
        from zqnt_utils.generated.zqnt import capability_execution_contracts_pb2 as exc  # type: ignore[import]

        logger.info("ResolveExecutionConfig")
        proto = await self._call(
            "ResolveExecutionConfig",
            exc.ResolveExecutionConfigRequest(
                base=build_request_base(_DEFAULT_SN), context=context, keys=list(keys or [])
            ),
        )
        config = self._unwrap("ResolveExecutionConfig", proto, "config")
        return struct_to_dict(config.values)

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

    async def list_schedulers(self) -> SchedulerResponse:
        """Fetch all schedulers. Result is in :attr:`SchedulerResponse.schedulers`."""
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("ListSchedulers")
        req = mission_autonomy_contracts_pb2.ListSchedulersRequest(base=build_request_base(_DEFAULT_SN))
        proto = await self._call("ListSchedulers", req)
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

    # ------------------------------------------------------------------
    # Deprecated Mission/Task operations — removed on the backend entirely.
    # ------------------------------------------------------------------

    async def create_mission(self, mission: MissionDTO) -> MissionResponse:
        raise LegacyOperationRemovedError("createMission")

    async def update_mission(self, mission_id: str, mission: MissionDTO) -> MissionResponse:
        raise LegacyOperationRemovedError("updateMission")

    async def get_mission(self, mission_id: str) -> MissionResponse:
        raise LegacyOperationRemovedError("getMission")

    async def delete_mission(self, mission_id: str) -> MissionResponse:
        raise LegacyOperationRemovedError("deleteMission")

    async def create_task(self, task: TaskDTO) -> TaskResponse:
        raise LegacyOperationRemovedError("createTask")

    async def update_task(self, task_id: str, task: TaskDTO) -> TaskResponse:
        raise LegacyOperationRemovedError("updateTask")

    async def get_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("getTask")

    async def get_task_by_flight_id(self, flight_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("getTaskByFlightId")

    async def delete_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("deleteTask")

    async def start_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("startTask")

    async def stop_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("stopTask")

    async def pause_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("pauseTask")

    async def resume_task(self, task_id: str) -> TaskResponse:
        raise LegacyOperationRemovedError("resumeTask")

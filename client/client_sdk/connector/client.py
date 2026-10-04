"""Connector sub-client — the system-of-record RPCs over ConnectorService.

Mirrors :java:`com.zqnt.sdk.client.connector.application.Connector` for the same RPC set,
adapted for ``asyncio`` + ``grpc.aio``: asset/sub-asset CRUD, asset payloads, organization
lookup, Scheduler CRUD (shared with MissionAutonomyService — identical wire messages), policies,
technical config, the Skill Registry, asset-monitoring server-streaming, and the three batch
upload sessions (telemetry/detection/notification).

Like ``MissionAutonomyClient``'s Application/SkillExecution surface, and matching
``client-go-sdk``'s ``connector`` package for the RPCs it does cover, every method here works
with raw generated proto DTOs (``AssetProtoDTO``, ``SkillContractProtoDTO``, ...) rather than a
parallel dataclass hierarchy — Connector's domain model is large and already has a typed
representation; wrapping it a second time buys little. Methods raise
:class:`~client_sdk.exceptions.ConnectorError` on ``has_errors`` since there is no response
dataclass to carry a ``success`` flag on the happy path.

``PersistApplication``/``PersistSkillExecution``/``AppendSkillExecutionEvent``/
``SetAssetProperty``/``ListAssetProperties``/``DeleteAssetProperty`` are intentionally not
covered — not part of the Java client SDK's ``Connector`` interface (the Persist* trio is
Mission Autonomy's own internal write path; the asset-property RPCs postdate it).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import grpc
import grpc.aio

from ..auth import explain
from ..config.resilience import ResilienceConfig
from ..exceptions import ConnectorError
from ..grpc_.resilience import GrpcResilience
from ..live_data.stream_handle import StreamHandle
from ..mission_autonomy._converters import proto_to_scheduler_response, scheduler_to_proto
from ..models._converters import build_request_base
from ..models._validation import validate_non_blank
from ..models.mission_autonomy import SchedulerDTO, SchedulerResponse
from .batch_session import ConnectorBatchSession

logger = logging.getLogger(__name__)

# Sentinel SN for non-asset-scoped management RPCs (same convention as MissionAutonomyClient).
_DEFAULT_SN = "client-sdk"

OnAssetMonitoring = Any  # Callable[[AssetMonitoringResponse proto], Awaitable[None] | None]
OnError = Any  # Callable[[BaseException], Awaitable[None] | None]

_RETRYABLE_CODES = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.UNKNOWN,
        grpc.StatusCode.INTERNAL,
    }
)
_MAX_BACKOFF_SECONDS = 30.0


class ConnectorClient:
    """Async client for the ``ConnectorService`` gRPC API."""

    def __init__(self, channel: grpc.aio.Channel, resilience: ResilienceConfig) -> None:
        try:
            from zqnt_utils.generated.zqnt import connector_pb2_grpc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - generation step
            raise ImportError("Protobuf stubs not found. Run scripts/generate_protos.sh first.") from exc

        self._channel = channel
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)
        self._stub = connector_pb2_grpc.ConnectorServiceStub(channel)

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    async def _call(self, rpc_name: str, request):
        rpc = getattr(self._stub, rpc_name)
        return await self._resilience_helper.execute(lambda: rpc(request, timeout=self._timeout))

    @staticmethod
    def _unwrap(operation: str, proto, payload_field: str | None = None):
        """Return ``getattr(proto, payload_field)`` (or ``proto`` itself) on success, else raise."""
        if bool(getattr(proto, "has_errors", False)):
            err = proto.error
            raise ConnectorError(operation, err.error_code, err.error_message)
        return getattr(proto, payload_field) if payload_field else proto

    # ------------------------------------------------------------------
    # Asset / sub-asset CRUD
    # ------------------------------------------------------------------

    async def register_asset(self, asset):
        """``asset`` is an ``AssetProtoDTO``. Returns the registered ``AssetProtoDTO``."""
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("RegisterAsset")
        proto = await self._call(
            "RegisterAsset",
            connector_pb2.ConnectorRegisterAssetRequest(base=build_request_base(_DEFAULT_SN), asset=asset),
        )
        return self._unwrap("RegisterAsset", proto, "asset")

    async def deregister_asset(self, sn: str) -> None:
        validate_non_blank("sn", sn)
        logger.info("DeregisterAsset: sn=%s", sn)
        proto = await self._call("DeregisterAsset", build_request_base(sn))
        self._unwrap("DeregisterAsset", proto)

    async def update_asset(self, asset_id: str, asset, update_mask: list[str] | None = None):
        """``asset`` is an ``AssetProtoDTO``. Empty ``update_mask`` replaces every mutable field."""
        validate_non_blank("assetId", asset_id)
        from google.protobuf import field_mask_pb2
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN), "asset": asset, "asset_id": asset_id}
        if update_mask:
            kwargs["update_mask"] = field_mask_pb2.FieldMask(paths=update_mask)
        logger.info("UpdateAsset: id=%s", asset_id)
        proto = await self._call("UpdateAsset", connector_pb2.ConnectorUpdateAssetRequest(**kwargs))
        return self._unwrap("UpdateAsset", proto, "asset")

    async def update_sub_asset(self, sub_asset_id: str, sub_asset, update_mask: list[str] | None = None):
        """``sub_asset`` is a ``SubAssetProtoDTO``."""
        validate_non_blank("subAssetId", sub_asset_id)
        from google.protobuf import field_mask_pb2
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {
            "base": build_request_base(_DEFAULT_SN),
            "sub_asset": sub_asset,
            "sub_asset_id": sub_asset_id,
        }
        if update_mask:
            kwargs["update_mask"] = field_mask_pb2.FieldMask(paths=update_mask)
        logger.info("UpdateSubAsset: id=%s", sub_asset_id)
        proto = await self._call("UpdateSubAsset", connector_pb2.ConnectorUpdateSubAssetRequest(**kwargs))
        return self._unwrap("UpdateSubAsset", proto, "sub_asset")

    async def get_asset_by_sn(self, sn: str):
        validate_non_blank("sn", sn)
        logger.info("GetAssetBySn: sn=%s", sn)
        proto = await self._call("GetAssetBySn", build_request_base(sn))
        return self._unwrap("GetAssetBySn", proto, "asset")

    async def get_asset_by_id(self, asset_id: str):
        validate_non_blank("assetId", asset_id)
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("GetAssetById: id=%s", asset_id)
        proto = await self._call(
            "GetAssetById",
            connector_pb2.ConnectorGetAssetByIdRequest(base=build_request_base(_DEFAULT_SN), asset_id=asset_id),
        )
        return self._unwrap("GetAssetById", proto, "asset")

    async def get_sub_asset_by_sn(self, sn: str):
        validate_non_blank("sn", sn)
        logger.info("GetSubAssetBySn: sn=%s", sn)
        proto = await self._call("GetSubAssetBySn", build_request_base(sn))
        return self._unwrap("GetSubAssetBySn", proto, "sub_asset")

    # ------------------------------------------------------------------
    # Asset payloads
    # ------------------------------------------------------------------

    @staticmethod
    def _payload_owner(asset_id: str | None, sub_asset_id: str | None):
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        if asset_id:
            return connector_pb2.AssetPayloadOwner(asset_id=asset_id)
        if sub_asset_id:
            return connector_pb2.AssetPayloadOwner(sub_asset_id=sub_asset_id)
        raise ValueError("exactly one of asset_id/sub_asset_id is required")

    async def upsert_asset_payload(
        self,
        payload,
        asset_id: str | None = None,
        sub_asset_id: str | None = None,
        sub_asset_sn: str | None = None,
        update_mask: list[str] | None = None,
    ):
        """``payload`` is an ``AssetPayloadProtoDTO``. Empty ``update_mask`` means a full upsert."""
        from google.protobuf import field_mask_pb2
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {
            "base": build_request_base(_DEFAULT_SN),
            "payload": payload,
            "owner": self._payload_owner(asset_id, sub_asset_id),
        }
        if sub_asset_sn:
            kwargs["sub_asset_sn"] = sub_asset_sn
        if update_mask:
            kwargs["update_mask"] = field_mask_pb2.FieldMask(paths=update_mask)
        logger.info("UpsertAssetPayload")
        proto = await self._call("UpsertAssetPayload", connector_pb2.UpsertAssetPayloadRequest(**kwargs))
        return self._unwrap("UpsertAssetPayload", proto, "payload")

    async def list_asset_payloads(self, asset_id: str | None = None, sub_asset_id: str | None = None) -> list:
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("ListAssetPayloads")
        proto = await self._call(
            "ListAssetPayloads",
            connector_pb2.ListAssetPayloadsRequest(
                base=build_request_base(_DEFAULT_SN), owner=self._payload_owner(asset_id, sub_asset_id)
            ),
        )
        return list(self._unwrap("ListAssetPayloads", proto, "payloads"))

    async def delete_asset_payload(self, payload_id: str, asset_id: str | None = None, sub_asset_id: str | None = None):
        validate_non_blank("payloadId", payload_id)
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("DeleteAssetPayload: id=%s", payload_id)
        proto = await self._call(
            "DeleteAssetPayload",
            connector_pb2.DeleteAssetPayloadRequest(
                base=build_request_base(_DEFAULT_SN),
                owner=self._payload_owner(asset_id, sub_asset_id),
                payload_id=payload_id,
            ),
        )
        return self._unwrap("DeleteAssetPayload", proto, "payload")

    # ------------------------------------------------------------------
    # Organization
    # ------------------------------------------------------------------

    async def get_organization(self, bind_code: str | None = None):
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if bind_code:
            kwargs["bind_code"] = bind_code
        logger.info("GetOrganization")
        proto = await self._call("GetOrganization", connector_pb2.ConnectorGetOrganizationRequest(**kwargs))
        return self._unwrap("GetOrganization", proto, "organization")

    # ------------------------------------------------------------------
    # Scheduler CRUD — identical wire messages to MissionAutonomyService's Scheduler RPCs.
    # ------------------------------------------------------------------

    async def get_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("GetScheduler: id=%s", scheduler_id)
        proto = await self._call(
            "GetScheduler",
            mission_autonomy_contracts_pb2.GetSchedulerRequest(
                base=build_request_base(_DEFAULT_SN), scheduler_id=scheduler_id
            ),
        )
        return proto_to_scheduler_response(proto)

    async def create_scheduler(self, scheduler: SchedulerDTO) -> SchedulerResponse:
        validate_non_blank("scheduler.name", scheduler.name)
        validate_non_blank("scheduler.cronExpression", scheduler.cron_expression)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateScheduler: name=%s", scheduler.name)
        proto = await self._call(
            "CreateScheduler",
            mission_autonomy_contracts_pb2.CreateSchedulerRequest(
                base=build_request_base(_DEFAULT_SN), scheduler=scheduler_to_proto(scheduler)
            ),
        )
        return proto_to_scheduler_response(proto)

    async def create_schedulers(self, schedulers: list[SchedulerDTO]) -> SchedulerResponse:
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("CreateSchedulers: count=%d", len(schedulers))
        proto = await self._call(
            "CreateSchedulers",
            mission_autonomy_contracts_pb2.CreateSchedulersRequest(
                base=build_request_base(_DEFAULT_SN), schedulers=[scheduler_to_proto(s) for s in schedulers]
            ),
        )
        return proto_to_scheduler_response(proto)

    async def update_scheduler(self, scheduler_id: str, scheduler: SchedulerDTO) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("UpdateScheduler: id=%s", scheduler_id)
        proto = await self._call(
            "UpdateScheduler",
            mission_autonomy_contracts_pb2.UpdateSchedulerRequest(
                base=build_request_base(_DEFAULT_SN), scheduler=scheduler_to_proto(scheduler), scheduler_id=scheduler_id
            ),
        )
        return proto_to_scheduler_response(proto)

    async def delete_scheduler(self, scheduler_id: str) -> SchedulerResponse:
        validate_non_blank("schedulerId", scheduler_id)
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteScheduler: id=%s", scheduler_id)
        proto = await self._call(
            "DeleteScheduler",
            mission_autonomy_contracts_pb2.DeleteSchedulerRequest(
                base=build_request_base(_DEFAULT_SN), scheduler_id=scheduler_id
            ),
        )
        return proto_to_scheduler_response(proto)

    async def delete_schedulers(self, scheduler_ids: list[str]) -> SchedulerResponse:
        from zqnt_utils.generated.zqnt import mission_autonomy_contracts_pb2  # type: ignore[import]

        logger.info("DeleteSchedulers: count=%d", len(scheduler_ids))
        proto = await self._call(
            "DeleteSchedulers",
            mission_autonomy_contracts_pb2.DeleteSchedulersRequest(
                base=build_request_base(_DEFAULT_SN), scheduler_ids=list(scheduler_ids)
            ),
        )
        return proto_to_scheduler_response(proto)

    # ------------------------------------------------------------------
    # Policies / technical config
    # ------------------------------------------------------------------

    async def get_active_policies_by_type(self, policy_type: str) -> list:
        validate_non_blank("policyType", policy_type)
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("GetActivePoliciesByType: type=%s", policy_type)
        proto = await self._call(
            "GetActivePoliciesByType",
            connector_pb2.ConnectorGetPoliciesRequest(base=build_request_base(_DEFAULT_SN), policy_type=policy_type),
        )
        result = self._unwrap("GetActivePoliciesByType", proto, "policy_list")
        return list(result.policies)

    async def get_all_active_policies(self) -> list:
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("GetAllActivePolicies")
        proto = await self._call(
            "GetAllActivePolicies", connector_pb2.ConnectorGetAllPoliciesRequest(base=build_request_base(_DEFAULT_SN))
        )
        result = self._unwrap("GetAllActivePolicies", proto, "policy_list")
        return list(result.policies)

    async def get_technical_configs(self, scope: str | None = None, scope_target: str | None = None) -> list:
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if scope:
            kwargs["scope"] = scope
        if scope_target:
            kwargs["scope_target"] = scope_target
        logger.info("GetTechnicalConfigs")
        proto = await self._call("GetTechnicalConfigs", connector_pb2.ConnectorGetConfigsRequest(**kwargs))
        result = self._unwrap("GetTechnicalConfigs", proto, "config_list")
        return list(result.configs)

    # ------------------------------------------------------------------
    # Skill Registry
    # ------------------------------------------------------------------

    async def observe_skill_contract(self, contract):
        """Upsert ``contract`` (a ``SkillContractProtoDTO``) — new for a never-seen
        (command_id, schema_version) pair, or refreshed content/last-seen for one already known."""
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("ObserveSkillContract: command_id=%s", getattr(contract, "command_id", None))
        proto = await self._call(
            "ObserveSkillContract",
            connector_pb2.UpsertSkillContractRequest(base=build_request_base(_DEFAULT_SN), contract=contract),
        )
        return self._unwrap("ObserveSkillContract", proto, "contract")

    async def list_skill_contracts(self, status=None, command_id: str | None = None) -> list:
        """``status`` is a ``SkillContractStatus`` enum value (int). ``command_id``, when set,
        returns that command's full version history instead of the whole registry."""
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        kwargs: dict[str, Any] = {"base": build_request_base(_DEFAULT_SN)}
        if status is not None:
            kwargs["status"] = status
        if command_id:
            kwargs["command_id"] = command_id
        logger.info("ListSkillContracts")
        proto = await self._call("ListSkillContracts", connector_pb2.ListSkillContractsRequest(**kwargs))
        return list(self._unwrap("ListSkillContracts", proto, "contracts"))

    async def set_skill_contract_status(self, contract_id: str, status):
        """``status`` is a ``SkillContractStatus`` enum value (int)."""
        validate_non_blank("id", contract_id)
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("SetSkillContractStatus: id=%s", contract_id)
        proto = await self._call(
            "SetSkillContractStatus",
            connector_pb2.SetSkillContractStatusRequest(
                base=build_request_base(_DEFAULT_SN), id=contract_id, status=status
            ),
        )
        return self._unwrap("SetSkillContractStatus", proto, "contract")

    async def set_skill_contract_permissions(self, contract_id: str, required_permissions: list[str]):
        """Full replacement, not a merge. Declarative only — nothing currently enforces this."""
        validate_non_blank("id", contract_id)
        from zqnt_utils.generated.zqnt import connector_pb2  # type: ignore[import]

        logger.info("SetSkillContractPermissions: id=%s", contract_id)
        proto = await self._call(
            "SetSkillContractPermissions",
            connector_pb2.SetSkillContractPermissionsRequest(
                base=build_request_base(_DEFAULT_SN), id=contract_id, required_permissions=list(required_permissions)
            ),
        )
        return self._unwrap("SetSkillContractPermissions", proto, "contract")

    # ------------------------------------------------------------------
    # Asset monitoring — server-streaming
    # ------------------------------------------------------------------

    def asset_monitoring(self, sn: str, on_data: OnAssetMonitoring, on_error: OnError | None = None) -> StreamHandle:
        """Subscribe to asset-monitoring updates. ``on_data`` receives the raw
        ``AssetMonitoringResponse`` proto frame; reconnects transparently on transient gRPC
        errors, same policy as :meth:`LiveDataClient.stream_telemetry`."""
        validate_non_blank("sn", sn)
        handle = StreamHandle()
        task = asyncio.create_task(
            self._asset_monitoring_loop(sn, on_data, on_error, handle), name=f"connector-monitoring-{sn}"
        )
        handle._bind(task)
        return handle

    async def _asset_monitoring_loop(self, sn: str, on_data, on_error, handle: StreamHandle) -> None:
        attempt = 0
        max_attempts = self._resilience.max_retry_attempts
        base_delay = self._resilience.retry_delay_millis / 1000.0

        while not handle.is_stopped:
            try:
                logger.info("AssetMonitoring connect: sn=%s", sn)
                stream = self._stub.AssetMonitoring(build_request_base(sn))
                async for frame in stream:
                    if handle.is_stopped:
                        break
                    attempt = 0
                    try:
                        result = on_data(frame)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:  # noqa: BLE001 - user callback shouldn't kill stream
                        logger.exception("AssetMonitoring on_data callback raised")
                if handle.is_stopped:
                    return
                logger.info("AssetMonitoring ended cleanly; reconnecting")
            except asyncio.CancelledError:
                logger.info("AssetMonitoring cancelled")
                return
            except grpc.aio.AioRpcError as exc:
                if handle.is_stopped:
                    return
                code = exc.code()
                logger.warning("AssetMonitoring gRPC error: %s (%s)", code.name if code else "?", exc.details())
                if code not in _RETRYABLE_CODES:
                    await _maybe_call(on_error, explain(exc))
                    return
            except Exception as exc:  # noqa: BLE001
                if handle.is_stopped:
                    return
                logger.exception("AssetMonitoring unexpected error")
                await _maybe_call(on_error, exc)
                return

            attempt += 1
            if attempt > max_attempts:
                logger.error("AssetMonitoring: exceeded %d reconnect attempts; giving up", max_attempts)
                await _maybe_call(
                    on_error, RuntimeError(f"asset_monitoring exceeded {max_attempts} reconnect attempts")
                )
                return
            delay = min(base_delay * attempt, _MAX_BACKOFF_SECONDS)
            logger.info("AssetMonitoring reconnect attempt %d in %.2fs", attempt, delay)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

    # ------------------------------------------------------------------
    # Batch upload sessions
    # ------------------------------------------------------------------

    def store_telemetry_batch(self) -> ConnectorBatchSession:
        """Open a client-streaming session for ``StoreTelemetryBatch``.

        Send raw ``ConnectorStoreTelemetryRequest`` proto messages via :meth:`ConnectorBatchSession.send`.
        """
        return ConnectorBatchSession("StoreTelemetryBatch", self._stub, self._timeout)

    def store_detection_batch(self) -> ConnectorBatchSession:
        """Open a client-streaming session for ``StoreDetectionBatch``.

        Send raw ``ConnectorStoreDetectionRequest`` proto messages via :meth:`ConnectorBatchSession.send`.
        """
        return ConnectorBatchSession("StoreDetectionBatch", self._stub, self._timeout)

    def store_notification_batch(self) -> ConnectorBatchSession:
        """Open a client-streaming session for ``StoreNotificationBatch``.

        Send raw ``ProduceNotificationRequest`` proto messages via :meth:`ConnectorBatchSession.send`.
        """
        return ConnectorBatchSession("StoreNotificationBatch", self._stub, self._timeout)


async def _maybe_call(cb: Any, exc: BaseException) -> None:
    if cb is None:
        return
    try:
        result = cb(exc)
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001
        logger.exception("on_error callback raised")

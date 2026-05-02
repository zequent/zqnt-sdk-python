"""RemoteControl sub-client – unary RPCs over RemoteControlService.

Mirrors ``com.zqnt.sdk.client.remotecontrol.application.RemoteControl``.
Manual-control client-streaming session is added in a later phase.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import grpc.aio

from ..config.resilience import ResilienceConfig
from ..grpc_.resilience import GrpcResilience
from ..models._converters import (
    build_coordinates,
    build_request_base,
    proto_to_response,
)
from ..models._validation import (
    validate_coordinates,
    validate_non_blank,
    validate_sn,
)
from ..models.common import RemoteControlResponse
from ..models.remote_control import (
    DockOperationRequest,
    GoToRequest,
    LookAtRequest,
    ManualControlRequest,
    ReturnToHomeRequest,
    TakeoffRequest,
)

if TYPE_CHECKING:
    from .manual_control_session import ManualControlInputSession

logger = logging.getLogger(__name__)


class RemoteControlClient:
    """Async client for the ``RemoteControlService`` gRPC API."""

    def __init__(
        self,
        channel: grpc.aio.Channel,
        resilience: ResilienceConfig,
    ) -> None:
        # Lazy import: stubs may not be generated yet.
        try:
            from ..generated import remote_control_pb2_grpc  # type: ignore[import]
        except ImportError as exc:  # pragma: no cover - generation step
            raise ImportError("Protobuf stubs not found. Run scripts/generate_protos.sh first.") from exc

        self._channel = channel
        self._resilience = resilience
        self._resilience_helper = GrpcResilience(resilience)
        self._stub = remote_control_pb2_grpc.RemoteControlServiceStub(channel)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _timeout(self) -> float:
        return float(self._resilience.request_timeout_seconds)

    # ------------------------------------------------------------------
    # Flight ops
    # ------------------------------------------------------------------

    async def takeoff(self, request: TakeoffRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("Takeoff: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlTakeOffRequest(
            base=build_request_base(request.sn),
            request=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        proto = await self._resilience_helper.execute(lambda: self._stub.TakeOff(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    async def go_to(self, request: GoToRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("GoTo: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlGoToRequest(
            base=build_request_base(request.sn),
            request=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        proto = await self._resilience_helper.execute(lambda: self._stub.GoTo(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    async def return_to_home(self, request: ReturnToHomeRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("ReturnToHome: sn=%s", request.sn)

        from ..generated import common_pb2, remote_control_pb2  # type: ignore[import]

        rth_kwargs: dict = {}
        if request.altitude is not None:
            rth_kwargs["altitude"] = request.altitude

        proto_request = remote_control_pb2.RemoteControlReturnToHomeRequest(
            base=build_request_base(request.sn),
            request=common_pb2.ReturnToHomeRequest(**rth_kwargs),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.ReturnToHome(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def look_at(self, request: LookAtRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("LookAt: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlLookAtRequest(
            base=build_request_base(request.sn),
            request=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        proto = await self._resilience_helper.execute(lambda: self._stub.LookAt(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    # ------------------------------------------------------------------
    # Manual control (unary)
    # ------------------------------------------------------------------

    async def enter_manual_control(self, request: ManualControlRequest) -> RemoteControlResponse:
        return await self._manual_control_call(request, enter=True)

    async def exit_manual_control(self, request: ManualControlRequest) -> RemoteControlResponse:
        return await self._manual_control_call(request, enter=False)

    async def _manual_control_call(self, request: ManualControlRequest, *, enter: bool) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_non_blank("clientId", request.client_id)
        validate_non_blank("userId", request.user_id)
        validate_non_blank("sessionId", request.session_id)
        logger.info(
            "%sManualControl: sn=%s",
            "Enter" if enter else "Exit",
            request.sn,
        )

        from ..generated import common_pb2, remote_control_pb2  # type: ignore[import]

        mc_kwargs: dict = {
            "clientId": request.client_id,
            "userId": request.user_id,
            "sessionId": request.session_id,
        }
        if request.reason is not None:
            mc_kwargs["reason"] = request.reason

        proto_request = remote_control_pb2.RemoteControlManualControlRequest(
            base=build_request_base(request.sn),
            request=common_pb2.ManualControlRequest(**mc_kwargs),
        )
        rpc = self._stub.EnterManualControl if enter else self._stub.ExitManualControl
        proto = await self._resilience_helper.execute(lambda: rpc(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    # ------------------------------------------------------------------
    # Manual control – client-streaming session
    # ------------------------------------------------------------------

    def start_manual_control_input(self, sn: str) -> "ManualControlInputSession":
        """Open a client-streaming session for ``ManualControlInput``.

        The returned session can be used as an ``async with`` block::

            async with rc.start_manual_control_input(sn) as session:
                await session.send_input(ManualControlInput(roll=0.1))
                response = await session.complete()
        """
        validate_sn(sn)
        from .manual_control_session import ManualControlInputSession

        return ManualControlInputSession(sn=sn, stub=self._stub, timeout=self._timeout)

    # ------------------------------------------------------------------
    # Dock operations
    # ------------------------------------------------------------------

    async def open_cover(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("OpenCover: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlOpenCoverRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.OpenCover(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def close_cover(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("CloseCover: sn=%s, force=%s", request.sn, request.value)

        from ..generated import remote_control_pb2  # type: ignore[import]

        kwargs: dict = {"base": build_request_base(request.sn)}
        if request.value is not None:
            kwargs["force"] = request.value

        proto_request = remote_control_pb2.RemoteControlCloseCoverRequest(**kwargs)
        proto = await self._resilience_helper.execute(
            lambda: self._stub.CloseCover(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def start_charging(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("StartCharging: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlStartChargingRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StartCharging(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def stop_charging(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("StopCharging: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlStopChargingRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StopCharging(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    # ------------------------------------------------------------------
    # Asset operations
    # ------------------------------------------------------------------

    async def reboot_asset(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("RebootAsset: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlRebootAssetRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.RebootAsset(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def boot_sub_asset(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("BootSubAsset: sn=%s, boot=%s", request.sn, request.value)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlBootSubAssetRequest(
            base=build_request_base(request.sn),
            boot=bool(request.value) if request.value is not None else False,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.BootSubAsset(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def debug_mode(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("DebugMode: sn=%s, enabled=%s", request.sn, request.value)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlDebugModeRequest(
            base=build_request_base(request.sn),
            enabled=bool(request.value) if request.value is not None else False,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.EnterOrCloseRemoteDebugMode(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    async def change_ac_mode(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("ChangeAcMode: sn=%s", request.sn)

        from ..generated import remote_control_pb2  # type: ignore[import]

        proto_request = remote_control_pb2.RemoteControlChangeAcModeRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.ChangeAcMode(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

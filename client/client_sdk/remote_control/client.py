"""RemoteControl sub-client – unary RPCs over RemoteControlService.

Mirrors ``com.zqnt.sdk.client.remotecontrol.application.RemoteControl``.
Manual-control client-streaming session is added in a later phase.
"""

from __future__ import annotations

import functools
import logging
import warnings
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


def _deprecated(command_id: str):
    def decorate(method):
        @functools.wraps(method)
        async def call(self, *args, **kwargs):
            warnings.warn(
                f"RemoteControlClient.{method.__name__} is the 2.x typed call; on Zequent 3.0 use "
                f'client.commands.execute_command(asset_sn, "{command_id}", params)',
                DeprecationWarning,
                stacklevel=2,
            )
            return await method(self, *args, **kwargs)

        return call

    return decorate


class RemoteControlClient:
    """Async client for the 2.x ``RemoteControlService`` gRPC API, kept for 2.x platforms.

    Every typed command is deprecated: on a 3.0 platform use ``client.commands.execute_command``
    with the command id and params (see MIGRATION.md). :meth:`start_manual_control_input` is not
    deprecated; it stays the way to fly by hand.
    """

    def __init__(
        self,
        channel: grpc.aio.Channel,
        resilience: ResilienceConfig,
    ) -> None:
        # Lazy import: stubs may not be generated yet.
        try:
            from zqnt_utils.generated.zqnt import remote_control_pb2_grpc  # type: ignore[import]
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

    @_deprecated("flight.takeoff")
    async def takeoff(self, request: TakeoffRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("Takeoff: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.CoordinateCommandRequest(
            base=build_request_base(request.sn),
            coordinate=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        proto = await self._resilience_helper.execute(lambda: self._stub.TakeOff(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    @_deprecated("navigation.go_to")
    async def go_to(self, request: GoToRequest, *, no_fly_zone_override: bool = False) -> RemoteControlResponse:
        """Fly to a coordinate.

        ``no_fly_zone_override=True`` flies straight through a HARD_BLOCK or REQUIRE_APPROVAL
        no-fly zone that would otherwise refuse the fly-to. The platform honours it only for an
        organization admin or a system admin (by the caller's own token) and refuses it for
        anybody else; it is sent only when asked for.
        """
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("GoTo: sn=%s, no_fly_zone_override=%s", request.sn, no_fly_zone_override)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.CoordinateCommandRequest(
            base=build_request_base(request.sn),
            coordinate=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        if no_fly_zone_override:
            proto_request.no_fly_zone_override = True
        proto = await self._resilience_helper.execute(lambda: self._stub.GoTo(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    @_deprecated("flight.return_to_home")
    async def return_to_home(self, request: ReturnToHomeRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("ReturnToHome: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        rth_kwargs: dict = {}
        if request.altitude is not None:
            rth_kwargs["altitude"] = request.altitude

        proto_request = common_pb2.ReturnToHomeCommandRequest(
            base=build_request_base(request.sn),
            request=common_pb2.ReturnToHomeRequest(**rth_kwargs),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.ReturnToHome(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("gimbal.look_at")
    async def look_at(self, request: LookAtRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        validate_coordinates(request.latitude, request.longitude, request.altitude)
        logger.info("LookAt: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.LookAtCommandRequest(
            base=build_request_base(request.sn),
            coordinate=build_coordinates(request.latitude, request.longitude, request.altitude),
        )
        proto = await self._resilience_helper.execute(lambda: self._stub.LookAt(proto_request, timeout=self._timeout))
        return proto_to_response(proto, request.sn)

    # ------------------------------------------------------------------
    # Manual control (unary)
    # ------------------------------------------------------------------

    @_deprecated("flight.manual.enter")
    async def enter_manual_control(self, request: ManualControlRequest) -> RemoteControlResponse:
        return await self._manual_control_call(request, enter=True)

    @_deprecated("flight.manual.exit")
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

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        mc_kwargs: dict = {
            "client_id": request.client_id,
            "user_id": request.user_id,
            "session_id": request.session_id,
        }
        if request.reason is not None:
            mc_kwargs["reason"] = request.reason

        proto_request = common_pb2.ManualControlCommandRequest(
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

    @_deprecated("dock.open_cover")
    async def open_cover(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("OpenCover: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.EmptyCommandRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.OpenCover(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("dock.close_cover")
    async def close_cover(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("CloseCover: sn=%s, force=%s", request.sn, request.value)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        kwargs: dict = {"base": build_request_base(request.sn)}
        if request.value is not None:
            kwargs["force"] = request.value

        proto_request = common_pb2.CloseCoverCommandRequest(**kwargs)
        proto = await self._resilience_helper.execute(
            lambda: self._stub.CloseCover(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("dock.start_charging")
    async def start_charging(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("StartCharging: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.EmptyCommandRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StartCharging(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("dock.stop_charging")
    async def stop_charging(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("StopCharging: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.EmptyCommandRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.StopCharging(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    # ------------------------------------------------------------------
    # Asset operations
    # ------------------------------------------------------------------

    @_deprecated("asset.reboot")
    async def reboot_asset(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("RebootAsset: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.EmptyCommandRequest(
            base=build_request_base(request.sn),
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.RebootAsset(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("asset.boot_sub_asset")
    async def boot_sub_asset(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("BootSubAsset: sn=%s, boot=%s", request.sn, request.value)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        # BootSubAsset uses the generic ToggleCommandRequest (field `enabled`), same as edge.proto's
        # own BootSubAsset RPC — despite there also being an unused BootSubAssetCommandRequest
        # (field `boot_up`) in the schema that neither service's BootSubAsset RPC actually takes.
        proto_request = common_pb2.ToggleCommandRequest(
            base=build_request_base(request.sn),
            enabled=bool(request.value) if request.value is not None else False,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.BootSubAsset(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("asset.remote_debug")
    async def debug_mode(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("DebugMode: sn=%s, enabled=%s", request.sn, request.value)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        proto_request = common_pb2.ToggleCommandRequest(
            base=build_request_base(request.sn),
            enabled=bool(request.value) if request.value is not None else False,
        )
        proto = await self._resilience_helper.execute(
            # RPC renamed from EnterOrCloseRemoteDebugMode -> SetRemoteDebugMode.
            lambda: self._stub.SetRemoteDebugMode(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

    @_deprecated("asset.change_ac_mode")
    async def change_ac_mode(self, request: DockOperationRequest) -> RemoteControlResponse:
        validate_sn(request.sn)
        logger.info("ChangeAcMode: sn=%s", request.sn)

        from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

        # NOTE: ChangeAcModeCommandRequest now requires a `mode: AssetAirConditionerStateEnum`
        # (see asset.proto) that DockOperationRequest has no field for -- this was already the case
        # before this fix (the old proto message took no mode either), so this preserves the
        # existing (incomplete) behaviour rather than silently inventing a new one. Giving callers a
        # way to actually choose a mode needs a DockOperationRequest change, deliberately not done
        # here.
        proto_request = common_pb2.ChangeAcModeCommandRequest(
            base=build_request_base(request.sn),
            mode=common_pb2.AIR_CONDITIONER_IDLE,
        )
        proto = await self._resilience_helper.execute(
            lambda: self._stub.ChangeAcMode(proto_request, timeout=self._timeout)
        )
        return proto_to_response(proto, request.sn)

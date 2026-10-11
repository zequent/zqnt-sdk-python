"""Stick input for one asset over ``zqnt.control.v3.RemoteControlService.StreamManualControl``."""

from __future__ import annotations

import asyncio

import grpc
import grpc.aio
from zqnt_api.generated.zqnt.common.v3 import common_pb2
from zqnt_api.generated.zqnt.control.v3 import remote_control_service_pb2 as control_pb2
from zqnt_api.generated.zqnt.edge.v3 import edge_adapter_service_pb2 as edge_pb2

from .errors import CommandError


class ManualControlStream:
    """A stick-input session on one asset: roll, pitch, yaw and throttle from -1 to 1, and an
    optional gimbal pitch. The asset has to be in manual control first (``flight.manual.enter``).

    Use it as an ``async with`` block: leaving it normally ends the session and waits for the
    platform's answer (:attr:`accepted_inputs`), leaving it with an exception aborts the stream.
    :meth:`send` and :meth:`close` raise :class:`CommandError` when the platform refused the
    session (no adapter reachable for the asset, an asset of another organization) or the adapter
    dropped it; :meth:`send` after :meth:`close` raises ``RuntimeError``.
    """

    def __init__(self, asset_sn: str, call: grpc.aio.StreamUnaryCall) -> None:
        self._asset_sn = asset_sn
        self._call = call
        self._named = False
        self._closed = False
        self._accepted_inputs: int | None = None
        self._lock = asyncio.Lock()

    @property
    def asset_sn(self) -> str:
        return self._asset_sn

    @property
    def accepted_inputs(self) -> int | None:
        """The number of inputs the platform passed on to the asset; ``None`` until :meth:`close`."""
        return self._accepted_inputs

    async def __aenter__(self) -> ManualControlStream:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.cancel()
            return
        await self.close()

    async def send(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        throttle: float = 0.0,
        *,
        gimbal_pitch: float | None = None,
    ) -> None:
        stick = edge_pb2.ManualControlInput(roll=roll, pitch=pitch, yaw=yaw, throttle=throttle)
        if gimbal_pitch is not None:
            stick.gimbal_pitch = gimbal_pitch
        async with self._lock:
            if self._closed:
                raise RuntimeError(f"the manual control stream on {self._asset_sn} is closed")
            request = control_pb2.StreamManualControlRequest(input=stick)
            if not self._named:
                request.asset.CopyFrom(common_pb2.AssetRef(sn=self._asset_sn))
                self._named = True
            try:
                await self._call.write(request)
            except grpc.aio.AioRpcError as exc:
                self._closed = True
                raise CommandError.from_exception(exc) from exc
            except asyncio.InvalidStateError:
                self._closed = True
                await self._answer()
                raise RuntimeError(f"the platform ended manual control on {self._asset_sn}") from None

    async def close(self) -> int:
        """Ends the session and returns the number of inputs the platform passed on to the asset."""
        async with self._lock:
            if self._accepted_inputs is not None:
                return self._accepted_inputs
            if not self._closed:
                self._closed = True
                try:
                    await self._call.done_writing()
                except (grpc.aio.AioRpcError, asyncio.InvalidStateError):
                    pass
            self._accepted_inputs = await self._answer()
            return self._accepted_inputs

    def cancel(self) -> None:
        """Aborts the stream without waiting for an answer."""
        self._closed = True
        self._call.cancel()

    async def _answer(self) -> int:
        try:
            response = await self._call
        except grpc.aio.AioRpcError as exc:
            raise CommandError.from_exception(exc) from exc
        if response.HasField("error"):
            error = response.error
            raise CommandError(
                error.message or f"manual control on {self._asset_sn} failed",
                category=error.category or common_pb2.ERROR_CATEGORY_SERVICE,
                code=error.code,
                retryable=error.retryable,
            )
        return response.accepted_inputs

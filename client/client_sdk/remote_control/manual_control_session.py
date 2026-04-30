"""Manual control client-streaming session.

Mirrors :java:`com.zqnt.sdk.client.remotecontrol.application.ManualControlInputSession`
adapted for ``asyncio`` + ``grpc.aio``. The session opens a client-streaming
RPC backed by an :class:`asyncio.Queue`; user code calls
:meth:`send_input` to push commands and :meth:`complete` to close the
stream and await the server's final response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import grpc.aio

from ..models._converters import build_request_base, proto_to_response
from ..models.common import RemoteControlResponse
from ..models.remote_control_input import ManualControlInput

logger = logging.getLogger(__name__)


# Sentinel pushed onto the queue to signal end-of-stream to the request iterator.
_CLOSE = object()


class ManualControlInputSession:
    """Client-streaming session for ``RemoteControlService.ManualControlInput``.

    Construct via :meth:`RemoteControlClient.start_manual_control_input`,
    then call :meth:`send_input` repeatedly and finish with :meth:`complete`
    (or :meth:`complete_with_error` on failure). Always call :meth:`close`
    in a ``finally`` block, or use the session as an ``async with`` context
    manager which closes automatically.
    """

    __slots__ = ("_sn", "_stub", "_timeout", "_queue", "_call", "_closed", "_completed")

    def __init__(
        self,
        sn: str,
        stub: Any,
        timeout: float,
    ) -> None:
        self._sn = sn
        self._stub = stub
        self._timeout = timeout
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._call = None
        self._closed = False
        self._completed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ManualControlInputSession":
        await self._open()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc is not None and not self._completed:
            await self.complete_with_error(exc)
        await self.close()

    async def _open(self) -> None:
        if self._call is not None:
            return
        logger.info("ManualControlInput session opened: sn=%s", self._sn)
        self._call = self._stub.ManualControlInput(
            self._request_iterator(), timeout=self._timeout
        )

    async def _request_iterator(self):
        from ..generated import common_pb2, remote_control_pb2  # type: ignore[import]

        while True:
            item = await self._queue.get()
            if item is _CLOSE:
                return
            inp: ManualControlInput = item
            inp_kwargs: dict[str, Any] = {}
            if inp.roll is not None:
                inp_kwargs["roll"] = inp.roll
            if inp.pitch is not None:
                inp_kwargs["pitch"] = inp.pitch
            if inp.yaw is not None:
                inp_kwargs["yaw"] = inp.yaw
            if inp.throttle is not None:
                inp_kwargs["throttle"] = inp.throttle
            if inp.gimbal_pitch is not None:
                inp_kwargs["gimbalPitch"] = inp.gimbal_pitch
            yield remote_control_pb2.RemoteControlManualControlInputRequest(
                base=build_request_base(self._sn),
                request=common_pb2.ManualControlInput(**inp_kwargs),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def send_input(self, input: ManualControlInput) -> None:
        """Queue a single :class:`ManualControlInput` for transmission."""
        if self._closed:
            raise RuntimeError("ManualControlInputSession is closed")
        if self._call is None:
            await self._open()
        await self._queue.put(input)

    async def complete(self) -> RemoteControlResponse:
        """Close the stream and await the server's final response."""
        if self._completed:
            raise RuntimeError("ManualControlInputSession already completed")
        if self._call is None:
            await self._open()
        self._completed = True
        await self._queue.put(_CLOSE)
        try:
            proto = await self._call
        finally:
            self._closed = True
        logger.info("ManualControlInput session completed: sn=%s", self._sn)
        return proto_to_response(proto, self._sn)

    async def complete_with_error(self, error: BaseException) -> None:
        """Cancel the stream after a local error."""
        if self._completed:
            return
        self._completed = True
        logger.warning(
            "ManualControlInput session completing with error: sn=%s err=%r",
            self._sn,
            error,
        )
        if self._call is not None:
            try:
                self._call.cancel()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error cancelling ManualControlInput call")
        await self._queue.put(_CLOSE)
        self._closed = True

    async def close(self) -> None:
        """Idempotent cleanup. Safe to call multiple times."""
        if self._closed:
            return
        self._closed = True
        if not self._completed:
            self._completed = True
            await self._queue.put(_CLOSE)
            if self._call is not None:
                try:
                    self._call.cancel()
                except Exception:  # pragma: no cover - defensive
                    pass
        logger.info("ManualControlInput session closed: sn=%s", self._sn)

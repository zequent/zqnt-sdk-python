"""Generic client-streaming batch session for Connector's telemetry/detection/notification
batch-upload RPCs.

Mirrors :java:`com.zqnt.sdk.client.connector.domains.ConnectorBatchSession` adapted for
``asyncio`` + ``grpc.aio``, using the same queue-backed request-iterator approach as
:class:`client_sdk.remote_control.manual_control_session.ManualControlInputSession`. Items are
raw generated proto request messages (``ConnectorStoreTelemetryRequest``,
``ConnectorStoreDetectionRequest``, ``ProduceNotificationRequest``) — the caller builds each one;
this class only owns the stream lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel pushed onto the queue to signal end-of-stream to the request iterator.
_CLOSE = object()


class ConnectorBatchSession:
    """Client-streaming session for one of Connector's ``Store*Batch`` RPCs.

    Construct via :meth:`ConnectorClient.store_telemetry_batch` /
    :meth:`store_detection_batch` / :meth:`store_notification_batch`, then call :meth:`send`
    repeatedly and finish with :meth:`complete` (or :meth:`cancel` on failure). Always call
    :meth:`close` in a ``finally`` block, or use the session as an ``async with`` context
    manager, which completes automatically on clean exit.
    """

    __slots__ = ("_rpc_name", "_stub", "_timeout", "_queue", "_call", "_completed", "_closed")

    def __init__(self, rpc_name: str, stub: Any, timeout: float) -> None:
        self._rpc_name = rpc_name
        self._stub = stub
        self._timeout = timeout
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._call = None
        self._completed = False
        self._closed = False

    async def __aenter__(self) -> "ConnectorBatchSession":
        self._open()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc is not None and not self._completed:
            await self.cancel(exc)
        else:
            await self.close()

    def _open(self) -> None:
        if self._call is not None:
            return
        logger.info("%s session opened", self._rpc_name)
        rpc = getattr(self._stub, self._rpc_name)
        self._call = rpc(self._request_iterator(), timeout=self._timeout)

    async def _request_iterator(self):
        while True:
            item = await self._queue.get()
            if item is _CLOSE:
                return
            yield item

    @property
    def is_completed(self) -> bool:
        return self._completed

    def send(self, request) -> None:
        """Queue a raw proto request message for transmission."""
        if self._completed:
            raise RuntimeError(f"{self._rpc_name} session is already completed")
        self._open()
        self._queue.put_nowait(request)

    async def complete(self):
        """Close the stream and await the server's final ``ConnectorResponse``."""
        if self._completed:
            raise RuntimeError(f"{self._rpc_name} session already completed")
        self._open()
        self._completed = True
        await self._queue.put(_CLOSE)
        try:
            proto = await self._call
        finally:
            self._closed = True
        logger.info("%s session completed", self._rpc_name)
        return proto

    async def cancel(self, error: BaseException | None = None) -> None:
        """Abort the stream after a local error."""
        if self._completed:
            return
        self._completed = True
        logger.warning("%s session cancelled: err=%r", self._rpc_name, error)
        if self._call is not None:
            try:
                self._call.cancel()
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error cancelling %s call", self._rpc_name)
        await self._queue.put(_CLOSE)
        self._closed = True

    async def close(self) -> None:
        """Idempotent cleanup. Safe to call multiple times."""
        if self._closed:
            return
        if not self._completed:
            await self.complete()
        self._closed = True
        logger.info("%s session closed", self._rpc_name)

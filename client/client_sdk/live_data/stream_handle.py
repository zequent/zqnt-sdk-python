"""Async-friendly stream handle returned by :meth:`LiveDataClient.stream_telemetry`.

Mirrors :java:`com.zqnt.sdk.client.livedata.domains.StreamHandle` adapted for
``asyncio``. The handle owns the background task that pumps telemetry frames
into the user-supplied callback and transparently reconnects on transient
gRPC errors.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class StreamHandle:
    """Handle for an active server-streaming subscription.

    Use :meth:`stop` to gracefully terminate the background reconnect loop,
    or use the handle as an ``async with`` context manager.
    """

    __slots__ = ("_stopped", "_task", "_done")

    def __init__(self) -> None:
        self._stopped = False
        self._task: asyncio.Task | None = None
        self._done = asyncio.Event()

    # ------------------------------------------------------------------
    # Internal — set by LiveDataClient.stream_telemetry
    # ------------------------------------------------------------------

    def _bind(self, task: asyncio.Task) -> None:
        self._task = task
        task.add_done_callback(lambda _t: self._done.set())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    async def stop(self) -> None:
        """Signal the stream to stop and wait for cleanup."""
        if self._stopped:
            return
        self._stopped = True
        logger.info("StreamHandle.stop requested")
        if self._task is not None and not self._task.done():
            self._task.cancel()
        await self._done.wait()

    async def wait_closed(self) -> None:
        """Block until the underlying task completes."""
        await self._done.wait()

    async def __aenter__(self) -> "StreamHandle":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

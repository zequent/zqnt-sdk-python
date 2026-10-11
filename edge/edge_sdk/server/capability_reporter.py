"""
Reports an adapter's capabilities to the platform on start and whenever they change.

Changes (a registration, a declared telemetry field, :meth:`EdgeAdapter.notify_capabilities_changed`)
are collected for a moment and sent once per asset. A failed report is retried later.
"""

from __future__ import annotations

import asyncio
import logging

from ..adapter.base import EdgeAdapter
from ..client.edge_gateway import EdgeGatewayClient

logger = logging.getLogger(__name__)


class CapabilityReporter:
    DEBOUNCE_SECONDS = 0.5
    RETRY_SECONDS = 30.0

    def __init__(self, adapter: EdgeAdapter, gateway: EdgeGatewayClient) -> None:
        self._adapter = adapter
        self._gateway = gateway
        self._pending: set[str] = set()
        self._reported: set[str] = set()
        self._task: asyncio.Task | None = None
        self._started = False

    @property
    def reported(self) -> set[str]:
        return set(self._reported)

    async def start(self) -> None:
        if not self._started:
            self._started = True
            self._adapter.add_capability_listener(self._changed)
        self._changed(None)

    async def stop(self) -> None:
        self._started = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def flush(self) -> None:
        """Wait until every pending report has been attempted (tests, shutdown)."""
        while self._task is not None and not self._task.done():
            await asyncio.shield(self._task)

    def _changed(self, sn: str | None) -> None:
        if not self._started:
            return
        if sn is None:
            self._pending.update(self._reported)
            self._pending.update(self._adapter.reported_asset_sns())
        else:
            self._pending.add(sn)
        self._schedule(self.DEBOUNCE_SECONDS)

    def _schedule(self, delay: float) -> None:
        if not self._pending or (self._task is not None and not self._task.done()):
            return
        try:
            self._task = asyncio.get_running_loop().create_task(self._report_after(delay), name="capability-report")
        except RuntimeError:
            logger.debug("no running loop; capabilities are reported on start")

    async def _report_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        failed: set[str] = set()
        while self._pending:
            sn = self._pending.pop()
            try:
                caps = await self._adapter.get_capabilities(sn=sn, asset_id=None)
                revision = await self._gateway.report_capabilities(caps)
                self._reported.add(sn)
                logger.info("capabilities of %s reported (revision %s)", sn, revision or "-")
            except Exception as exc:
                logger.warning("capabilities of %s not reported (%s: %s)", sn, type(exc).__name__, exc)
                failed.add(sn)
        if failed and self._started:
            self._pending.update(failed)
            self._task = asyncio.get_running_loop().create_task(
                self._report_after(self.RETRY_SECONDS), name="capability-report-retry"
            )

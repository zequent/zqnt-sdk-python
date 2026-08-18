"""
Shared test fixtures.

Design decisions:
- No gRPC mocks: the integration tests spin up a real in-process server.
  This gives confidence that protobuf serialisation, servicer routing, and
  status codes all work exactly as they would in production.
- fakeredis replaces a real Redis instance so registration tests run without
  any external infrastructure.
"""

import asyncio
import socket
from contextlib import suppress
from datetime import datetime, timezone

import pytest_asyncio

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse, EdgeServer
from edge_sdk.models.common import Capabilities, CustomCommandRequest, CustomCommandResponse, RequestContext

# ---------------------------------------------------------------------------
# Minimal adapter used across all tests
# ---------------------------------------------------------------------------


class _TestAdapter(EdgeAdapter):
    """
    A minimal adapter that implements only the operations needed for tests.
    Anything not overridden intentionally returns ``not_supported``.
    """

    async def get_capabilities(self, sn: str, asset_id: str | None) -> Capabilities:
        return self._auto_capabilities(sn, AssetType.SENSOR)

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        return EdgeResponse.ok(ctx.tid, ctx.sn, f"started:{task_id}", external_execution_id=f"vendor-{task_id}")

    async def stop_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        return EdgeResponse.ok(ctx.tid, ctx.sn, f"stopped:{task_id}")

    async def send_custom_command(self, ctx: RequestContext, request: CustomCommandRequest) -> CustomCommandResponse:
        return CustomCommandResponse.ok(
            ctx.tid,
            ctx.sn,
            request.command_type,
            external_execution_id=f"vendor-{request.command_type}",
        )


class _CrashingAdapter(_TestAdapter):
    """Adapter that deliberately raises exceptions – for error-handling tests."""

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        raise RuntimeError("hardware exploded")


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
def test_adapter() -> _TestAdapter:
    return _TestAdapter()


@pytest_asyncio.fixture
def crashing_adapter() -> _CrashingAdapter:
    return _CrashingAdapter()


@pytest_asyncio.fixture
async def server_port(test_adapter):
    """
    Start a real EdgeServer on a random port; yield the port number.
    The server is stopped after the test completes.
    """
    port = _free_port()
    server = EdgeServer(adapter=test_adapter, port=port)
    task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)  # give the server time to bind
    yield port
    await server.stop(grace=0)
    with suppress(asyncio.CancelledError, Exception):
        await task


@pytest_asyncio.fixture
async def crashing_server_port(crashing_adapter):
    """Same as server_port but uses the crashing adapter."""
    port = _free_port()
    server = EdgeServer(adapter=crashing_adapter, port=port)
    task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.05)
    yield port
    await server.stop(grace=0)
    with suppress(asyncio.CancelledError, Exception):
        await task


def make_ctx(tid: str = "test-tid", sn: str = "TEST-001") -> RequestContext:
    return RequestContext(tid=tid, sn=sn, timestamp=datetime.now(tz=timezone.utc))

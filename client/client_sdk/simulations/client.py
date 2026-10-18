"""Simulated runs of an Application over ``zqnt.application_simulation.v3.SimulationService``."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import grpc.aio
from zqnt_api.generated.zqnt.application_simulation.v3 import (
    application_simulation_pb2,
    application_simulation_pb2_grpc,
)
from zqnt_api.generated.zqnt.common.v3 import common_pb2

from ..commands.errors import CommandError
from ..config.resilience import ResilienceConfig
from ..grpc_.resilience import GrpcResilience

FINAL_SIMULATION_STATUSES = frozenset(
    {
        application_simulation_pb2.SIMULATION_STATUS_SUCCEEDED,
        application_simulation_pb2.SIMULATION_STATUS_FAILED,
        application_simulation_pb2.SIMULATION_STATUS_CANCELLED,
        application_simulation_pb2.SIMULATION_STATUS_TIMED_OUT,
    }
)


class SimulationsClient:
    """Simulated runs of an Application: the platform's own engine runs it on a virtual fleet, every
    command is answered from its published contract and the request's scenario, and no command
    leaves the platform. A simulated run never holds, commands or changes a real asset.

    Every call raises :class:`CommandError` with the gRPC ``status``: ``INVALID_ARGUMENT`` for an
    unusable scenario or fleet, ``NOT_FOUND`` for an Application or run that is not the caller's
    organization's.
    """

    def __init__(self, channel: grpc.aio.Channel, resilience: ResilienceConfig) -> None:
        self._stub = application_simulation_pb2_grpc.SimulationServiceStub(channel)
        self._timeout = float(resilience.request_timeout_seconds)
        self._resilience = GrpcResilience(resilience)

    async def start_simulation(
        self, request: application_simulation_pb2.StartSimulationRequest
    ) -> application_simulation_pb2.StartSimulationResponse:
        """Start a simulated run; returns once it is running, with its ``execution_id`` and
        ``status``. A request without ``context.idempotency_key`` gets a new one; a start retried
        with the same key answers the run it started."""
        if not request.application_id:
            raise ValueError("application_id is required")
        start = application_simulation_pb2.StartSimulationRequest()
        start.CopyFrom(request)
        if not start.context.request_id:
            start.context.request_id = str(uuid.uuid4())
        if not start.context.idempotency_key:
            start.context.idempotency_key = str(uuid.uuid4())
        return await self._unary(lambda: self._stub.StartSimulation(start, timeout=self._timeout))

    async def simulation_trace(self, execution_id: str) -> application_simulation_pb2.SimulationTrace:
        """The path the run took so far, or in full once it has ended."""
        request = application_simulation_pb2.GetSimulationTraceRequest(
            context=_context(), execution_id=_require(execution_id, "execution_id")
        )
        response = await self._unary(lambda: self._stub.GetSimulationTrace(request, timeout=self._timeout))
        return response.trace

    async def cancel_simulation(self, execution_id: str) -> int:
        """Stop a simulated run; returns its ``SimulationStatus``, ``CANCELLING`` while its commands
        stop."""
        request = application_simulation_pb2.CancelSimulationRequest(
            context=_context(), execution_id=_require(execution_id, "execution_id")
        )
        response = await self._unary(lambda: self._stub.CancelSimulation(request, timeout=self._timeout))
        return response.status

    async def wait_for_simulation(
        self,
        execution_id: str,
        *,
        interval: timedelta | float = 1.0,
        timeout: timedelta | float | None = None,
    ) -> application_simulation_pb2.SimulationTrace:
        """Poll the trace every ``interval`` until the run is ``SUCCEEDED``, ``FAILED``,
        ``CANCELLED`` or ``TIMED_OUT`` and return that trace, whatever the outcome. When ``timeout``
        elapses first (``None`` waits without a limit) it raises a :class:`CommandError` with category
        ``TIMEOUT`` and the run keeps going (:meth:`cancel_simulation` stops it)."""
        _require(execution_id, "execution_id")
        pause = _seconds(interval)
        if pause <= 0:
            raise ValueError("interval must be positive")
        limit = None if timeout is None else _seconds(timeout)
        try:
            async with asyncio.timeout(limit):
                while True:
                    trace = await self.simulation_trace(execution_id)
                    if trace.status in FINAL_SIMULATION_STATUSES:
                        return trace
                    await asyncio.sleep(pause)
        except TimeoutError:
            raise CommandError(
                f"simulation {execution_id} did not end within {limit}s",
                category=common_pb2.ERROR_CATEGORY_TIMEOUT,
            ) from None

    async def simulate(
        self,
        request: application_simulation_pb2.StartSimulationRequest,
        *,
        interval: timedelta | float = 1.0,
        timeout: timedelta | float | None = None,
    ) -> application_simulation_pb2.SimulationTrace:
        """Start a simulated run and wait for its trace as :meth:`wait_for_simulation` does."""
        started = await self.start_simulation(request)
        return await self.wait_for_simulation(started.execution_id, interval=interval, timeout=timeout)

    async def _unary(self, op):
        try:
            return await self._resilience.execute(op)
        except Exception as exc:
            raise CommandError.from_exception(exc) from exc


def _context() -> common_pb2.RequestContext:
    return common_pb2.RequestContext(request_id=str(uuid.uuid4()))


def _require(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _seconds(value: timedelta | float) -> float:
    return value.total_seconds() if isinstance(value, timedelta) else float(value)

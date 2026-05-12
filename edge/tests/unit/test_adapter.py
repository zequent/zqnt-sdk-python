"""
Unit tests for EdgeAdapter – no network, no gRPC.

Tests the core SDK logic:
- _auto_capabilities() reflects exactly what's overridden
- _is_overridden() detects subclass overrides
- Default methods return not_supported (not raise)
- Only get_capabilities() is required (ABC)
"""

import pytest

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse
from edge_sdk.models.common import ErrorCode
from tests.conftest import make_ctx

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _DroneAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(self, ctx, coordinates):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def go_to(self, ctx, coordinates):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_task(self, ctx, task_id):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


class _DockAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    async def open_cover(self, ctx):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def close_cover(self, ctx, force):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_charging(self, ctx):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


# ---------------------------------------------------------------------------
# _auto_capabilities
# ---------------------------------------------------------------------------


def test_auto_capabilities_marks_overridden_as_available():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-001", AssetType.AIRCRAFT)

    available = {c.command for c in caps.capabilities if c.available}
    assert "TakeOff" in available
    assert "GoTo" in available
    assert "StartTask" in available


def test_auto_capabilities_marks_not_overridden_as_unavailable():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-001", AssetType.AIRCRAFT)

    unavailable = {c.command for c in caps.capabilities if not c.available}
    assert "OpenCover" in unavailable
    assert "StartCharging" in unavailable
    assert "CloseCover" in unavailable


def test_auto_capabilities_drone_vs_dock_differ():
    drone = _DroneAdapter()
    dock = _DockAdapter()

    drone_caps = {c.command for c in drone._auto_capabilities("D", AssetType.AIRCRAFT).capabilities if c.available}
    dock_caps = {c.command for c in dock._auto_capabilities("D", AssetType.DOCK).capabilities if c.available}

    assert "TakeOff" in drone_caps
    assert "TakeOff" not in dock_caps
    assert "OpenCover" in dock_caps
    assert "OpenCover" not in drone_caps


def test_auto_capabilities_sets_correct_sn_and_type():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-XYZ", AssetType.AIRCRAFT)

    assert caps.asset_sn == "DRONE-XYZ"
    assert caps.asset_type == AssetType.AIRCRAFT
    assert caps.timestamp is not None


# ---------------------------------------------------------------------------
# _is_overridden
# ---------------------------------------------------------------------------


def test_is_overridden_true_for_implemented_method():
    adapter = _DroneAdapter()
    assert adapter._is_overridden("take_off") is True
    assert adapter._is_overridden("start_task") is True


def test_is_overridden_false_for_default_method():
    adapter = _DroneAdapter()
    assert adapter._is_overridden("open_cover") is False
    assert adapter._is_overridden("start_charging") is False


# ---------------------------------------------------------------------------
# Default implementations return not_supported (no raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_methods_return_not_supported_not_raise():
    adapter = _DroneAdapter()
    ctx = make_ctx()

    resp = await adapter.open_cover(ctx)

    assert resp.success is False
    assert resp.error is not None
    assert resp.error.code == ErrorCode.SDK_ERROR


@pytest.mark.asyncio
async def test_default_methods_carry_tid_and_sn():
    adapter = _DroneAdapter()
    ctx = make_ctx(tid="abc-123", sn="MY-SENSOR")

    resp = await adapter.open_cover(ctx)

    assert resp.tid == "abc-123"
    assert resp.sn == "MY-SENSOR"


# ---------------------------------------------------------------------------
# ABC: get_capabilities is the only required method
# ---------------------------------------------------------------------------


def test_adapter_without_get_capabilities_raises():
    with pytest.raises(TypeError):

        class _Bad(EdgeAdapter):
            pass  # no get_capabilities

        _Bad()


def test_adapter_with_only_get_capabilities_is_instantiable():
    class _Minimal(EdgeAdapter):
        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.SENSOR)

    _Minimal()  # must not raise
"""
Unit tests for EdgeAdapter – no network, no gRPC.

Tests the core SDK logic:
- _auto_capabilities() reflects exactly what's overridden
- _is_overridden() detects subclass overrides
- Default methods return not_supported (not raise)
- Only get_capabilities() is required (ABC)
"""

import pytest

from edge_sdk import AssetType, EdgeAdapter, EdgeResponse
from edge_sdk.models.common import ErrorCode
from tests.conftest import make_ctx

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _DroneAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(self, ctx, coordinates):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def go_to(self, ctx, coordinates):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_task(self, ctx, task_id):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


class _DockAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    async def open_cover(self, ctx):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def close_cover(self, ctx, force):
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_charging(self, ctx):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


# ---------------------------------------------------------------------------
# _auto_capabilities
# ---------------------------------------------------------------------------


def test_auto_capabilities_marks_overridden_as_available():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-001", AssetType.AIRCRAFT)

    available = {c.command for c in caps.capabilities if c.available}
    assert "TakeOff" in available
    assert "GoTo" in available
    assert "StartTask" in available


def test_auto_capabilities_marks_not_overridden_as_unavailable():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-001", AssetType.AIRCRAFT)

    unavailable = {c.command for c in caps.capabilities if not c.available}
    assert "OpenCover" in unavailable
    assert "StartCharging" in unavailable
    assert "CloseCover" in unavailable


def test_auto_capabilities_drone_vs_dock_differ():
    drone = _DroneAdapter()
    dock = _DockAdapter()

    drone_caps = {c.command for c in drone._auto_capabilities("D", AssetType.AIRCRAFT).capabilities if c.available}
    dock_caps = {c.command for c in dock._auto_capabilities("D", AssetType.DOCK).capabilities if c.available}

    assert "TakeOff" in drone_caps
    assert "TakeOff" not in dock_caps
    assert "OpenCover" in dock_caps
    assert "OpenCover" not in drone_caps


def test_auto_capabilities_sets_correct_sn_and_type():
    adapter = _DroneAdapter()
    caps = adapter._auto_capabilities("DRONE-XYZ", AssetType.AIRCRAFT)

    assert caps.asset_sn == "DRONE-XYZ"
    assert caps.asset_type == AssetType.AIRCRAFT
    assert caps.timestamp is not None


# ---------------------------------------------------------------------------
# _is_overridden
# ---------------------------------------------------------------------------


def test_is_overridden_true_for_implemented_method():
    adapter = _DroneAdapter()
    assert adapter._is_overridden("take_off") is True
    assert adapter._is_overridden("start_task") is True


def test_is_overridden_false_for_default_method():
    adapter = _DroneAdapter()
    assert adapter._is_overridden("open_cover") is False
    assert adapter._is_overridden("start_charging") is False


# ---------------------------------------------------------------------------
# Default implementations return not_supported (no raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_methods_return_not_supported_not_raise():
    adapter = _DroneAdapter()
    ctx = make_ctx()

    resp = await adapter.open_cover(ctx)

    assert resp.success is False
    assert resp.error is not None
    assert resp.error.code == ErrorCode.SDK_ERROR


@pytest.mark.asyncio
async def test_default_methods_carry_tid_and_sn():
    adapter = _DroneAdapter()
    ctx = make_ctx(tid="abc-123", sn="MY-SENSOR")

    resp = await adapter.open_cover(ctx)

    assert resp.tid == "abc-123"
    assert resp.sn == "MY-SENSOR"


# ---------------------------------------------------------------------------
# ABC: get_capabilities is the only required method
# ---------------------------------------------------------------------------


def test_adapter_without_get_capabilities_raises():
    with pytest.raises(TypeError):

        class _Bad(EdgeAdapter):
            pass  # no get_capabilities

        _Bad()


def test_adapter_with_only_get_capabilities_is_instantiable():
    class _Minimal(EdgeAdapter):
        async def get_capabilities(self, sn, asset_id):
            return self._auto_capabilities(sn, AssetType.SENSOR)

    _Minimal()  # must not raise

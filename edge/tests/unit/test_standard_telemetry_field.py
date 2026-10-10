import pytest

from edge_sdk.adapter.base import EdgeAdapter
from edge_sdk.models.common import AssetType, TelemetryValueType


class _Adapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)


def test_a_catalog_key_is_declared_as_the_platform_describes_it():
    adapter = _Adapter()
    adapter.declare_standard_telemetry_field("dock.mode")
    adapter.declare_standard_telemetry_field("wind.speed")
    mode = adapter._telemetry_fields["dock.mode"]
    assert mode.type is TelemetryValueType.STRING and "WORKING" in mode.allowed_values
    wind = adapter._telemetry_fields["wind.speed"]
    assert (wind.type, wind.unit) == (TelemetryValueType.NUMBER, "m/s")


def test_a_key_outside_the_catalog_is_refused():
    with pytest.raises(ValueError, match="radar.mode"):
        _Adapter().declare_standard_telemetry_field("radar.mode")

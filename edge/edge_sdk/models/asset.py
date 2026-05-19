"""
Plain-Python asset models mirroring common.proto AssetProtoDTO / SubAssetProtoDTO.
"""

from dataclasses import dataclass

from .common import AssetConnection, AssetType, AssetVendor, LiveStreamType


@dataclass
class SubAsset:
    id: str | None
    sn: str
    name: str
    type: AssetType
    vendor: AssetVendor
    connection: AssetConnection
    model: str
    organization: str
    online: bool
    stream_type: LiveStreamType
    connection_string: str | None = None
    port: int | None = None
    live_stream_server: str | None = None
    external_device_type: str | None = None
    external_device_sub_type: str | None = None
    external_id: str | None = None
    stream_url_predefined: bool | None = None


@dataclass
class Asset:
    id: str | None
    sn: str
    name: str
    type: AssetType
    vendor: AssetVendor
    connection: AssetConnection
    model: str
    organization: str
    online: bool
    stream_type: LiveStreamType
    connection_string: str | None = None
    port: int | None = None
    live_stream_server: str | None = None
    external_device_type: str | None = None
    external_device_sub_type: str | None = None
    external_id: str | None = None
    sub_asset: SubAsset | None = None

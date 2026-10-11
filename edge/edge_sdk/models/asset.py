"""
Plain-Python asset models mirroring asset.proto AssetProtoDTO / SubAssetProtoDTO.

``online``/``stream_type``/``connection_string``/``port``/``live_stream_server`` (and, for
``SubAsset`` only, ``organization``) are permanently reserved on the wire — retired in favor of
``system_connection_string`` and the split ``live_stream_push_url``/``live_stream_pull_url``, with
``online``/``stream_type`` dropped outright (liveness now lives in Redis staleness tracking, not
the DTO; stream type is chosen per live-stream-start request instead of stored on the asset).
``sub_asset`` (singular) is likewise gone — ``AssetProtoDTO`` now carries ``repeated
SubAssetProtoDTO sub_assets``.
"""

from dataclasses import dataclass, field
from datetime import datetime

from .common import AssetConnection, AssetType, AssetVendor


@dataclass
class SubAsset:
    id: str | None
    sn: str
    name: str
    type: AssetType
    vendor: AssetVendor
    connection: AssetConnection
    model: str
    system_connection_string: str | None = None
    external_device_type: str | None = None
    external_device_sub_type: str | None = None
    external_id: str | None = None
    stream_url_predefined: bool | None = None
    live_stream_push_url: str | None = None
    live_stream_pull_url: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    modified_from: str | None = None


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
    system_connection_string: str | None = None
    external_device_type: str | None = None
    external_device_sub_type: str | None = None
    external_id: str | None = None
    live_stream_push_url: str | None = None
    live_stream_pull_url: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    modified_from: str | None = None
    sub_assets: list[SubAsset] = field(default_factory=list)

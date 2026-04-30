"""Proto <-> dataclass converters for the LiveData sub-client.

Field names mirror :file:`live-data.proto` exactly. Generated proto modules
are imported lazily so the package remains importable before
``scripts/generate_protos.sh`` has been run.
"""

from __future__ import annotations

from typing import Any

from ..models._converters import (
    opt_field,
    proto_to_error_info,
    proto_ts_to_datetime,
)
from ..models.live_data import (
    AssetAirConditioner,
    AssetNetworkInfo,
    AssetPositionState,
    AssetSubAssetInformation,
    AssetTelemetry,
    CameraData,
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataResponse,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    LiveStreamStartResult,
    PayloadTelemetry,
    RangeFinderData,
    SensorData,
    StreamTelemetryError,
    StreamTelemetryRequest,
    StreamTelemetryResponse,
    SubAssetBatteryInfo,
    SubAssetTelemetry,
)


def _set_opt(kwargs: dict[str, Any], field: str, value: Any) -> None:
    if value is not None:
        kwargs[field] = value


def _enum_name(enum_module, enum_value, default: str | None = None) -> str | None:
    try:
        return enum_module.Name(enum_value)
    except Exception:  # pragma: no cover - defensive
        return default


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def stream_telemetry_request_to_proto(req: StreamTelemetryRequest):
    from ..generated import common_pb2, live_data_pb2  # type: ignore[import]
    from ..models._converters import build_request_base

    # Default command = START_TELEMETRY_STREAM (0)
    kwargs: dict[str, Any] = {
        "base": build_request_base(req.sn, tid=req.tid),
        "command": common_pb2.LiveDataServiceCommand.START_TELEMETRY_STREAM,
    }
    if req.frequency_ms:
        kwargs["frequencyMs"] = req.frequency_ms
    if req.duration_seconds:
        kwargs["duration"] = req.duration_seconds
    return live_data_pb2.LiveDataStreamTelemetryRequest(**kwargs)


def start_live_stream_to_proto(req: LiveDataStartLiveStreamRequest):
    from ..generated import common_pb2, live_data_pb2  # type: ignore[import]
    from ..models._converters import build_request_base

    inner = live_data_pb2.LiveStreamStartRequest(
        videoId=req.video_id,
        streamServer=req.stream_server,
        streamType=req.stream_type.value,
        assetType=req.asset_type.value,
    )
    return live_data_pb2.LiveDataStartLiveStreamRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def stop_live_stream_to_proto(req: LiveDataStopLiveStreamRequest):
    from ..generated import live_data_pb2  # type: ignore[import]
    from ..models._converters import build_request_base

    inner = live_data_pb2.LiveStreamStopRequest(videoId=req.video_id)
    return live_data_pb2.LiveDataStopLiveStreamRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def change_lens_to_proto(req: ChangeLensRequest):
    from ..generated import common_pb2, live_data_pb2  # type: ignore[import]
    from ..models._converters import build_request_base

    inner = common_pb2.ChangeCameraLensRequest(lens=req.lens)
    return live_data_pb2.LiveDataChangeLensRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def change_zoom_to_proto(req: ChangeZoomRequest):
    from ..generated import common_pb2, live_data_pb2  # type: ignore[import]
    from ..models._converters import build_request_base

    inner_kwargs: dict[str, Any] = {"zoom": req.zoom}
    if req.lens is not None:
        inner_kwargs["lens"] = req.lens
    inner = common_pb2.ChangeCameraZoomRequest(**inner_kwargs)
    return live_data_pb2.LiveDataChangeZoomRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


# ---------------------------------------------------------------------------
# Unary response converter
# ---------------------------------------------------------------------------


def proto_to_live_data_response(proto) -> LiveDataResponse:
    """Decode ``LiveDataResponse`` (unary) into the SDK dataclass."""
    detail = proto.WhichOneof("detail")

    error_code: str | None = None
    error_message: str | None = None
    live_stream_start: LiveStreamStartResult | None = None

    if detail == "error":
        info = proto_to_error_info(proto.error)
        error_code = info.error_code
        error_message = info.error_message
    elif detail == "liveStreamStartResponse":
        lsr = proto.liveStreamStartResponse
        live_stream_start = LiveStreamStartResult(
            stream_url=lsr.streamUrl,
            video_id=lsr.videoId,
        )

    return LiveDataResponse(
        success=not proto.hasErrors,
        tid=proto.tid,
        sn=proto.sn,
        asset_id=opt_field(proto, "assetId"),
        message=opt_field(proto, "responseMessage"),
        error_code=error_code,
        error_message=error_message,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        live_stream_start=live_stream_start,
    )


# ---------------------------------------------------------------------------
# Telemetry decoders
# ---------------------------------------------------------------------------


def _decode_asset_telemetry(t) -> AssetTelemetry:
    from ..generated import common_pb2  # type: ignore[import]

    net = None
    if t.HasField("networkInformation"):
        ni = t.networkInformation
        net = AssetNetworkInfo(
            type=_enum_name(common_pb2.NetworkTypeEnum, ni.type) if ni.HasField("type") else None,
            rate=opt_field(ni, "rate"),
            quality=_enum_name(common_pb2.NetworkStateQualityEnum, ni.quality) if ni.HasField("quality") else None,
        )
    ac = None
    if t.HasField("airConditioner"):
        a = t.airConditioner
        ac = AssetAirConditioner(
            state=_enum_name(common_pb2.AssetAirConditionerStateEnum, a.state) if a.HasField("state") else None,
            switch_time=opt_field(a, "switchTime"),
        )
    sub_info = None
    if t.HasField("subAssetInformation"):
        si = t.subAssetInformation
        sub_info = AssetSubAssetInformation(
            sn=opt_field(si, "sn"),
            model=opt_field(si, "model"),
            paired=opt_field(si, "paired"),
            online=opt_field(si, "online"),
        )
    pos = None
    if t.HasField("positionState"):
        ps = t.positionState
        pos = AssetPositionState(
            gps_number=opt_field(ps, "gpsNumber"),
            rtk_number=opt_field(ps, "rtkNumber"),
            quality=opt_field(ps, "quality"),
        )
    return AssetTelemetry(
        id=t.id,
        timestamp=proto_ts_to_datetime(t.timestamp),
        latitude=opt_field(t, "latitude"),
        longitude=opt_field(t, "longitude"),
        absolute_altitude=opt_field(t, "absoluteAltitude"),
        relative_altitude=opt_field(t, "relativeAltitude"),
        environment_temp=opt_field(t, "environmentTemp"),
        inside_temp=opt_field(t, "insideTemp"),
        humidity=opt_field(t, "humidity"),
        mode=_enum_name(common_pb2.AssetMode, t.mode) if t.HasField("mode") else None,
        rainfall=_enum_name(common_pb2.RainfallEnum, t.rainfall) if t.HasField("rainfall") else None,
        sub_asset_information=sub_info,
        sub_asset_at_home=opt_field(t, "subAssetAtHome"),
        sub_asset_charging=opt_field(t, "subAssetCharging"),
        sub_asset_percentage=opt_field(t, "subAssetPercentage"),
        heading=opt_field(t, "heading"),
        debug_mode_open=opt_field(t, "debugModeOpen"),
        has_active_manual_control_session=opt_field(t, "hasActiveManualControlSession"),
        cover_state=_enum_name(common_pb2.AssetCoverStateEnum, t.coverState) if t.HasField("coverState") else None,
        working_voltage=opt_field(t, "workingVoltage"),
        working_current=opt_field(t, "workingCurrent"),
        supply_voltage=opt_field(t, "supplyVoltage"),
        wind_speed=opt_field(t, "windSpeed"),
        position_valid=opt_field(t, "positionValid"),
        network_information=net,
        air_conditioner=ac,
        manual_control_state=_enum_name(common_pb2.ManualControlStateEnum, t.manualControlState) if t.HasField("manualControlState") else None,
        position_state=pos,
    )


def _decode_payload(p) -> PayloadTelemetry:
    cam = None
    if p.HasField("cameraData"):
        cd = p.cameraData
        cam = CameraData(
            current_lens=opt_field(cd, "currentLens"),
            gimbal_pitch=opt_field(cd, "gimbalPitch"),
            gimbal_yaw=opt_field(cd, "gimbalYaw"),
            gimbal_roll=opt_field(cd, "gimbalRoll"),
            zoom_factor=opt_field(cd, "zoomFactor"),
        )
    rf = None
    if p.HasField("rangeFinderData"):
        rd = p.rangeFinderData
        rf = RangeFinderData(
            target_latitude=opt_field(rd, "targetLatitude"),
            target_longitude=opt_field(rd, "targetLongitude"),
            target_distance=opt_field(rd, "targetDistance"),
            target_altitude=opt_field(rd, "targetAltitude"),
        )
    sens = None
    if p.HasField("sensorData"):
        sd = p.sensorData
        sens = SensorData(target_temperature=opt_field(sd, "targetTemperature"))
    return PayloadTelemetry(
        id=p.id,
        name=p.name,
        timestamp=proto_ts_to_datetime(p.timestamp),
        camera=cam,
        range_finder=rf,
        sensor=sens,
    )


def _decode_sub_asset_telemetry(t) -> SubAssetTelemetry:
    from ..generated import common_pb2  # type: ignore[import]

    payload = _decode_payload(t.payloadTelemetry) if t.HasField("payloadTelemetry") else None
    batt = None
    if t.HasField("batteryInformation"):
        bi = t.batteryInformation
        batt = SubAssetBatteryInfo(
            percentage=opt_field(bi, "percentage"),
            remaining_time=opt_field(bi, "remainingTime"),
            return_to_home_power=opt_field(bi, "returnToHomePower"),
        )
    return SubAssetTelemetry(
        id=t.id,
        timestamp=proto_ts_to_datetime(t.timestamp),
        latitude=opt_field(t, "latitude"),
        longitude=opt_field(t, "longitude"),
        absolute_altitude=opt_field(t, "absoluteAltitude"),
        relative_altitude=opt_field(t, "relativeAltitude"),
        horizontal_speed=opt_field(t, "horizontalSpeed"),
        vertical_speed=opt_field(t, "verticalSpeed"),
        wind_speed=opt_field(t, "windSpeed"),
        wind_direction=opt_field(t, "windDirection"),
        heading=opt_field(t, "heading"),
        gear=opt_field(t, "gear"),
        payload=payload,
        battery=batt,
        height_limit=opt_field(t, "heightLimit"),
        home_distance=opt_field(t, "homeDistance"),
        total_movement_distance=opt_field(t, "totalMovementDistance"),
        total_movement_time=opt_field(t, "totalMovementTime"),
        mode=_enum_name(common_pb2.SubAssetMode, t.mode) if t.HasField("mode") else None,
        country=opt_field(t, "country"),
    )


def proto_to_stream_telemetry_response(proto) -> StreamTelemetryResponse:
    """Decode one frame of ``LiveDataTelemetryResponse``."""
    which = proto.WhichOneof("telemetry")
    asset_t = _decode_asset_telemetry(proto.assetTelemetry) if which == "assetTelemetry" else None
    sub_t = _decode_sub_asset_telemetry(proto.subAssetTelemetry) if which == "subAssetTelemetry" else None
    error: StreamTelemetryError | None = None
    if which == "error":
        info = proto_to_error_info(proto.error)
        error = StreamTelemetryError(
            error_code=info.error_code,
            error_message=info.error_message,
            timestamp=info.timestamp,
        )
    return StreamTelemetryResponse(
        tid=proto.tid,
        sn=proto.sn,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        has_errors=proto.hasErrors,
        asset_id=opt_field(proto, "assetId"),
        asset_telemetry=asset_t,
        sub_asset_telemetry=sub_t,
        error=error,
    )

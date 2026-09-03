"""Proto <-> dataclass converters for the LiveData sub-client.

Field names mirror ``live-data.proto`` / ``live-data-types.proto`` / ``events.proto``
exactly (real generated fields are snake_case, matching the .proto source — not the
camelCase the stale pre-migration stubs used to expose). Generated proto modules are
imported lazily so the package remains importable before the SDK's protobuf
dependency has been installed.
"""

from __future__ import annotations

from typing import Any

from ..models._converters import (
    has_field,
    opt_field,
    proto_to_error_info,
    proto_ts_to_datetime,
)
from ..models.live_data import (
    AssetAirConditioner,
    AssetNetworkInfo,
    AssetPositionState,
    AssetSdrState,
    AssetSubAssetInformation,
    AssetTelemetry,
    AssetWirelessLinkInfo,
    CameraData,
    ChangeLensRequest,
    ChangeZoomRequest,
    LiveDataResponse,
    LiveDataStartLiveStreamRequest,
    LiveDataStopLiveStreamRequest,
    LiveStreamStartResult,
    NotificationAssetStatus,
    NotificationOperationEvent,
    NotificationTaskEvent,
    PayloadTelemetry,
    RangeFinderData,
    SensorData,
    StreamNotificationRequest,
    StreamNotificationResponse,
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
    from zqnt_utils.generated.zqnt import common_pb2, live_data_types_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    kwargs: dict[str, Any] = {
        "base": build_request_base(req.sn, tid=req.tid),
        "command": common_pb2.LIVE_DATA_COMMAND_START_TELEMETRY_STREAM,
    }
    if req.frequency_ms:
        kwargs["frequency_ms"] = req.frequency_ms
    if req.duration_seconds:
        kwargs["duration"] = req.duration_seconds
    return live_data_types_pb2.StreamTelemetryRequest(**kwargs)


def stream_notifications_request_to_proto(req: StreamNotificationRequest):
    from zqnt_utils.generated.zqnt import events_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    kwargs: dict[str, Any] = {"base": build_request_base(req.sn, tid=req.tid)}
    if req.event_types:
        kwargs["event_types"] = [getattr(event_type, "value", event_type) for event_type in req.event_types]
    return events_pb2.StreamNotificationsRequest(**kwargs)


def start_live_stream_to_proto(req: LiveDataStartLiveStreamRequest):
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    inner = common_pb2.LiveStreamStartCommandPayload(
        video_id=req.video_id,
        stream_server=req.stream_server,
        stream_type=req.stream_type.value,
        asset_type=req.asset_type.value,
    )
    return common_pb2.LiveStreamStartCommandRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def stop_live_stream_to_proto(req: LiveDataStopLiveStreamRequest):
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    inner = common_pb2.LiveStreamStopCommandPayload(video_id=req.video_id)
    return common_pb2.LiveStreamStopCommandRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def change_lens_to_proto(req: ChangeLensRequest):
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    inner = common_pb2.ChangeCameraLensRequest(lens=req.lens)
    return common_pb2.ChangeCameraLensCommandRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


def change_zoom_to_proto(req: ChangeZoomRequest):
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    from ..models._converters import build_request_base

    inner_kwargs: dict[str, Any] = {"zoom": req.zoom}
    if req.lens is not None:
        inner_kwargs["lens"] = req.lens
    inner = common_pb2.ChangeCameraZoomRequest(**inner_kwargs)
    return common_pb2.ChangeCameraZoomCommandRequest(
        base=build_request_base(req.sn, tid=req.tid),
        request=inner,
    )


# ---------------------------------------------------------------------------
# Unary response converter — start/stopLiveStream, changeLens, changeZoom all
# return the shared device-control-contracts ``CommandResponse``.
# ---------------------------------------------------------------------------


def proto_to_live_data_response(proto, sn: str | None = None) -> LiveDataResponse:
    """Decode a ``CommandResponse`` into the SDK dataclass.

    tid/sn/asset_id/message live under ``proto.meta`` (a ``ResponseMeta``) now,
    not flat on the response itself. ``sn`` is accepted as a fallback (preferred
    over ``meta.sn``, matching the RemoteControl client's convention) since
    callers already know it from the request.
    """
    which = proto.WhichOneof("response")

    error_code: str | None = None
    error_message: str | None = None
    live_stream_start: LiveStreamStartResult | None = None

    if which == "error":
        info = proto_to_error_info(proto.error)
        error_code = info.error_code
        error_message = info.error_message
    elif which == "live_stream_start_response":
        lsr = proto.live_stream_start_response
        live_stream_start = LiveStreamStartResult(
            stream_url=lsr.stream_url,
            video_id=lsr.video_id,
        )

    meta = proto.meta if proto.HasField("meta") else None
    return LiveDataResponse(
        success=not bool(opt_field(proto, "has_errors")),
        tid=meta.tid if meta is not None else "",
        sn=(meta.sn if meta is not None else "") or sn or "",
        asset_id=(opt_field(meta, "asset_id") if meta is not None else None),
        message=(opt_field(meta, "response_message") if meta is not None else None),
        error_code=error_code,
        error_message=error_message,
        timestamp=proto_ts_to_datetime(meta.timestamp) if meta is not None else None,
        live_stream_start=live_stream_start,
    )


# ---------------------------------------------------------------------------
# Notification decoder
# ---------------------------------------------------------------------------


def proto_to_stream_notification_response(proto) -> StreamNotificationResponse:
    """Decode one frame of ``NotificationResponse`` (``events.proto``)."""
    event_type: str | None = None
    asset_status: NotificationAssetStatus | None = None
    operation_event: NotificationOperationEvent | None = None
    task_event: NotificationTaskEvent | None = None
    error = None

    detail = proto.WhichOneof("detail")
    if detail == "error":
        error = proto_to_error_info(proto.error)
    elif detail == "event":
        inner = proto.event
        which_event = inner.WhichOneof("event")
        if which_event == "asset_status":
            event_type = "NOTIFICATION_EVENT_ASSET_STATUS"
            asset = inner.asset_status
            asset_status = NotificationAssetStatus(
                sn=asset.sn,
                asset_id=opt_field(asset, "asset_id"),
                online=opt_field(asset, "online"),
                message=opt_field(asset, "message"),
            )
        elif which_event == "mission":
            event_type = "NOTIFICATION_EVENT_MISSION"
            from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

            mission = inner.mission
            operation_event = NotificationOperationEvent(
                operation_id=mission.mission_id,
                mission_type=_enum_name(common_pb2.MissionType, mission.mission_type),
                status=_enum_name(common_pb2.MissionStatus, mission.status),
                message=opt_field(mission, "message"),
            )
        elif which_event == "task":
            event_type = "NOTIFICATION_EVENT_TASK"
            from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

            task = inner.task
            task_event = NotificationTaskEvent(
                task_id=task.task_id,
                task_type=_enum_name(common_pb2.TaskTypeProto, task.task_type),
                status=_enum_name(common_pb2.TaskStatus, task.status),
                progress=opt_field(task, "progress"),
                message=opt_field(task, "message"),
                external_task_type=opt_field(task, "external_task_type"),
            )
        elif which_event == "error":
            event_type = None
            error = proto_to_error_info(inner.error)
        # asset_runtime: a newer branch, not yet surfaced as a typed dataclass here -- same
        # scope boundary as the richer capability-package shape left untouched elsewhere.

    return StreamNotificationResponse(
        tid=proto.tid,
        sn=proto.sn,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        has_errors=proto.has_errors,
        asset_id=opt_field(proto, "asset_id"),
        event_type=event_type,
        asset_status=asset_status,
        operation_event=operation_event,
        task_event=task_event,
        error=error,
    )


# ---------------------------------------------------------------------------
# Telemetry decoders
# ---------------------------------------------------------------------------


def _decode_asset_telemetry_details(sn: str | None, base_id: str, timestamp, t) -> AssetTelemetry:
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    net = None
    if has_field(t, "network_information"):
        ni = t.network_information
        net = AssetNetworkInfo(
            type=_enum_name(common_pb2.NetworkTypeEnum, ni.type) if has_field(ni, "type") else None,
            rate=opt_field(ni, "rate"),
            quality=_enum_name(common_pb2.NetworkStateQualityEnum, ni.quality) if has_field(ni, "quality") else None,
        )
    ac = None
    if has_field(t, "air_conditioner"):
        a = t.air_conditioner
        ac = AssetAirConditioner(
            state=_enum_name(common_pb2.AssetAirConditionerStateEnum, a.state) if has_field(a, "state") else None,
            switch_time=opt_field(a, "switch_time"),
        )
    sub_info = None
    if has_field(t, "sub_asset_information"):
        si = t.sub_asset_information
        sub_info = AssetSubAssetInformation(
            sn=opt_field(si, "sn"),
            model=opt_field(si, "model"),
            paired=opt_field(si, "paired"),
            online=opt_field(si, "online"),
        )
    pos = None
    if has_field(t, "position_state"):
        ps = t.position_state
        pos = AssetPositionState(
            gps_number=opt_field(ps, "gps_number"),
            rtk_number=opt_field(ps, "rtk_number"),
            quality=opt_field(ps, "quality"),
        )
    wireless_link = None
    if has_field(t, "wireless_link"):
        wl = t.wireless_link
        wireless_link = AssetWirelessLinkInfo(
            fourth_generation_freq_band=opt_field(wl, "fourth_generation_freq_band"),
            fourth_generation_gnd_quality=opt_field(wl, "fourth_generation_gnd_quality"),
            fourth_generation_link_state=opt_field(wl, "fourth_generation_link_state"),
            fourth_generation_quality=opt_field(wl, "fourth_generation_quality"),
            fourth_generation_uav_quality=opt_field(wl, "fourth_generation_uav_quality"),
            dongle_number=opt_field(wl, "dongle_number"),
            link_workmode=opt_field(wl, "link_workmode"),
            sdr_freq_band=opt_field(wl, "sdr_freq_band"),
            sdr_link_state=opt_field(wl, "sdr_link_state"),
            sdr_quality=opt_field(wl, "sdr_quality"),
        )
    sdr_state = None
    if has_field(t, "sdr_state"):
        sdr = t.sdr_state
        sdr_state = AssetSdrState(
            down_quality=opt_field(sdr, "down_quality"),
            up_quality=opt_field(sdr, "up_quality"),
            frequency_band=opt_field(sdr, "frequency_band"),
        )
    return AssetTelemetry(
        id=base_id,
        timestamp=timestamp,
        sn=sn,
        latitude=None,
        longitude=None,
        absolute_altitude=None,
        relative_altitude=None,
        environment_temp=opt_field(t, "environment_temp"),
        inside_temp=opt_field(t, "inside_temp"),
        humidity=opt_field(t, "humidity"),
        mode=_enum_name(common_pb2.AssetMode, t.mode) if has_field(t, "mode") else None,
        rainfall=_enum_name(common_pb2.RainfallEnum, t.rainfall) if has_field(t, "rainfall") else None,
        sub_asset_information=sub_info,
        sub_asset_at_home=opt_field(t, "sub_asset_at_home"),
        sub_asset_charging=opt_field(t, "sub_asset_charging"),
        sub_asset_percentage=opt_field(t, "sub_asset_percentage"),
        heading=None,
        debug_mode_open=opt_field(t, "debug_mode_open"),
        has_active_manual_control_session=opt_field(t, "has_active_manual_control_session"),
        cover_state=_enum_name(common_pb2.AssetCoverStateEnum, t.cover_state) if has_field(t, "cover_state") else None,
        working_voltage=opt_field(t, "working_voltage"),
        working_current=opt_field(t, "working_current"),
        supply_voltage=opt_field(t, "supply_voltage"),
        wind_speed=None,
        position_valid=opt_field(t, "position_valid"),
        network_information=net,
        air_conditioner=ac,
        manual_control_state=_enum_name(common_pb2.ManualControlStateEnum, t.manual_control_state)
        if has_field(t, "manual_control_state")
        else None,
        position_state=pos,
        wireless_link=wireless_link,
        sdr_state=sdr_state,
    )


def _decode_payload(p) -> PayloadTelemetry:
    cam = None
    if has_field(p, "camera_data"):
        cd = p.camera_data
        cam = CameraData(
            current_lens=opt_field(cd, "current_lens"),
            gimbal_pitch=opt_field(cd, "gimbal_pitch"),
            gimbal_yaw=opt_field(cd, "gimbal_yaw"),
            gimbal_roll=opt_field(cd, "gimbal_roll"),
            zoom_factor=opt_field(cd, "zoom_factor"),
        )
    rf = None
    if has_field(p, "range_finder_data"):
        rd = p.range_finder_data
        rf = RangeFinderData(
            target_latitude=opt_field(rd, "target_latitude"),
            target_longitude=opt_field(rd, "target_longitude"),
            target_distance=opt_field(rd, "target_distance"),
            target_altitude=opt_field(rd, "target_altitude"),
        )
    sens = None
    if has_field(p, "sensor_data"):
        sd = p.sensor_data
        sens = SensorData(target_temperature=opt_field(sd, "target_temperature"))
    return PayloadTelemetry(
        id=p.id,
        name=p.name,
        timestamp=proto_ts_to_datetime(p.timestamp),
        camera=cam,
        range_finder=rf,
        sensor=sens,
    )


def _decode_sub_asset_telemetry_details(
    sn: str | None, base_id: str, timestamp, wind_speed, heading, t
) -> SubAssetTelemetry:
    from zqnt_utils.generated.zqnt import common_pb2  # type: ignore[import]

    payload = _decode_payload(t.payload_telemetry) if has_field(t, "payload_telemetry") else None
    batt = None
    if has_field(t, "battery_information"):
        bi = t.battery_information
        batt = SubAssetBatteryInfo(
            percentage=opt_field(bi, "percentage"),
            remaining_time=opt_field(bi, "remaining_time"),
            return_to_home_power=opt_field(bi, "return_to_home_power"),
        )
    return SubAssetTelemetry(
        id=base_id,
        timestamp=timestamp,
        sn=sn,
        latitude=None,
        longitude=None,
        absolute_altitude=None,
        relative_altitude=None,
        horizontal_speed=opt_field(t, "horizontal_speed"),
        vertical_speed=opt_field(t, "vertical_speed"),
        wind_speed=wind_speed,
        wind_direction=opt_field(t, "wind_direction"),
        heading=heading,
        gear=opt_field(t, "gear"),
        payload=payload,
        battery=batt,
        height_limit=opt_field(t, "height_limit"),
        home_distance=opt_field(t, "home_distance"),
        total_movement_distance=opt_field(t, "total_movement_distance"),
        total_movement_time=opt_field(t, "total_movement_time"),
        mode=_enum_name(common_pb2.SubAssetMode, t.mode) if has_field(t, "mode") else None,
        country=opt_field(t, "country"),
    )


def proto_to_stream_telemetry_response(proto) -> StreamTelemetryResponse:
    """Decode one frame of ``LiveDataTelemetryResponse``.

    The ``telemetry`` oneof's ``data`` branch (a ``Telemetry`` envelope) carries
    common fields (id/timestamp/sn/lat/lon/altitude/heading/wind_speed) plus a
    nested ``source`` oneof (``asset`` / ``sub_asset``) for the type-specific
    detail. ``live_stream_state`` / ``stream_heartbeat`` / ``source_status``
    frames decode to an all-``None`` payload (matching prior behaviour for
    frames outside the asset/sub-asset/error shape this dataclass models).
    """
    which = proto.WhichOneof("telemetry")
    asset_t: AssetTelemetry | None = None
    sub_t: SubAssetTelemetry | None = None
    error: StreamTelemetryError | None = None

    if which == "data":
        data = proto.data
        ts = proto_ts_to_datetime(data.timestamp)
        source = data.WhichOneof("source")
        if source == "asset":
            asset_t = _decode_asset_telemetry_details(opt_field(data, "sn"), data.id, ts, data.asset)
            asset_t.latitude = opt_field(data, "latitude")
            asset_t.longitude = opt_field(data, "longitude")
            asset_t.absolute_altitude = opt_field(data, "absolute_altitude")
            asset_t.relative_altitude = opt_field(data, "relative_altitude")
            asset_t.heading = opt_field(data, "heading")
            asset_t.wind_speed = opt_field(data, "wind_speed")
        elif source == "sub_asset":
            sub_t = _decode_sub_asset_telemetry_details(
                opt_field(data, "sn"),
                data.id,
                ts,
                opt_field(data, "wind_speed"),
                opt_field(data, "heading"),
                data.sub_asset,
            )
            sub_t.latitude = opt_field(data, "latitude")
            sub_t.longitude = opt_field(data, "longitude")
            sub_t.absolute_altitude = opt_field(data, "absolute_altitude")
            sub_t.relative_altitude = opt_field(data, "relative_altitude")
    elif which == "error":
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
        has_errors=proto.has_errors,
        asset_id=opt_field(proto, "asset_id"),
        asset_telemetry=asset_t,
        sub_asset_telemetry=sub_t,
        error=error,
    )

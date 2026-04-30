"""
Internal converters between protobuf messages and SDK plain-Python models.

All functions that convert *from* proto accept raw proto objects (duck-typed)
so this module never needs to import the generated pb2 files directly.

Functions that build proto objects receive the pb2 module as a parameter so
they can construct the right classes without a hard import dependency here.
"""

from datetime import datetime, timezone

from ..models.asset import Asset, SubAsset
from ..models.common import (
    AssetAirConditionerState,
    AssetConnection,
    AssetCoverState,
    AssetMode,
    AssetType,
    AssetVendor,
    BoundingBox,
    Capabilities,
    Capability,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    CommandProgress,
    Coordinates,
    DetectionResponse,
    DetectionResult,
    EdgeResponse,
    ErrorCode,
    ErrorMessage,
    LiveStreamStartRequest,
    LiveStreamStopRequest,
    LiveStreamType,
    ManualControlInput,
    ManualControlRequest,
    ManualControlState,
    MissionStatus,
    MissionType,
    NetworkStateQuality,
    NetworkType,
    Rainfall,
    RequestContext,
    ReturnToHomeRequest,
    SubAssetMode,
    TaskStatus,
    TaskType,
)
from ..models.task import (
    AreaMappingTaskConfig,
    AreaVertex,
    DetectTaskConfig,
    DetectionParameter,
    FollowTaskConfig,
    Mission,
    PoiTaskConfig,
    Task,
    TrackTaskConfig,
    Waypoint,
    WaypointTaskConfig,
)
from ..models.telemetry import (
    AssetAirConditioner,
    AssetNetworkInfo,
    AssetPositionState,
    AssetSubAssetInfo,
    AssetTelemetry,
    CameraData,
    PayloadTelemetry,
    RangeFinderData,
    SensorData,
    SubAssetBatteryInfo,
    SubAssetTelemetry,
)


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------


def _ts_to_dt(ts) -> datetime | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts.seconds + ts.nanos / 1e9, tz=timezone.utc)


def _dt_to_ts(pb2_timestamp_module, dt: datetime | None):
    ts = pb2_timestamp_module.Timestamp()
    if dt is not None:
        ts.FromDatetime(dt)
    else:
        ts.GetCurrentTime()
    return ts


def _now_ts(pb2_timestamp_module):
    ts = pb2_timestamp_module.Timestamp()
    ts.GetCurrentTime()
    return ts


# ---------------------------------------------------------------------------
# proto → model
# ---------------------------------------------------------------------------


def proto_to_request_context(base) -> RequestContext:
    return RequestContext(
        tid=base.tid,
        sn=base.sn,
        timestamp=_ts_to_dt(base.timestamp) or datetime.now(tz=timezone.utc),
    )


def proto_to_coordinates(c) -> Coordinates:
    return Coordinates(latitude=c.latitude, longitude=c.longitude, altitude=c.altitude)


def proto_to_return_to_home(r) -> ReturnToHomeRequest:
    return ReturnToHomeRequest(
        altitude=r.altitude if r.HasField("altitude") else None  # type: ignore[attr-defined]
    )


def proto_to_manual_control_request(r) -> ManualControlRequest:
    return ManualControlRequest(
        client_id=r.clientId,
        user_id=r.userId,
        session_id=r.sessionId,
        reason=r.reason if r.HasField("reason") else None,  # type: ignore[attr-defined]
    )


def proto_to_manual_control_input(i) -> ManualControlInput:
    def _opt(msg, field):
        return getattr(msg, field) if msg.HasField(field) else None  # type: ignore[attr-defined]

    return ManualControlInput(
        roll=_opt(i, "roll"),
        pitch=_opt(i, "pitch"),
        yaw=_opt(i, "yaw"),
        throttle=_opt(i, "throttle"),
        gimbal_pitch=_opt(i, "gimbalPitch"),
    )


def proto_to_live_stream_start(r) -> LiveStreamStartRequest:
    return LiveStreamStartRequest(
        video_id=r.videoId,
        stream_server=r.streamServer,
        stream_type=LiveStreamType(r.streamType),
        asset_type=AssetType(r.assetType),
    )


def proto_to_live_stream_stop(r) -> LiveStreamStopRequest:
    return LiveStreamStopRequest(video_id=r.videoId)


def proto_to_change_lens(r) -> ChangeCameraLensRequest:
    return ChangeCameraLensRequest(lens=r.lens if r.HasField("lens") else None)  # type: ignore[attr-defined]


def proto_to_change_zoom(r) -> ChangeCameraZoomRequest:
    return ChangeCameraZoomRequest(
        lens=r.lens if r.HasField("lens") else None,  # type: ignore[attr-defined]
        zoom=r.zoom if r.HasField("zoom") else None,  # type: ignore[attr-defined]
    )


def proto_to_sub_asset(s) -> SubAsset:
    return SubAsset(
        id=s.id,
        sn=s.sn,
        name=s.name,
        type=AssetType(s.type),
        vendor=AssetVendor(s.vendor),
        connection=AssetConnection(s.connection),
        model=s.model,
        organization=s.organization,
        online=s.online,
        stream_type=LiveStreamType(s.streamType),
        connection_string=s.connectionString
        if s.HasField("connectionString")
        else None,  # type: ignore[attr-defined]
        port=s.port if s.HasField("port") else None,  # type: ignore[attr-defined]
        live_stream_server=s.liveStreamServer
        if s.HasField("liveStreamServer")
        else None,  # type: ignore[attr-defined]
        external_device_type=s.externalDeviceType
        if s.HasField("externalDeviceType")
        else None,  # type: ignore[attr-defined]
        external_device_sub_type=s.externalDeviceSubType
        if s.HasField("externalDeviceSubType")
        else None,  # type: ignore[attr-defined]
        external_id=s.externalId if s.HasField("externalId") else None,  # type: ignore[attr-defined]
        stream_url_predefined=s.streamUrlPredefined
        if s.HasField("streamUrlPredefined")
        else None,  # type: ignore[attr-defined]
    )


def proto_to_asset(a) -> Asset:
    sub = proto_to_sub_asset(a.subAssetDTO) if a.HasField("subAssetDTO") else None  # type: ignore[attr-defined]
    return Asset(
        id=a.id,
        sn=a.sn,
        name=a.name,
        type=AssetType(a.type),
        vendor=AssetVendor(a.vendor),
        connection=AssetConnection(a.connection),
        model=a.model,
        organization=a.organization,
        online=a.online,
        stream_type=LiveStreamType(a.streamType),
        connection_string=a.connectionString
        if a.HasField("connectionString")
        else None,  # type: ignore[attr-defined]
        port=a.port if a.HasField("port") else None,  # type: ignore[attr-defined]
        live_stream_server=a.liveStreamServer
        if a.HasField("liveStreamServer")
        else None,  # type: ignore[attr-defined]
        external_device_type=a.externalDeviceType
        if a.HasField("externalDeviceType")
        else None,  # type: ignore[attr-defined]
        external_device_sub_type=a.externalDeviceSubType
        if a.HasField("externalDeviceSubType")
        else None,  # type: ignore[attr-defined]
        external_id=a.externalId if a.HasField("externalId") else None,  # type: ignore[attr-defined]
        sub_asset=sub,
    )


def _sub_asset_to_proto(sub: "SubAsset", common_pb2):
    kwargs = dict(
        id=sub.id,
        sn=sub.sn,
        name=sub.name,
        type=sub.type.value,
        vendor=sub.vendor.value,
        connection=sub.connection.value,
        model=sub.model,
        organization=sub.organization,
        online=sub.online,
        streamType=sub.stream_type.value,
    )
    if sub.connection_string is not None:
        kwargs["connectionString"] = sub.connection_string
    if sub.port is not None:
        kwargs["port"] = sub.port
    if sub.live_stream_server is not None:
        kwargs["liveStreamServer"] = sub.live_stream_server
    if sub.external_device_type is not None:
        kwargs["externalDeviceType"] = sub.external_device_type
    if sub.external_device_sub_type is not None:
        kwargs["externalDeviceSubType"] = sub.external_device_sub_type
    if sub.external_id is not None:
        kwargs["externalId"] = sub.external_id
    if sub.stream_url_predefined is not None:
        kwargs["streamUrlPredefined"] = sub.stream_url_predefined
    return common_pb2.SubAssetProtoDTO(**kwargs)


def asset_to_proto(asset: "Asset", common_pb2):
    kwargs = dict(
        id=asset.id,
        sn=asset.sn,
        name=asset.name,
        type=asset.type.value,
        vendor=asset.vendor.value,
        connection=asset.connection.value,
        model=asset.model,
        organization=asset.organization,
        online=asset.online,
        streamType=asset.stream_type.value,
    )
    if asset.connection_string is not None:
        kwargs["connectionString"] = asset.connection_string
    if asset.port is not None:
        kwargs["port"] = asset.port
    if asset.live_stream_server is not None:
        kwargs["liveStreamServer"] = asset.live_stream_server
    if asset.external_device_type is not None:
        kwargs["externalDeviceType"] = asset.external_device_type
    if asset.external_device_sub_type is not None:
        kwargs["externalDeviceSubType"] = asset.external_device_sub_type
    if asset.external_id is not None:
        kwargs["externalId"] = asset.external_id
    if asset.sub_asset is not None:
        kwargs["subAssetDTO"] = _sub_asset_to_proto(asset.sub_asset, common_pb2)
    return common_pb2.AssetProtoDTO(**kwargs)


def _opt_field(msg, field):
    """Return proto optional scalar or None."""
    try:
        return getattr(msg, field) if msg.HasField(field) else None  # type: ignore[attr-defined]
    except ValueError:
        # HasField not supported for non-oneof / non-optional scalars
        return getattr(msg, field, None)


def proto_to_waypoint(w) -> Waypoint:
    return Waypoint(
        latitude=w.latitude,
        longitude=w.longitude,
        altitude=_opt_field(w, "altitude"),
        speed=_opt_field(w, "speed"),
        fly_through=_opt_field(w, "flyTrough"),
        wp_order=_opt_field(w, "wpOrder"),
        gimbal_pitch=_opt_field(w, "gimbalPitch"),
    )


def proto_to_waypoint_config(c) -> WaypointTaskConfig:
    return WaypointTaskConfig(
        flight_id=c.flightId,
        waypoints=[proto_to_waypoint(w) for w in c.waypoints],
        fly_to_wayline_mode=_opt_field(c, "flyToWaylineMode"),
        wayline_finish_action=_opt_field(c, "waylineFinishAction"),
        wayline_type=_opt_field(c, "waylineType"),
        wayline_turn_mode=_opt_field(c, "waylineTurnMode"),
        use_straight_line=_opt_field(c, "useStraightLine"),
        wayline_precision_type=_opt_field(c, "waylinePrecisionType"),
        exit_wayline_when_rc_lost=_opt_field(c, "exitWaylineWhenRcLostEnum"),
        rc_lost_action=_opt_field(c, "rcLostActionEnum"),
        out_of_control_action=_opt_field(c, "outOfControlAction"),
        take_off_security_height=_opt_field(c, "takeOffSecurityHeight"),
        rth_altitude=_opt_field(c, "rthAltitude"),
        rth_mode=_opt_field(c, "rthMode"),
        rth_speed=_opt_field(c, "rthSpeed"),
        global_speed=_opt_field(c, "globalSpeed"),
        global_transition_speed=_opt_field(c, "globalTransitionSpeed"),
        global_height=_opt_field(c, "globalHeight"),
        gimbal_pitch_mode=_opt_field(c, "gimbalPitchMode"),
        global_gimbal_pitch=_opt_field(c, "globalGimbalPitch"),
        payload_imaging_type=_opt_field(c, "payloadImagingType"),
        file_url=_opt_field(c, "fileUrl"),
        file_md5=_opt_field(c, "fileMd5"),
        flight_area_file_url=_opt_field(c, "flightAreaFileUrl"),
        flight_area_checksum=_opt_field(c, "flightAreaChecksum"),
    )


def proto_to_detect_config(c) -> DetectTaskConfig:
    params = [
        DetectionParameter(
            name=p.name,
            value=p.value,
            description=_opt_field(p, "description"),
        )
        for p in c.detectionParameters
    ]
    return DetectTaskConfig(
        detection_targets=list(c.detectionTargets),
        detection_mode=_opt_field(c, "detectionMode"),
        area_latitude=_opt_field(c, "areaLatitude"),
        area_longitude=_opt_field(c, "areaLongitude"),
        area_radius=_opt_field(c, "areaRadius"),
        detection_altitude=_opt_field(c, "detectionAltitude"),
        scan_pattern=_opt_field(c, "scanPattern"),
        scan_speed=_opt_field(c, "scanSpeed"),
        thermal_detection=_opt_field(c, "thermalDetection"),
        visual_detection=_opt_field(c, "visualDetection"),
        min_confidence=_opt_field(c, "minConfidence"),
        max_detections=_opt_field(c, "maxDetections"),
        auto_capture_on_detection=_opt_field(c, "autoCaptureOnDetection"),
        investigate_detections=_opt_field(c, "investigateDetections"),
        investigation_distance=_opt_field(c, "investigationDistance"),
        investigation_duration=_opt_field(c, "investigationDuration"),
        gimbal_pitch=_opt_field(c, "gimbalPitch"),
        enable_zoom=_opt_field(c, "enableZoom"),
        zoom_level=_opt_field(c, "zoomLevel"),
        max_duration=_opt_field(c, "maxDuration"),
        on_max_detections_action=_opt_field(c, "onMaxDetectionsAction"),
        realtime_alerts=_opt_field(c, "realtimeAlerts"),
        ai_model_id=_opt_field(c, "aiModelId"),
        detection_parameters=params,
    )


def proto_to_task(t) -> Task:
    wp_config = None
    detect_config = None
    area_config = None
    poi_config = None
    follow_config = None
    track_config = None

    which = t.WhichOneof("taskConfig")
    if which == "waypointConfig":
        wp_config = proto_to_waypoint_config(t.waypointConfig)
    elif which == "detectConfig":
        detect_config = proto_to_detect_config(t.detectConfig)
    # area / poi / follow / track configs follow the same pattern but are omitted
    # for brevity – add converters as needed.

    return Task(
        id=_opt_field(t, "id"),
        mission_id=_opt_field(t, "missionId"),
        name=_opt_field(t, "name"),
        description=_opt_field(t, "description"),
        task_type=TaskType(_opt_field(t, "taskType") or 0),
        status=TaskStatus(t.status),
        asset_id=_opt_field(t, "assetId"),
        sn_number=_opt_field(t, "snNumber"),
        current_progress=_opt_field(t, "currentProgress"),
        current_step=_opt_field(t, "currentStep"),
        waypoint_config=wp_config,
        detect_config=detect_config,
        area_mapping_config=area_config,
        poi_config=poi_config,
        follow_config=follow_config,
        track_config=track_config,
        created_at=_ts_to_dt(_opt_field(t, "createdAt")),
        modified_at=_ts_to_dt(_opt_field(t, "modifiedAt")),
    )


def proto_to_mission(m) -> Mission:
    return Mission(
        id=_opt_field(m, "id"),
        name=m.name,
        description=m.description,
        status=MissionStatus(m.status),
        type=MissionType(m.type),
        tasks=[proto_to_task(t) for t in m.tasks],
        geo_json=_opt_field(m, "geoJson"),
        assigned_assets=list(m.assignedAssets),
        start_date=_ts_to_dt(_opt_field(m, "startDate")),
        end_date=_ts_to_dt(_opt_field(m, "endDate")),
        created_at=_ts_to_dt(_opt_field(m, "createdAt")),
        modified_at=_ts_to_dt(_opt_field(m, "modifiedAt")),
    )


def proto_to_asset_telemetry(t) -> AssetTelemetry:
    net = None
    if t.HasField("networkInformation"):  # type: ignore[attr-defined]
        ni = t.networkInformation
        net = AssetNetworkInfo(
            type=NetworkType(ni.type) if ni.HasField("type") else None,
            rate=ni.rate if ni.HasField("rate") else None,
            quality=NetworkStateQuality(ni.quality) if ni.HasField("quality") else None,
        )
    ac = None
    if t.HasField("airConditioner"):  # type: ignore[attr-defined]
        a = t.airConditioner
        ac = AssetAirConditioner(
            state=AssetAirConditionerState(a.state) if a.HasField("state") else None,
            switch_time=a.switchTime if a.HasField("switchTime") else None,
        )
    sub_info = None
    if t.HasField("subAssetInformation"):  # type: ignore[attr-defined]
        si = t.subAssetInformation
        sub_info = AssetSubAssetInfo(
            sn=si.sn if si.HasField("sn") else None,
            model=si.model if si.HasField("model") else None,
            paired=si.paired if si.HasField("paired") else None,
            online=si.online if si.HasField("online") else None,
        )
    pos = None
    if t.HasField("positionState"):  # type: ignore[attr-defined]
        ps = t.positionState
        pos = AssetPositionState(
            gps_number=ps.gpsNumber if ps.HasField("gpsNumber") else None,
            rtk_number=ps.rtkNumber if ps.HasField("rtkNumber") else None,
            quality=ps.quality if ps.HasField("quality") else None,
        )
    return AssetTelemetry(
        id=t.id,
        timestamp=_ts_to_dt(t.timestamp),
        latitude=_opt_field(t, "latitude"),
        longitude=_opt_field(t, "longitude"),
        absolute_altitude=_opt_field(t, "absoluteAltitude"),
        relative_altitude=_opt_field(t, "relativeAltitude"),
        environment_temp=_opt_field(t, "environmentTemp"),
        inside_temp=_opt_field(t, "insideTemp"),
        humidity=_opt_field(t, "humidity"),
        mode=AssetMode(_opt_field(t, "mode") or 0)
        if _opt_field(t, "mode") is not None
        else None,
        rainfall=Rainfall(_opt_field(t, "rainfall") or 0)
        if _opt_field(t, "rainfall") is not None
        else None,
        sub_asset_info=sub_info,
        sub_asset_at_home=_opt_field(t, "subAssetAtHome"),
        sub_asset_charging=_opt_field(t, "subAssetCharging"),
        sub_asset_percentage=_opt_field(t, "subAssetPercentage"),
        heading=_opt_field(t, "heading"),
        debug_mode_open=_opt_field(t, "debugModeOpen"),
        has_active_manual_control_session=_opt_field(
            t, "hasActiveManualControlSession"
        ),
        cover_state=AssetCoverState(_opt_field(t, "coverState") or 0)
        if _opt_field(t, "coverState") is not None
        else None,
        working_voltage=_opt_field(t, "workingVoltage"),
        working_current=_opt_field(t, "workingCurrent"),
        supply_voltage=_opt_field(t, "supplyVoltage"),
        wind_speed=_opt_field(t, "windSpeed"),
        position_valid=_opt_field(t, "positionValid"),
        network_info=net,
        air_conditioner=ac,
        manual_control_state=ManualControlState(
            _opt_field(t, "manualControlState") or 0
        )
        if _opt_field(t, "manualControlState") is not None
        else None,
        position_state=pos,
    )


def proto_to_sub_asset_telemetry(t) -> SubAssetTelemetry:
    payload = None
    if t.HasField("payloadTelemetry"):  # type: ignore[attr-defined]
        p = t.payloadTelemetry
        cam = None
        if p.HasField("cameraData"):
            cd = p.cameraData
            cam = CameraData(
                current_lens=cd.currentLens if cd.HasField("currentLens") else None,
                gimbal_pitch=cd.gimbalPitch if cd.HasField("gimbalPitch") else None,
                gimbal_yaw=cd.gimbalYaw if cd.HasField("gimbalYaw") else None,
                zoom_factor=cd.zoomFactor if cd.HasField("zoomFactor") else None,
                gimbal_roll=cd.gimbalRoll if cd.HasField("gimbalRoll") else None,
            )
        rf = None
        if p.HasField("rangeFinderData"):
            rd = p.rangeFinderData
            rf = RangeFinderData(
                target_latitude=rd.targetLatitude
                if rd.HasField("targetLatitude")
                else None,
                target_longitude=rd.targetLongitude
                if rd.HasField("targetLongitude")
                else None,
                target_distance=rd.targetDistance
                if rd.HasField("targetDistance")
                else None,
                target_altitude=rd.targetAltitude
                if rd.HasField("targetAltitude")
                else None,
            )
        sens = None
        if p.HasField("sensorData"):
            sd = p.sensorData
            sens = SensorData(
                target_temperature=sd.targetTemperature
                if sd.HasField("targetTemperature")
                else None,
            )
        payload = PayloadTelemetry(
            id=p.id,
            name=p.name,
            timestamp=_ts_to_dt(p.timestamp),
            camera=cam,
            range_finder=rf,
            sensor=sens,
        )
    batt = None
    if t.HasField("batteryInformation"):  # type: ignore[attr-defined]
        bi = t.batteryInformation
        batt = SubAssetBatteryInfo(
            percentage=bi.percentage if bi.HasField("percentage") else None,
            remaining_time=bi.remainingTime if bi.HasField("remainingTime") else None,
            return_to_home_power=bi.returnToHomePower
            if bi.HasField("returnToHomePower")
            else None,
        )
    return SubAssetTelemetry(
        id=t.id,
        timestamp=_ts_to_dt(t.timestamp),
        latitude=_opt_field(t, "latitude"),
        longitude=_opt_field(t, "longitude"),
        absolute_altitude=_opt_field(t, "absoluteAltitude"),
        relative_altitude=_opt_field(t, "relativeAltitude"),
        horizontal_speed=_opt_field(t, "horizontalSpeed"),
        vertical_speed=_opt_field(t, "verticalSpeed"),
        wind_speed=_opt_field(t, "windSpeed"),
        wind_direction=_opt_field(t, "windDirection"),
        heading=_opt_field(t, "heading"),
        gear=_opt_field(t, "gear"),
        payload=payload,
        battery=batt,
        height_limit=_opt_field(t, "heightLimit"),
        home_distance=_opt_field(t, "homeDistance"),
        total_movement_distance=_opt_field(t, "totalMovementDistance"),
        total_movement_time=_opt_field(t, "totalMovementTime"),
        mode=SubAssetMode(_opt_field(t, "mode") or 0)
        if _opt_field(t, "mode") is not None
        else None,
        country=_opt_field(t, "country"),
    )


# ---------------------------------------------------------------------------
# model → proto
# ---------------------------------------------------------------------------


def capabilities_to_proto(caps: Capabilities, common_pb2, timestamp_pb2):
    ts = _now_ts(timestamp_pb2)
    proto_caps = [
        common_pb2.Capability(
            command=c.command,
            description=c.description,
            available=c.available,
            unavailableReason=c.unavailable_reason or "",
            metadata=c.metadata,
        )
        for c in caps.capabilities
    ]
    return common_pb2.CurrentCapabilities(
        assetSn=caps.asset_sn,
        assetType=int(caps.asset_type),
        capabilities=proto_caps,
        timestamp=ts,
    )


def edge_response_to_proto(
    response: EdgeResponse, edge_pb2, timestamp_pb2, empty_pb2, common_pb2=None
):
    ts = _now_ts(timestamp_pb2)
    kwargs: dict = {
        "hasErrors": not response.success,
        "tid": response.tid,
        "sn": response.sn,
        "timestamp": ts,
    }
    if response.asset_id:
        kwargs["assetId"] = response.asset_id
    if response.message:
        kwargs["responseMessage"] = response.message

    if response.error:
        err_ts = _now_ts(timestamp_pb2)
        # GlobalErrorMessage lives in common_pb2, not edge_pb2
        _common = common_pb2 if common_pb2 is not None else edge_pb2
        kwargs["error"] = _common.GlobalErrorMessage(
            timestamp=err_ts,
            errorMessage=response.error.message,
            errorCode=int(response.error.code),
        )
    elif response.stream_url or response.video_id:
        kwargs["liveStreamStartResponse"] = edge_pb2.LiveStreamStartResponse(
            streamUrl=response.stream_url or "",
            videoId=response.video_id or "",
        )
    elif response.progress:
        kwargs["progress"] = edge_pb2.CommandProgress(
            progress=response.progress.progress,
            state=response.progress.state,
            leftTimeInSeconds=response.progress.left_time_seconds,
        )
    else:
        kwargs["empty"] = empty_pb2.Empty()

    return edge_pb2.EdgeResponse(**kwargs)

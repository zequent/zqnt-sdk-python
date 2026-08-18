"""
Internal converters between protobuf messages and SDK plain-Python models.

All functions that convert *from* proto accept raw proto objects (duck-typed)
so this module never needs to import the generated pb2 files directly.

Functions that build proto objects receive the pb2 module as a parameter so
they can construct the right classes without a hard import dependency here.
"""

import json
import types
import typing
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum

from zqnt_utils.proto_utils import parse_enum

from ..models.asset import Asset, SubAsset
from ..models.common import (
    AssetAirConditionerState,
    AssetConnection,
    AssetCoverState,
    AssetMode,
    AssetType,
    AssetVendor,
    Capabilities,
    ChangeCameraLensRequest,
    ChangeCameraZoomRequest,
    Coordinates,
    CustomCommandRequest,
    CustomCommandResponse,
    EdgeResponse,
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
    VehicleAction,
)
from ..models.task import (
    AreaMappingTaskConfig,
    AreaVertex,
    DetectionParameter,
    DetectTaskConfig,
    FlightTaskBreakReason,
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
        client_id=r.client_id,
        user_id=r.user_id,
        session_id=r.session_id,
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
        gimbal_pitch=_opt(i, "gimbal_pitch"),
    )


def proto_to_live_stream_start(r) -> LiveStreamStartRequest:
    return LiveStreamStartRequest(
        video_id=r.video_id,
        stream_server=r.stream_server,
        stream_type=LiveStreamType(r.stream_type),
        asset_type=AssetType(r.asset_type),
    )


def proto_to_live_stream_stop(r) -> LiveStreamStopRequest:
    return LiveStreamStopRequest(video_id=r.video_id)


def proto_to_change_lens(r) -> ChangeCameraLensRequest:
    return ChangeCameraLensRequest(lens=r.lens if r.HasField("lens") else None)  # type: ignore[attr-defined]


def proto_to_change_zoom(r) -> ChangeCameraZoomRequest:
    return ChangeCameraZoomRequest(
        lens=r.lens if r.HasField("lens") else None,  # type: ignore[attr-defined]
        zoom=r.zoom if r.HasField("zoom") else None,  # type: ignore[attr-defined]
    )


def proto_to_sub_asset(s) -> SubAsset:
    return SubAsset(
        id=_opt_field(s, "id"),
        sn=s.sn,
        name=s.name,
        type=parse_enum(AssetType, s.type, AssetType.UNKNOWN),
        vendor=parse_enum(AssetVendor, s.vendor, AssetVendor.DJI),
        connection=parse_enum(AssetConnection, s.connection, AssetConnection.MQTT),
        model=s.model,
        system_connection_string=_opt_field(s, "system_connection_string"),
        external_device_type=_opt_field(s, "external_device_type"),
        external_device_sub_type=_opt_field(s, "external_device_sub_type"),
        external_id=_opt_field(s, "external_id"),
        stream_url_predefined=_opt_field(s, "stream_url_predefined"),
        live_stream_push_url=_opt_field(s, "live_stream_push_url"),
        live_stream_pull_url=_opt_field(s, "live_stream_pull_url"),
        modified_from=_opt_field(s, "modified_from"),
    )


def proto_to_asset(a) -> Asset:
    return Asset(
        id=_opt_field(a, "id"),
        sn=a.sn,
        name=a.name,
        type=parse_enum(AssetType, a.type, AssetType.UNKNOWN),
        vendor=parse_enum(AssetVendor, a.vendor, AssetVendor.DJI),
        connection=parse_enum(AssetConnection, a.connection, AssetConnection.MQTT),
        model=a.model,
        organization=a.organization,
        system_connection_string=_opt_field(a, "system_connection_string"),
        external_device_type=_opt_field(a, "external_device_type"),
        external_device_sub_type=_opt_field(a, "external_device_sub_type"),
        external_id=_opt_field(a, "external_id"),
        live_stream_push_url=_opt_field(a, "live_stream_push_url"),
        live_stream_pull_url=_opt_field(a, "live_stream_pull_url"),
        modified_from=_opt_field(a, "modified_from"),
        sub_assets=[proto_to_sub_asset(s) for s in a.sub_assets],
    )


def _sub_asset_to_proto(sub: "SubAsset", common_pb2):
    kwargs = dict(
        id=sub.id,
        sn=sub.sn,
        name=sub.name,
        type=f"ASSET_TYPE_{sub.type.name}",
        vendor=f"ASSET_VENDOR_{sub.vendor.name}",
        connection=sub.connection.name,
        model=sub.model,
    )
    if sub.system_connection_string is not None:
        kwargs["system_connection_string"] = sub.system_connection_string
    if sub.external_device_type is not None:
        kwargs["external_device_type"] = sub.external_device_type
    if sub.external_device_sub_type is not None:
        kwargs["external_device_sub_type"] = sub.external_device_sub_type
    if sub.external_id is not None:
        kwargs["external_id"] = sub.external_id
    if sub.stream_url_predefined is not None:
        kwargs["stream_url_predefined"] = sub.stream_url_predefined
    if sub.live_stream_push_url is not None:
        kwargs["live_stream_push_url"] = sub.live_stream_push_url
    if sub.live_stream_pull_url is not None:
        kwargs["live_stream_pull_url"] = sub.live_stream_pull_url
    if sub.modified_from is not None:
        kwargs["modified_from"] = sub.modified_from
    return common_pb2.SubAssetProtoDTO(**kwargs)


def asset_to_proto(asset: "Asset", common_pb2):
    kwargs = dict(
        id=asset.id,
        sn=asset.sn,
        name=asset.name,
        type=f"ASSET_TYPE_{asset.type.name}",
        vendor=f"ASSET_VENDOR_{asset.vendor.name}",
        connection=asset.connection.name,
        model=asset.model,
        organization=asset.organization,
    )
    if asset.system_connection_string is not None:
        kwargs["system_connection_string"] = asset.system_connection_string
    if asset.external_device_type is not None:
        kwargs["external_device_type"] = asset.external_device_type
    if asset.external_device_sub_type is not None:
        kwargs["external_device_sub_type"] = asset.external_device_sub_type
    if asset.external_id is not None:
        kwargs["external_id"] = asset.external_id
    if asset.live_stream_push_url is not None:
        kwargs["live_stream_push_url"] = asset.live_stream_push_url
    if asset.live_stream_pull_url is not None:
        kwargs["live_stream_pull_url"] = asset.live_stream_pull_url
    if asset.modified_from is not None:
        kwargs["modified_from"] = asset.modified_from
    if asset.sub_assets:
        kwargs["sub_assets"] = [_sub_asset_to_proto(s, common_pb2) for s in asset.sub_assets]
    return common_pb2.AssetProtoDTO(**kwargs)


def _opt_field(msg, field):
    """Return proto optional scalar or None."""
    try:
        return getattr(msg, field) if msg.HasField(field) else None  # type: ignore[attr-defined]
    except ValueError:
        # HasField not supported for non-oneof / non-optional scalars
        return getattr(msg, field, None)


def proto_to_waypoint(w) -> Waypoint:
    va_raw = _opt_field(w, "vehicle_action")
    vehicle_action = VehicleAction(va_raw) if va_raw is not None else None
    return Waypoint(
        latitude=w.latitude,
        longitude=w.longitude,
        altitude=_opt_field(w, "altitude"),
        speed=_opt_field(w, "speed"),
        fly_through=_opt_field(w, "fly_trough"),
        vehicle_action=vehicle_action,
        wp_order=_opt_field(w, "wp_order"),
        gimbal_pitch=_opt_field(w, "gimbal_pitch"),
    )


def proto_to_waypoint_config(c) -> WaypointTaskConfig:
    return WaypointTaskConfig(
        flight_id=c.external_task_id,
        waypoints=[proto_to_waypoint(w) for w in c.waypoints],
        fly_to_wayline_mode=_opt_field(c, "fly_to_wayline_mode"),
        wayline_finish_action=_opt_field(c, "wayline_finish_action"),
        wayline_type=_opt_field(c, "wayline_type"),
        wayline_turn_mode=_opt_field(c, "wayline_turn_mode"),
        use_straight_line=_opt_field(c, "use_straight_line"),
        wayline_precision_type=_opt_field(c, "wayline_precision_type"),
        exit_wayline_when_rc_lost=_opt_field(c, "exit_wayline_when_rc_lost_enum"),
        rc_lost_action=_opt_field(c, "rc_lost_action_enum"),
        out_of_control_action=_opt_field(c, "out_of_control_action"),
        take_off_security_height=_opt_field(c, "take_off_security_height"),
        rth_altitude=_opt_field(c, "rth_altitude"),
        rth_mode=_opt_field(c, "rth_mode"),
        rth_speed=_opt_field(c, "rth_speed"),
        global_speed=_opt_field(c, "global_speed"),
        global_transition_speed=_opt_field(c, "global_transition_speed"),
        global_height=_opt_field(c, "global_height"),
        gimbal_pitch_mode=_opt_field(c, "gimbal_pitch_mode"),
        global_gimbal_pitch=_opt_field(c, "global_gimbal_pitch"),
        payload_imaging_type=_opt_field(c, "payload_imaging_type"),
        file_url=_opt_field(c, "file_url"),
        file_md5=_opt_field(c, "file_md5"),
        flight_area_file_url=_opt_field(c, "flight_area_file_url"),
        flight_area_checksum=_opt_field(c, "flight_area_checksum"),
    )


def proto_to_detect_config(c) -> DetectTaskConfig:
    params = [
        DetectionParameter(
            name=p.name,
            value=p.value,
            description=_opt_field(p, "description"),
        )
        for p in c.detection_parameters
    ]
    return DetectTaskConfig(
        detection_targets=list(c.detection_targets),
        detection_mode=_opt_field(c, "detection_mode"),
        area_latitude=_opt_field(c, "area_latitude"),
        area_longitude=_opt_field(c, "area_longitude"),
        area_radius=_opt_field(c, "area_radius"),
        detection_altitude=_opt_field(c, "detection_altitude"),
        scan_pattern=_opt_field(c, "scan_pattern"),
        scan_speed=_opt_field(c, "scan_speed"),
        thermal_detection=_opt_field(c, "thermal_detection"),
        visual_detection=_opt_field(c, "visual_detection"),
        min_confidence=_opt_field(c, "min_confidence"),
        max_detections=_opt_field(c, "max_detections"),
        auto_capture_on_detection=_opt_field(c, "auto_capture_on_detection"),
        investigate_detections=_opt_field(c, "investigate_detections"),
        investigation_distance=_opt_field(c, "investigation_distance"),
        investigation_duration=_opt_field(c, "investigation_duration"),
        gimbal_pitch=_opt_field(c, "gimbal_pitch"),
        enable_zoom=_opt_field(c, "enable_zoom"),
        zoom_level=_opt_field(c, "zoom_level"),
        max_duration=_opt_field(c, "max_duration"),
        on_max_detections_action=_opt_field(c, "on_max_detections_action"),
        realtime_alerts=_opt_field(c, "realtime_alerts"),
        ai_model_id=_opt_field(c, "ai_model_id"),
        detection_parameters=params,
    )


def proto_to_area_mapping_config(c) -> AreaMappingTaskConfig:
    vertices = [
        AreaVertex(
            latitude=v.latitude,
            longitude=v.longitude,
            order=_opt_field(v, "order"),
        )
        for v in c.area_vertices
    ]
    return AreaMappingTaskConfig(
        survey_altitude=c.survey_altitude,
        area_vertices=vertices,
        flight_pattern=_opt_field(c, "flight_pattern"),
        front_overlap=_opt_field(c, "front_overlap"),
        side_overlap=_opt_field(c, "side_overlap"),
        speed=_opt_field(c, "speed"),
        gimbal_pitch=_opt_field(c, "gimbal_pitch"),
        camera_angle=_opt_field(c, "camera_angle"),
        terrain_following=_opt_field(c, "terrain_following"),
        ground_sampling_distance=_opt_field(c, "ground_sampling_distance"),
        enable_3d_reconstruction=_opt_field(c, "enable3_d_reconstruction"),
    )


def proto_to_poi_config(c) -> PoiTaskConfig:
    return PoiTaskConfig(
        poi_latitude=c.poi_latitude,
        poi_longitude=c.poi_longitude,
        poi_altitude=c.poi_altitude,
        orbit_radius=_opt_field(c, "orbit_radius"),
        orbit_speed=_opt_field(c, "orbit_speed"),
        flight_altitude=_opt_field(c, "flight_altitude"),
        number_of_orbits=_opt_field(c, "number_of_orbits"),
        orbit_direction=_opt_field(c, "orbit_direction"),
        start_angle=_opt_field(c, "start_angle"),
        end_angle=_opt_field(c, "end_angle"),
        capture_enabled=_opt_field(c, "capture_enabled"),
        capture_interval=_opt_field(c, "capture_interval"),
        lock_camera_on_poi=_opt_field(c, "lock_camera_on_poi"),
    )


def proto_to_follow_config(c) -> FollowTaskConfig:
    return FollowTaskConfig(
        target_type=c.target_type,
        initial_latitude=_opt_field(c, "initial_latitude"),
        initial_longitude=_opt_field(c, "initial_longitude"),
        follow_distance=_opt_field(c, "follow_distance"),
        relative_altitude=_opt_field(c, "relative_altitude"),
        max_speed=_opt_field(c, "max_speed"),
        follow_mode=_opt_field(c, "follow_mode"),
        angle_offset=_opt_field(c, "angle_offset"),
        obstacle_avoidance=_opt_field(c, "obstacle_avoidance"),
        max_duration=_opt_field(c, "max_duration"),
        max_distance_from_start=_opt_field(c, "max_distance_from_start"),
        lost_target_action=_opt_field(c, "lost_target_action"),
        lost_target_timeout=_opt_field(c, "lost_target_timeout"),
        lock_camera_on_target=_opt_field(c, "lock_camera_on_target"),
        gimbal_pitch_offset=_opt_field(c, "gimbal_pitch_offset"),
        auto_capture=_opt_field(c, "auto_capture"),
        capture_interval=_opt_field(c, "capture_interval"),
    )


def proto_to_track_config(c) -> TrackTaskConfig:
    return TrackTaskConfig(
        target_type=c.target_type,
        initial_latitude=_opt_field(c, "initial_latitude"),
        initial_longitude=_opt_field(c, "initial_longitude"),
        target_altitude=_opt_field(c, "target_altitude"),
        tracking_mode=_opt_field(c, "tracking_mode"),
        max_movement_radius=_opt_field(c, "max_movement_radius"),
        tracking_altitude=_opt_field(c, "tracking_altitude"),
        gimbal_tracking=_opt_field(c, "gimbal_tracking"),
        auto_zoom=_opt_field(c, "auto_zoom"),
        zoom_level=_opt_field(c, "zoom_level"),
        tracking_sensitivity=_opt_field(c, "tracking_sensitivity"),
        max_duration=_opt_field(c, "max_duration"),
        lost_target_action=_opt_field(c, "lost_target_action"),
        lost_target_timeout=_opt_field(c, "lost_target_timeout"),
        search_pattern=_opt_field(c, "search_pattern"),
        search_duration=_opt_field(c, "search_duration"),
        continuous_recording=_opt_field(c, "continuous_recording"),
        photo_capture=_opt_field(c, "photo_capture"),
        capture_interval=_opt_field(c, "capture_interval"),
        confidence_threshold=_opt_field(c, "confidence_threshold"),
    )


def _parse_task_type(raw) -> TaskType | None:
    """Parse task_type from proto string (e.g. 'TASK_TYPE_DETECT') or int."""
    if raw is None:
        return None
    if isinstance(raw, int):
        try:
            return TaskType(raw)
        except ValueError:
            return None
    s = str(raw)
    prefix = "TASK_TYPE_"
    name = s[len(prefix) :] if s.startswith(prefix) else s
    try:
        return TaskType[name]
    except KeyError:
        return None


# ---------------------------------------------------------------------------
# Legacy JSON-string config parsing
#
# Older systems still populate the deprecated `config` string field (JSON blob)
# instead of the type-safe `task_config` oneof. When the oneof is unset we parse
# that JSON into the matching typed config dataclass, keyed by task_type, so
# downstream consumers can rely on the typed configs regardless of the source.
# ---------------------------------------------------------------------------


def _norm_key(k: str) -> str:
    """Normalize a JSON/field key so camelCase, snake_case and PascalCase all match."""
    return "".join(c for c in k.lower() if c.isalnum())


def _unwrap_optional(tp):
    """Strip `| None` / Optional[...] down to the underlying type."""
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is getattr(types, "UnionType", None):
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _coerce_enum(enum_cls, value):
    if isinstance(value, enum_cls):
        return value
    try:
        if isinstance(value, str):
            if value in enum_cls.__members__:
                return enum_cls[value]
            return enum_cls(int(value))
        return enum_cls(value)
    except (KeyError, ValueError):
        return None


def _coerce_value(tp, value):
    if value is None:
        return None
    tp = _unwrap_optional(tp)
    if typing.get_origin(tp) is list:
        args = typing.get_args(tp)
        item_tp = args[0] if args else None
        if isinstance(value, list) and item_tp is not None:
            return [_coerce_value(item_tp, v) for v in value]
        return value
    if is_dataclass(tp) and isinstance(value, dict):
        return _dict_to_dataclass(tp, value)
    if isinstance(tp, type) and issubclass(tp, Enum):
        return _coerce_enum(tp, value)
    return value


def _dict_to_dataclass(cls, data):
    """Best-effort build of a dataclass from a (camelCase or snake_case) dict."""
    if not isinstance(data, dict):
        return None
    field_map = {_norm_key(f.name): f for f in fields(cls)}
    kwargs = {}
    for k, v in data.items():
        f = field_map.get(_norm_key(k))
        if f is None:
            continue
        kwargs[f.name] = _coerce_value(f.type, v)
    try:
        return cls(**kwargs)
    except TypeError:
        # Required field missing in the legacy blob — treat as unmappable.
        return None


_LEGACY_CONFIG_DISPATCH: dict[TaskType, tuple[str, type]] = {
    TaskType.WAYPOINT: ("waypoint_config", WaypointTaskConfig),
    TaskType.DETECT: ("detect_config", DetectTaskConfig),
    TaskType.AREA_MAPPING: ("area_mapping_config", AreaMappingTaskConfig),
    TaskType.POI: ("poi_config", PoiTaskConfig),
    TaskType.FOLLOW: ("follow_config", FollowTaskConfig),
    TaskType.TRACK: ("track_config", TrackTaskConfig),
}


def _parse_legacy_config(task_type: TaskType | None, raw: str | None):
    """Parse a legacy JSON-string config into (attr_name, typed_config) or None."""
    if not raw or task_type is None:
        return None
    entry = _LEGACY_CONFIG_DISPATCH.get(task_type)
    if entry is None:
        return None
    attr, cls = entry
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    obj = _dict_to_dataclass(cls, data)
    if obj is None:
        return None
    return attr, obj


def proto_to_task(t) -> Task:
    wp_config = None
    detect_config = None
    area_config = None
    poi_config = None
    follow_config = None
    track_config = None

    task_type = _parse_task_type(_opt_field(t, "task_type"))
    config_raw = _opt_field(t, "config")

    which = t.WhichOneof("task_config")
    if which == "waypoint_config":
        wp_config = proto_to_waypoint_config(t.waypoint_config)
    elif which == "detect_config":
        detect_config = proto_to_detect_config(t.detect_config)
    elif which == "area_mapping_config":
        area_config = proto_to_area_mapping_config(t.area_mapping_config)
    elif which == "poi_config":
        poi_config = proto_to_poi_config(t.poi_config)
    elif which == "follow_config":
        follow_config = proto_to_follow_config(t.follow_config)
    elif which == "track_config":
        track_config = proto_to_track_config(t.track_config)
    elif config_raw:
        # Legacy fallback: no typed oneof, but a deprecated JSON-string config.
        parsed = _parse_legacy_config(task_type, config_raw)
        if parsed is not None:
            attr, obj = parsed
            if attr == "waypoint_config":
                wp_config = obj
            elif attr == "detect_config":
                detect_config = obj
            elif attr == "area_mapping_config":
                area_config = obj
            elif attr == "poi_config":
                poi_config = obj
            elif attr == "follow_config":
                follow_config = obj
            elif attr == "track_config":
                track_config = obj

    break_reason_raw = _opt_field(t, "break_reason")
    break_reason = FlightTaskBreakReason(break_reason_raw) if break_reason_raw is not None else None

    return Task(
        id=_opt_field(t, "id"),
        mission_id=_opt_field(t, "mission_id"),
        name=_opt_field(t, "name"),
        description=_opt_field(t, "description"),
        task_type=task_type,
        status=TaskStatus(t.status),
        asset_id=_opt_field(t, "asset_id"),
        sn_number=_opt_field(t, "sn_number"),
        current_progress=_opt_field(t, "current_progress"),
        current_step=_opt_field(t, "current_step"),
        waypoint_config=wp_config,
        detect_config=detect_config,
        area_mapping_config=area_config,
        config=config_raw,
        poi_config=poi_config,
        follow_config=follow_config,
        track_config=track_config,
        break_reason=break_reason,
        external_command_type=_opt_field(t, "external_command_type"),
        modified_from=_opt_field(t, "modified_from"),
        created_at=_ts_to_dt(_opt_field(t, "created_at")),
        modified_at=_ts_to_dt(_opt_field(t, "modified_at")),
    )


def proto_to_mission(m) -> Mission:
    return Mission(
        id=_opt_field(m, "id"),
        name=m.name,
        description=m.description,
        status=MissionStatus(m.status),
        type=MissionType(m.type),
        tasks=[proto_to_task(t) for t in m.tasks],
        geo_json=_opt_field(m, "geo_json"),
        assigned_assets=list(m.assigned_assets),
        start_date=_ts_to_dt(_opt_field(m, "start_date")),
        end_date=_ts_to_dt(_opt_field(m, "end_date")),
        created_at=_ts_to_dt(_opt_field(m, "created_at")),
        modified_at=_ts_to_dt(_opt_field(m, "modified_at")),
    )


def proto_to_asset_telemetry(t) -> AssetTelemetry:
    net = None
    if t.HasField("network_information"):  # type: ignore[attr-defined]
        ni = t.network_information
        net = AssetNetworkInfo(
            type=NetworkType(ni.type) if ni.HasField("type") else None,
            rate=ni.rate if ni.HasField("rate") else None,
            quality=NetworkStateQuality(ni.quality) if ni.HasField("quality") else None,
        )
    ac = None
    if t.HasField("air_conditioner"):  # type: ignore[attr-defined]
        a = t.air_conditioner
        ac = AssetAirConditioner(
            state=AssetAirConditionerState(a.state) if a.HasField("state") else None,
            switch_time=a.switch_time if a.HasField("switch_time") else None,
        )
    sub_info = None
    if t.HasField("sub_asset_information"):  # type: ignore[attr-defined]
        si = t.sub_asset_information
        sub_info = AssetSubAssetInfo(
            sn=si.sn if si.HasField("sn") else None,
            model=si.model if si.HasField("model") else None,
            paired=si.paired if si.HasField("paired") else None,
            online=si.online if si.HasField("online") else None,
        )
    pos = None
    if t.HasField("position_state"):  # type: ignore[attr-defined]
        ps = t.position_state
        pos = AssetPositionState(
            gps_number=ps.gps_number if ps.HasField("gps_number") else None,
            rtk_number=ps.rtk_number if ps.HasField("rtk_number") else None,
            quality=ps.quality if ps.HasField("quality") else None,
        )
    return AssetTelemetry(
        id=t.id,
        timestamp=_ts_to_dt(t.timestamp),
        latitude=_opt_field(t, "latitude"),
        longitude=_opt_field(t, "longitude"),
        absolute_altitude=_opt_field(t, "absolute_altitude"),
        relative_altitude=_opt_field(t, "relative_altitude"),
        environment_temp=_opt_field(t, "environment_temp"),
        inside_temp=_opt_field(t, "inside_temp"),
        humidity=_opt_field(t, "humidity"),
        mode=AssetMode(_opt_field(t, "mode") or 0) if _opt_field(t, "mode") is not None else None,
        rainfall=Rainfall(_opt_field(t, "rainfall") or 0) if _opt_field(t, "rainfall") is not None else None,
        sub_asset_info=sub_info,
        sub_asset_at_home=_opt_field(t, "sub_asset_at_home"),
        sub_asset_charging=_opt_field(t, "sub_asset_charging"),
        sub_asset_percentage=_opt_field(t, "sub_asset_percentage"),
        heading=_opt_field(t, "heading"),
        debug_mode_open=_opt_field(t, "debug_mode_open"),
        has_active_manual_control_session=_opt_field(t, "has_active_manual_control_session"),
        cover_state=AssetCoverState(_opt_field(t, "cover_state") or 0)
        if _opt_field(t, "cover_state") is not None
        else None,
        working_voltage=_opt_field(t, "working_voltage"),
        working_current=_opt_field(t, "working_current"),
        supply_voltage=_opt_field(t, "supply_voltage"),
        wind_speed=_opt_field(t, "wind_speed"),
        position_valid=_opt_field(t, "position_valid"),
        network_info=net,
        air_conditioner=ac,
        manual_control_state=ManualControlState(_opt_field(t, "manual_control_state") or 0)
        if _opt_field(t, "manual_control_state") is not None
        else None,
        position_state=pos,
    )


def proto_to_sub_asset_telemetry(t) -> SubAssetTelemetry:
    payload = None
    if t.HasField("payload_telemetry"):  # type: ignore[attr-defined]
        p = t.payload_telemetry
        cam = None
        if p.HasField("camera_data"):
            cd = p.camera_data
            cam = CameraData(
                current_lens=cd.current_lens if cd.HasField("current_lens") else None,
                gimbal_pitch=cd.gimbal_pitch if cd.HasField("gimbal_pitch") else None,
                gimbal_yaw=cd.gimbal_yaw if cd.HasField("gimbal_yaw") else None,
                zoom_factor=cd.zoom_factor if cd.HasField("zoom_factor") else None,
                gimbal_roll=cd.gimbal_roll if cd.HasField("gimbal_roll") else None,
            )
        rf = None
        if p.HasField("range_finder_data"):
            rd = p.range_finder_data
            rf = RangeFinderData(
                target_latitude=rd.target_latitude if rd.HasField("target_latitude") else None,
                target_longitude=rd.target_longitude if rd.HasField("target_longitude") else None,
                target_distance=rd.target_distance if rd.HasField("target_distance") else None,
                target_altitude=rd.target_altitude if rd.HasField("target_altitude") else None,
            )
        sens = None
        if p.HasField("sensor_data"):
            sd = p.sensor_data
            sens = SensorData(
                target_temperature=sd.target_temperature if sd.HasField("target_temperature") else None,
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
    if t.HasField("battery_information"):  # type: ignore[attr-defined]
        bi = t.battery_information
        batt = SubAssetBatteryInfo(
            percentage=bi.percentage if bi.HasField("percentage") else None,
            remaining_time=bi.remaining_time if bi.HasField("remaining_time") else None,
            return_to_home_power=bi.return_to_home_power if bi.HasField("return_to_home_power") else None,
        )
    return SubAssetTelemetry(
        id=t.id,
        timestamp=_ts_to_dt(t.timestamp),
        latitude=_opt_field(t, "latitude"),
        longitude=_opt_field(t, "longitude"),
        absolute_altitude=_opt_field(t, "absolute_altitude"),
        relative_altitude=_opt_field(t, "relative_altitude"),
        horizontal_speed=_opt_field(t, "horizontal_speed"),
        vertical_speed=_opt_field(t, "vertical_speed"),
        wind_speed=_opt_field(t, "wind_speed"),
        wind_direction=_opt_field(t, "wind_direction"),
        heading=_opt_field(t, "heading"),
        gear=_opt_field(t, "gear"),
        payload=payload,
        battery=batt,
        height_limit=_opt_field(t, "height_limit"),
        home_distance=_opt_field(t, "home_distance"),
        total_movement_distance=_opt_field(t, "total_movement_distance"),
        total_movement_time=_opt_field(t, "total_movement_time"),
        mode=SubAssetMode(_opt_field(t, "mode") or 0) if _opt_field(t, "mode") is not None else None,
        country=_opt_field(t, "country"),
    )


# ---------------------------------------------------------------------------
# model → proto
# ---------------------------------------------------------------------------


def capabilities_to_proto(caps: Capabilities, common_pb2, timestamp_pb2):
    # NOTE: the wire contract for capabilities grew a much richer Capability Contract model
    # (CapabilityState enum instead of a plain bool, plus constraints/input_schema/output_schema/
    # errors/events/schema_version — see device-control-contracts.proto). This SDK's own
    # Capability/Capabilities dataclasses (edge_sdk/models/common.py) still only carry the old,
    # flat fields, so this is a best-effort mapping onto the new message shape, not a full
    # migration to the richer contract — adapters can't yet declare input_schema/output_schema/
    # errors/events through this SDK. That's real follow-up work (same thing edge-go-sdk deferred
    # for the same reason), not something to improvise silently here.
    ts = _now_ts(timestamp_pb2)
    proto_caps = [
        common_pb2.Capability(
            command_id=c.command,
            display_name=c.command,
            description=c.description,
            state=(common_pb2.CAPABILITY_STATE_AVAILABLE if c.available else common_pb2.CAPABILITY_STATE_UNSUPPORTED),
            unavailable_reason=c.unavailable_reason or "",
            metadata=c.metadata,
        )
        for c in caps.capabilities
    ]
    return common_pb2.AssetCapabilities(
        asset_sn=caps.asset_sn,
        asset_type=caps.asset_type.name,
        capabilities=proto_caps,
        timestamp=ts,
        snapshot_state=common_pb2.CAPABILITY_SNAPSHOT_STATE_CURRENT,
    )


def edge_response_to_proto(response: EdgeResponse, edge_pb2, timestamp_pb2, empty_pb2, common_pb2=None):
    # CommandResponse (like every other message below) lives in device-control-contracts.proto,
    # publicly re-exported through common_pb2 — edge_pb2 itself only defines the service, no
    # messages of its own. edge_pb2 is kept as a fallback for callers that don't pass common_pb2,
    # though none of the current ones rely on that anymore.
    _common = common_pb2 if common_pb2 is not None else edge_pb2

    ts = _now_ts(timestamp_pb2)
    meta_kwargs: dict = {
        "tid": response.tid,
        "sn": response.sn,
        "timestamp": ts,
    }
    if response.asset_id:
        meta_kwargs["asset_id"] = response.asset_id
    if response.message:
        meta_kwargs["response_message"] = response.message

    kwargs: dict = {
        "has_errors": not response.success,
        "meta": _common.ResponseMeta(**meta_kwargs),
    }

    if response.error:
        err_ts = _now_ts(timestamp_pb2)
        kwargs["error"] = _common.GlobalErrorMessage(
            timestamp=err_ts,
            error_message=response.error.message,
            error_code=int(response.error.code),
        )
    elif response.stream_url or response.video_id:
        kwargs["live_stream_start_response"] = _common.LiveStreamStartResponse(
            stream_url=response.stream_url or "",
            video_id=response.video_id or "",
        )
    elif response.progress:
        kwargs["progress"] = _common.CommandProgress(
            progress=response.progress.progress,
            state=response.progress.state,
            left_time_in_seconds=response.progress.left_time_seconds,
        )
    else:
        kwargs["empty"] = empty_pb2.Empty()

    return _common.CommandResponse(**kwargs)


def custom_command_response_to_proto(
    response: CustomCommandResponse,
    edge_pb2,
    timestamp_pb2,
    empty_pb2,
    common_pb2=None,
):
    from google.protobuf import struct_pb2

    _common = common_pb2 if common_pb2 is not None else edge_pb2

    ts = _now_ts(timestamp_pb2)
    meta_kwargs: dict = {
        "tid": response.tid,
        "sn": response.sn,
        "timestamp": ts,
    }
    if response.message:
        meta_kwargs["response_message"] = response.message

    kwargs: dict = {
        "has_errors": not response.success,
        "meta": _common.ResponseMeta(**meta_kwargs),
        # The wire field is command_id, not command_type — command_type is this SDK's own
        # (unchanged) Python-facing name for it, on both CustomCommandRequest/Response models.
        "command_id": response.command_type,
    }

    if response.error:
        err_ts = _now_ts(timestamp_pb2)
        kwargs["error"] = _common.GlobalErrorMessage(
            timestamp=err_ts,
            error_message=response.error.message,
            error_code=int(response.error.code),
        )
    elif response.result is not None:
        s = struct_pb2.Struct()
        s.update(response.result)
        kwargs["result"] = s
    else:
        kwargs["empty"] = empty_pb2.Empty()

    return _common.CustomCommandResponse(**kwargs)


def proto_to_custom_command(r) -> CustomCommandRequest:
    from google.protobuf import json_format

    params = {}
    if r.HasField("params"):  # type: ignore[attr-defined]
        params = json_format.MessageToDict(r.params)
    # r.command_id: see the command_id/command_type note in custom_command_response_to_proto.
    return CustomCommandRequest(command_type=r.command_id, params=params)

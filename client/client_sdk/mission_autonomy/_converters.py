"""Proto <-> dataclass converters for the MissionAutonomy sub-client.

Field names mirror :file:`common.proto` exactly. Generated proto modules are
imported lazily so the package remains importable before
``scripts/generate_protos.sh`` has been run.
"""

from __future__ import annotations

from typing import Any

from ..models._converters import (
    datetime_to_proto_ts,
    opt_field,
    proto_to_error_info,
    proto_to_progress_info,
    proto_ts_to_datetime,
)
from ..models.enums import (
    MissionStatus,
    MissionType,
    SchedulerType,
    TaskStatus,
    TaskType,
)
from ..models.mission_autonomy import (
    MissionDTO,
    MissionResponse,
    SchedulerDTO,
    SchedulerResponse,
    TaskDTO,
    TaskResponse,
)
from ..models.task_config import (
    AreaMappingTaskConfig,
    AreaVertex,
    DetectionParameter,
    DetectTaskConfig,
    FollowTaskConfig,
    PoiTaskConfig,
    TaskConfig,
    TrackTaskConfig,
    WaypointDTO,
    WaypointTaskConfig,
)


def _set_opt(kwargs: dict[str, Any], proto_field: str, value: Any) -> None:
    if value is not None:
        kwargs[proto_field] = value


# ---------------------------------------------------------------------------
# Waypoint <-> proto
# ---------------------------------------------------------------------------


def waypoint_to_proto(w: WaypointDTO, common_pb2):
    kwargs: dict[str, Any] = {"latitude": w.latitude, "longitude": w.longitude}
    _set_opt(kwargs, "altitude", w.altitude)
    _set_opt(kwargs, "speed", w.speed)
    if w.fly_through is not None:
        kwargs["flyTrough"] = w.fly_through  # proto field is misspelled
    _set_opt(kwargs, "wpOrder", w.wp_order)
    _set_opt(kwargs, "gimbalPitch", w.gimbal_pitch)
    return common_pb2.WaypointProtoDTO(**kwargs)


def proto_to_waypoint(w) -> WaypointDTO:
    return WaypointDTO(
        latitude=w.latitude,
        longitude=w.longitude,
        altitude=opt_field(w, "altitude"),
        speed=opt_field(w, "speed"),
        fly_through=opt_field(w, "flyTrough"),
        wp_order=opt_field(w, "wpOrder"),
        gimbal_pitch=opt_field(w, "gimbalPitch"),
    )


# ---------------------------------------------------------------------------
# WaypointTaskConfig
# ---------------------------------------------------------------------------


def _waypoint_config_to_proto(c: WaypointTaskConfig, common_pb2):
    kwargs: dict[str, Any] = {
        "flightId": c.flight_id,
        "waypoints": [waypoint_to_proto(w, common_pb2) for w in c.waypoints],
    }
    _set_opt(kwargs, "useStraightLine", c.use_straight_line)
    _set_opt(kwargs, "takeOffSecurityHeight", c.take_off_security_height)
    _set_opt(kwargs, "rthAltitude", c.rth_altitude)
    _set_opt(kwargs, "rthSpeed", c.rth_speed)
    _set_opt(kwargs, "globalSpeed", c.global_speed)
    _set_opt(kwargs, "globalTransitionSpeed", c.global_transition_speed)
    _set_opt(kwargs, "globalHeight", c.global_height)
    _set_opt(kwargs, "globalGimbalPitch", c.global_gimbal_pitch)
    _set_opt(kwargs, "payloadImagingType", c.payload_imaging_type)
    _set_opt(kwargs, "fileUrl", c.file_url)
    _set_opt(kwargs, "fileMd5", c.file_md5)
    _set_opt(kwargs, "flightAreaFileUrl", c.flight_area_file_url)
    _set_opt(kwargs, "flightAreaChecksum", c.flight_area_checksum)
    return common_pb2.WaypointTaskConfigProto(**kwargs)


def _proto_to_waypoint_config(proto) -> WaypointTaskConfig:
    return WaypointTaskConfig(
        flight_id=proto.flightId,
        waypoints=[proto_to_waypoint(w) for w in proto.waypoints],
        use_straight_line=opt_field(proto, "useStraightLine"),
        take_off_security_height=opt_field(proto, "takeOffSecurityHeight"),
        rth_altitude=opt_field(proto, "rthAltitude"),
        rth_speed=opt_field(proto, "rthSpeed"),
        global_speed=opt_field(proto, "globalSpeed"),
        global_transition_speed=opt_field(proto, "globalTransitionSpeed"),
        global_height=opt_field(proto, "globalHeight"),
        global_gimbal_pitch=opt_field(proto, "globalGimbalPitch"),
        payload_imaging_type=opt_field(proto, "payloadImagingType"),
        file_url=opt_field(proto, "fileUrl"),
        file_md5=opt_field(proto, "fileMd5"),
        flight_area_file_url=opt_field(proto, "flightAreaFileUrl"),
        flight_area_checksum=opt_field(proto, "flightAreaChecksum"),
    )


# ---------------------------------------------------------------------------
# DetectTaskConfig
# ---------------------------------------------------------------------------


def _detect_config_to_proto(c: DetectTaskConfig, common_pb2):
    kwargs: dict[str, Any] = {"detectionTargets": list(c.detection_targets)}
    _set_opt(kwargs, "detectionMode", c.detection_mode)
    _set_opt(kwargs, "areaLatitude", c.area_latitude)
    _set_opt(kwargs, "areaLongitude", c.area_longitude)
    _set_opt(kwargs, "areaRadius", c.area_radius)
    _set_opt(kwargs, "detectionAltitude", c.detection_altitude)
    _set_opt(kwargs, "scanPattern", c.scan_pattern)
    _set_opt(kwargs, "scanSpeed", c.scan_speed)
    _set_opt(kwargs, "thermalDetection", c.thermal_detection)
    _set_opt(kwargs, "visualDetection", c.visual_detection)
    _set_opt(kwargs, "minConfidence", c.min_confidence)
    _set_opt(kwargs, "maxDetections", c.max_detections)
    _set_opt(kwargs, "autoCaptureOnDetection", c.auto_capture_on_detection)
    _set_opt(kwargs, "investigateDetections", c.investigate_detections)
    _set_opt(kwargs, "investigationDistance", c.investigation_distance)
    _set_opt(kwargs, "investigationDuration", c.investigation_duration)
    _set_opt(kwargs, "gimbalPitch", c.gimbal_pitch)
    _set_opt(kwargs, "enableZoom", c.enable_zoom)
    _set_opt(kwargs, "zoomLevel", c.zoom_level)
    _set_opt(kwargs, "maxDuration", c.max_duration)
    _set_opt(kwargs, "onMaxDetectionsAction", c.on_max_detections_action)
    _set_opt(kwargs, "realtimeAlerts", c.realtime_alerts)
    _set_opt(kwargs, "aiModelId", c.ai_model_id)
    if c.detection_parameters:
        DetParam = common_pb2.DetectTaskConfigProto.DetectionParameterProto
        params = []
        for p in c.detection_parameters:
            pkw: dict[str, Any] = {"name": p.name, "value": p.value}
            _set_opt(pkw, "description", p.description)
            params.append(DetParam(**pkw))
        kwargs["detectionParameters"] = params
    return common_pb2.DetectTaskConfigProto(**kwargs)


def _proto_to_detect_config(proto) -> DetectTaskConfig:
    return DetectTaskConfig(
        detection_targets=list(proto.detectionTargets),
        detection_mode=opt_field(proto, "detectionMode"),
        area_latitude=opt_field(proto, "areaLatitude"),
        area_longitude=opt_field(proto, "areaLongitude"),
        area_radius=opt_field(proto, "areaRadius"),
        detection_altitude=opt_field(proto, "detectionAltitude"),
        scan_pattern=opt_field(proto, "scanPattern"),
        scan_speed=opt_field(proto, "scanSpeed"),
        thermal_detection=opt_field(proto, "thermalDetection"),
        visual_detection=opt_field(proto, "visualDetection"),
        min_confidence=opt_field(proto, "minConfidence"),
        max_detections=opt_field(proto, "maxDetections"),
        auto_capture_on_detection=opt_field(proto, "autoCaptureOnDetection"),
        investigate_detections=opt_field(proto, "investigateDetections"),
        investigation_distance=opt_field(proto, "investigationDistance"),
        investigation_duration=opt_field(proto, "investigationDuration"),
        gimbal_pitch=opt_field(proto, "gimbalPitch"),
        enable_zoom=opt_field(proto, "enableZoom"),
        zoom_level=opt_field(proto, "zoomLevel"),
        max_duration=opt_field(proto, "maxDuration"),
        on_max_detections_action=opt_field(proto, "onMaxDetectionsAction"),
        realtime_alerts=opt_field(proto, "realtimeAlerts"),
        ai_model_id=opt_field(proto, "aiModelId"),
        detection_parameters=[
            DetectionParameter(
                name=p.name,
                value=p.value,
                description=opt_field(p, "description"),
            )
            for p in proto.detectionParameters
        ],
    )


# ---------------------------------------------------------------------------
# AreaMappingTaskConfig
# ---------------------------------------------------------------------------


def _area_mapping_config_to_proto(c: AreaMappingTaskConfig, common_pb2):
    AreaVertexProto = common_pb2.AreaMappingTaskConfigProto.AreaVertexProto
    kwargs: dict[str, Any] = {
        "surveyAltitude": c.survey_altitude,
        "areaVertices": [
            AreaVertexProto(
                latitude=v.latitude,
                longitude=v.longitude,
                **({"order": v.order} if v.order is not None else {}),
            )
            for v in c.area_vertices
        ],
    }
    _set_opt(kwargs, "flightPattern", c.flight_pattern)
    _set_opt(kwargs, "frontOverlap", c.front_overlap)
    _set_opt(kwargs, "sideOverlap", c.side_overlap)
    _set_opt(kwargs, "speed", c.speed)
    _set_opt(kwargs, "gimbalPitch", c.gimbal_pitch)
    _set_opt(kwargs, "cameraAngle", c.camera_angle)
    _set_opt(kwargs, "terrainFollowing", c.terrain_following)
    _set_opt(kwargs, "groundSamplingDistance", c.ground_sampling_distance)
    _set_opt(kwargs, "enable3DReconstruction", c.enable_3d_reconstruction)
    return common_pb2.AreaMappingTaskConfigProto(**kwargs)


def _proto_to_area_mapping_config(proto) -> AreaMappingTaskConfig:
    return AreaMappingTaskConfig(
        survey_altitude=proto.surveyAltitude,
        area_vertices=[
            AreaVertex(
                latitude=v.latitude,
                longitude=v.longitude,
                order=opt_field(v, "order"),
            )
            for v in proto.areaVertices
        ],
        flight_pattern=opt_field(proto, "flightPattern"),
        front_overlap=opt_field(proto, "frontOverlap"),
        side_overlap=opt_field(proto, "sideOverlap"),
        speed=opt_field(proto, "speed"),
        gimbal_pitch=opt_field(proto, "gimbalPitch"),
        camera_angle=opt_field(proto, "cameraAngle"),
        terrain_following=opt_field(proto, "terrainFollowing"),
        ground_sampling_distance=opt_field(proto, "groundSamplingDistance"),
        enable_3d_reconstruction=opt_field(proto, "enable3DReconstruction"),
    )


# ---------------------------------------------------------------------------
# PoiTaskConfig
# ---------------------------------------------------------------------------


def _poi_config_to_proto(c: PoiTaskConfig, common_pb2):
    kwargs: dict[str, Any] = {
        "poiLatitude": c.poi_latitude,
        "poiLongitude": c.poi_longitude,
        "poiAltitude": c.poi_altitude,
    }
    _set_opt(kwargs, "orbitRadius", c.orbit_radius)
    _set_opt(kwargs, "orbitSpeed", c.orbit_speed)
    _set_opt(kwargs, "flightAltitude", c.flight_altitude)
    _set_opt(kwargs, "numberOfOrbits", c.number_of_orbits)
    _set_opt(kwargs, "orbitDirection", c.orbit_direction)
    _set_opt(kwargs, "startAngle", c.start_angle)
    _set_opt(kwargs, "endAngle", c.end_angle)
    _set_opt(kwargs, "captureEnabled", c.capture_enabled)
    _set_opt(kwargs, "captureInterval", c.capture_interval)
    _set_opt(kwargs, "lockCameraOnPoi", c.lock_camera_on_poi)
    return common_pb2.PoiTaskConfigProto(**kwargs)


def _proto_to_poi_config(proto) -> PoiTaskConfig:
    return PoiTaskConfig(
        poi_latitude=proto.poiLatitude,
        poi_longitude=proto.poiLongitude,
        poi_altitude=proto.poiAltitude,
        orbit_radius=opt_field(proto, "orbitRadius"),
        orbit_speed=opt_field(proto, "orbitSpeed"),
        flight_altitude=opt_field(proto, "flightAltitude"),
        number_of_orbits=opt_field(proto, "numberOfOrbits"),
        orbit_direction=opt_field(proto, "orbitDirection"),
        start_angle=opt_field(proto, "startAngle"),
        end_angle=opt_field(proto, "endAngle"),
        capture_enabled=opt_field(proto, "captureEnabled"),
        capture_interval=opt_field(proto, "captureInterval"),
        lock_camera_on_poi=opt_field(proto, "lockCameraOnPoi"),
    )


# ---------------------------------------------------------------------------
# FollowTaskConfig
# ---------------------------------------------------------------------------


def _follow_config_to_proto(c: FollowTaskConfig, common_pb2):
    kwargs: dict[str, Any] = {"targetType": c.target_type}
    _set_opt(kwargs, "initialLatitude", c.initial_latitude)
    _set_opt(kwargs, "initialLongitude", c.initial_longitude)
    _set_opt(kwargs, "followDistance", c.follow_distance)
    _set_opt(kwargs, "relativeAltitude", c.relative_altitude)
    _set_opt(kwargs, "maxSpeed", c.max_speed)
    _set_opt(kwargs, "followMode", c.follow_mode)
    _set_opt(kwargs, "angleOffset", c.angle_offset)
    _set_opt(kwargs, "obstacleAvoidance", c.obstacle_avoidance)
    _set_opt(kwargs, "maxDuration", c.max_duration)
    _set_opt(kwargs, "maxDistanceFromStart", c.max_distance_from_start)
    _set_opt(kwargs, "lostTargetAction", c.lost_target_action)
    _set_opt(kwargs, "lostTargetTimeout", c.lost_target_timeout)
    _set_opt(kwargs, "lockCameraOnTarget", c.lock_camera_on_target)
    _set_opt(kwargs, "gimbalPitchOffset", c.gimbal_pitch_offset)
    _set_opt(kwargs, "autoCapture", c.auto_capture)
    _set_opt(kwargs, "captureInterval", c.capture_interval)
    return common_pb2.FollowTaskConfigProto(**kwargs)


def _proto_to_follow_config(proto) -> FollowTaskConfig:
    return FollowTaskConfig(
        target_type=proto.targetType,
        initial_latitude=opt_field(proto, "initialLatitude"),
        initial_longitude=opt_field(proto, "initialLongitude"),
        follow_distance=opt_field(proto, "followDistance"),
        relative_altitude=opt_field(proto, "relativeAltitude"),
        max_speed=opt_field(proto, "maxSpeed"),
        follow_mode=opt_field(proto, "followMode"),
        angle_offset=opt_field(proto, "angleOffset"),
        obstacle_avoidance=opt_field(proto, "obstacleAvoidance"),
        max_duration=opt_field(proto, "maxDuration"),
        max_distance_from_start=opt_field(proto, "maxDistanceFromStart"),
        lost_target_action=opt_field(proto, "lostTargetAction"),
        lost_target_timeout=opt_field(proto, "lostTargetTimeout"),
        lock_camera_on_target=opt_field(proto, "lockCameraOnTarget"),
        gimbal_pitch_offset=opt_field(proto, "gimbalPitchOffset"),
        auto_capture=opt_field(proto, "autoCapture"),
        capture_interval=opt_field(proto, "captureInterval"),
    )


# ---------------------------------------------------------------------------
# TrackTaskConfig
# ---------------------------------------------------------------------------


def _track_config_to_proto(c: TrackTaskConfig, common_pb2):
    kwargs: dict[str, Any] = {"targetType": c.target_type}
    _set_opt(kwargs, "initialLatitude", c.initial_latitude)
    _set_opt(kwargs, "initialLongitude", c.initial_longitude)
    _set_opt(kwargs, "targetAltitude", c.target_altitude)
    _set_opt(kwargs, "trackingMode", c.tracking_mode)
    _set_opt(kwargs, "maxMovementRadius", c.max_movement_radius)
    _set_opt(kwargs, "trackingAltitude", c.tracking_altitude)
    _set_opt(kwargs, "gimbalTracking", c.gimbal_tracking)
    _set_opt(kwargs, "autoZoom", c.auto_zoom)
    _set_opt(kwargs, "zoomLevel", c.zoom_level)
    _set_opt(kwargs, "trackingSensitivity", c.tracking_sensitivity)
    _set_opt(kwargs, "maxDuration", c.max_duration)
    _set_opt(kwargs, "lostTargetAction", c.lost_target_action)
    _set_opt(kwargs, "lostTargetTimeout", c.lost_target_timeout)
    _set_opt(kwargs, "searchPattern", c.search_pattern)
    _set_opt(kwargs, "searchDuration", c.search_duration)
    _set_opt(kwargs, "continuousRecording", c.continuous_recording)
    _set_opt(kwargs, "photoCapture", c.photo_capture)
    _set_opt(kwargs, "captureInterval", c.capture_interval)
    _set_opt(kwargs, "confidenceThreshold", c.confidence_threshold)
    return common_pb2.TrackTaskConfigProto(**kwargs)


def _proto_to_track_config(proto) -> TrackTaskConfig:
    return TrackTaskConfig(
        target_type=proto.targetType,
        initial_latitude=opt_field(proto, "initialLatitude"),
        initial_longitude=opt_field(proto, "initialLongitude"),
        target_altitude=opt_field(proto, "targetAltitude"),
        tracking_mode=opt_field(proto, "trackingMode"),
        max_movement_radius=opt_field(proto, "maxMovementRadius"),
        tracking_altitude=opt_field(proto, "trackingAltitude"),
        gimbal_tracking=opt_field(proto, "gimbalTracking"),
        auto_zoom=opt_field(proto, "autoZoom"),
        zoom_level=opt_field(proto, "zoomLevel"),
        tracking_sensitivity=opt_field(proto, "trackingSensitivity"),
        max_duration=opt_field(proto, "maxDuration"),
        lost_target_action=opt_field(proto, "lostTargetAction"),
        lost_target_timeout=opt_field(proto, "lostTargetTimeout"),
        search_pattern=opt_field(proto, "searchPattern"),
        search_duration=opt_field(proto, "searchDuration"),
        continuous_recording=opt_field(proto, "continuousRecording"),
        photo_capture=opt_field(proto, "photoCapture"),
        capture_interval=opt_field(proto, "captureInterval"),
        confidence_threshold=opt_field(proto, "confidenceThreshold"),
    )


# ---------------------------------------------------------------------------
# Task DTO <-> proto
# ---------------------------------------------------------------------------


def task_to_proto(task: TaskDTO):
    from ..generated import common_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {"status": task.status.value}
    _set_opt(kwargs, "id", task.id)
    _set_opt(kwargs, "missionId", task.mission_id)
    _set_opt(kwargs, "name", task.name)
    _set_opt(kwargs, "description", task.description)
    if task.task_type is not None:
        kwargs["taskType"] = task.task_type.value
    _set_opt(kwargs, "assetId", task.asset_id)
    _set_opt(kwargs, "snNumber", task.sn_number)
    _set_opt(kwargs, "currentProgress", task.current_progress)
    _set_opt(kwargs, "currentStep", task.current_step)
    if task.created_at is not None:
        kwargs["createdAt"] = datetime_to_proto_ts(task.created_at)
    if task.modified_at is not None:
        kwargs["modifiedAt"] = datetime_to_proto_ts(task.modified_at)
    _set_opt(kwargs, "modifiedFrom", task.modified_from)
    if task.config is not None:
        _apply_task_config(kwargs, task.config, common_pb2)
    return common_pb2.TaskProtoDTO(**kwargs)


def proto_to_task(proto) -> TaskDTO:
    return TaskDTO(
        status=TaskStatus(proto.status),
        id=opt_field(proto, "id"),
        mission_id=opt_field(proto, "missionId"),
        name=opt_field(proto, "name"),
        description=opt_field(proto, "description"),
        task_type=TaskType(proto.taskType) if proto.HasField("taskType") else None,  # type: ignore[attr-defined]
        asset_id=opt_field(proto, "assetId"),
        sn_number=opt_field(proto, "snNumber"),
        current_progress=opt_field(proto, "currentProgress"),
        current_step=opt_field(proto, "currentStep"),
        created_at=proto_ts_to_datetime(opt_field(proto, "createdAt")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modifiedAt")),
        modified_from=opt_field(proto, "modifiedFrom"),
        config=_proto_to_task_config(proto),
    )


def _apply_task_config(kwargs: dict[str, Any], config: TaskConfig, common_pb2) -> None:
    if isinstance(config, WaypointTaskConfig):
        kwargs["waypointConfig"] = _waypoint_config_to_proto(config, common_pb2)
    elif isinstance(config, DetectTaskConfig):
        kwargs["detectConfig"] = _detect_config_to_proto(config, common_pb2)
    elif isinstance(config, AreaMappingTaskConfig):
        kwargs["areaMappingConfig"] = _area_mapping_config_to_proto(config, common_pb2)
    elif isinstance(config, PoiTaskConfig):
        kwargs["poiConfig"] = _poi_config_to_proto(config, common_pb2)
    elif isinstance(config, FollowTaskConfig):
        kwargs["followConfig"] = _follow_config_to_proto(config, common_pb2)
    elif isinstance(config, TrackTaskConfig):
        kwargs["trackConfig"] = _track_config_to_proto(config, common_pb2)
    else:
        raise TypeError(f"Unknown TaskConfig variant: {type(config).__name__}")


def _proto_to_task_config(proto) -> TaskConfig | None:
    which = proto.WhichOneof("taskConfig")
    if which == "waypointConfig":
        return _proto_to_waypoint_config(proto.waypointConfig)
    if which == "detectConfig":
        return _proto_to_detect_config(proto.detectConfig)
    if which == "areaMappingConfig":
        return _proto_to_area_mapping_config(proto.areaMappingConfig)
    if which == "poiConfig":
        return _proto_to_poi_config(proto.poiConfig)
    if which == "followConfig":
        return _proto_to_follow_config(proto.followConfig)
    if which == "trackConfig":
        return _proto_to_track_config(proto.trackConfig)
    return None


# ---------------------------------------------------------------------------
# Mission DTO <-> proto
# ---------------------------------------------------------------------------


def mission_to_proto(mission: MissionDTO):
    from ..generated import common_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {
        "name": mission.name,
        "description": mission.description,
        "status": mission.status.value,
        "type": mission.type.value,
    }
    _set_opt(kwargs, "id", mission.id)
    _set_opt(kwargs, "geoJson", mission.geo_json)
    if mission.start_date is not None:
        kwargs["startDate"] = datetime_to_proto_ts(mission.start_date)
    if mission.end_date is not None:
        kwargs["endDate"] = datetime_to_proto_ts(mission.end_date)
    if mission.assigned_assets:
        kwargs["assignedAssets"] = list(mission.assigned_assets)
    if mission.created_at is not None:
        kwargs["createdAt"] = datetime_to_proto_ts(mission.created_at)
    if mission.modified_at is not None:
        kwargs["modifiedAt"] = datetime_to_proto_ts(mission.modified_at)
    _set_opt(kwargs, "updatedUser", mission.updated_user)
    if mission.tasks:
        kwargs["tasks"] = [task_to_proto(t) for t in mission.tasks]
    return common_pb2.MissionProtoDTO(**kwargs)


def proto_to_mission(proto) -> MissionDTO:
    return MissionDTO(
        id=opt_field(proto, "id"),
        name=proto.name,
        description=proto.description,
        status=MissionStatus(proto.status),
        type=MissionType(proto.type),
        tasks=[proto_to_task(t) for t in proto.tasks],
        geo_json=opt_field(proto, "geoJson"),
        start_date=proto_ts_to_datetime(opt_field(proto, "startDate")),
        end_date=proto_ts_to_datetime(opt_field(proto, "endDate")),
        assigned_assets=list(proto.assignedAssets),
        created_at=proto_ts_to_datetime(opt_field(proto, "createdAt")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modifiedAt")),
        updated_user=opt_field(proto, "updatedUser"),
    )


# ---------------------------------------------------------------------------
# Scheduler DTO <-> proto
# ---------------------------------------------------------------------------


def scheduler_to_proto(s: SchedulerDTO):
    from ..generated import common_pb2  # type: ignore[import]

    kwargs: dict[str, Any] = {
        "name": s.name,
        "cronExpression": s.cron_expression,
        "type": s.type.value,
    }
    _set_opt(kwargs, "id", s.id)
    _set_opt(kwargs, "missionId", s.mission_id)
    _set_opt(kwargs, "taskId", s.task_id)
    _set_opt(kwargs, "active", s.active)
    _set_opt(kwargs, "clientTimeZone", s.client_time_zone)
    if s.created_at is not None:
        kwargs["createdAt"] = datetime_to_proto_ts(s.created_at)
    if s.modified_at is not None:
        kwargs["modifiedAt"] = datetime_to_proto_ts(s.modified_at)
    return common_pb2.SchedulerProtoDTO(**kwargs)


def proto_to_scheduler(proto) -> SchedulerDTO:
    return SchedulerDTO(
        name=proto.name,
        cron_expression=proto.cronExpression,
        type=SchedulerType(proto.type),
        id=opt_field(proto, "id"),
        mission_id=opt_field(proto, "missionId"),
        task_id=opt_field(proto, "taskId"),
        active=opt_field(proto, "active"),
        client_time_zone=opt_field(proto, "clientTimeZone"),
        created_at=proto_ts_to_datetime(opt_field(proto, "createdAt")),
        modified_at=proto_ts_to_datetime(opt_field(proto, "modifiedAt")),
    )


# ---------------------------------------------------------------------------
# Response converters
# ---------------------------------------------------------------------------


def proto_to_mission_response(proto) -> MissionResponse:
    which = proto.WhichOneof("response")
    return MissionResponse(
        success=not bool(opt_field(proto, "hasErrors")),
        tid=proto.tid,
        mission_id=proto.missionId,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        mission=proto_to_mission(proto.missionDTO) if which == "missionDTO" else None,
    )


def proto_to_task_response(proto) -> TaskResponse:
    which = proto.WhichOneof("response")
    return TaskResponse(
        success=not bool(opt_field(proto, "hasErrors")),
        tid=proto.tid,
        task_id=proto.taskId,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        task=proto_to_task(proto.taskDTO) if which == "taskDTO" else None,
    )


def proto_to_scheduler_response(proto) -> SchedulerResponse:
    which = proto.WhichOneof("response")
    return SchedulerResponse(
        success=not bool(opt_field(proto, "hasErrors")),
        tid=proto.tid,
        scheduler_id=proto.schedulerId,
        timestamp=proto_ts_to_datetime(proto.timestamp),
        error=proto_to_error_info(proto.error) if which == "error" else None,
        progress=proto_to_progress_info(proto.progress) if which == "progress" else None,
        scheduler=proto_to_scheduler(proto.schedulerDTO) if which == "schedulerDTO" else None,
        schedulers=[proto_to_scheduler(s) for s in proto.schedulerDTOList.schedulerDTOList]
        if which == "schedulerDTOList"
        else None,
    )

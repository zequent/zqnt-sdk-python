"""
Plain-Python task and mission models mirroring common.proto task DTOs.
"""

from dataclasses import dataclass, field
from datetime import datetime

from .common import MissionStatus, MissionType, TaskStatus, TaskType

# ---------------------------------------------------------------------------
# Waypoint task
# ---------------------------------------------------------------------------


@dataclass
class Waypoint:
    latitude: float
    longitude: float
    altitude: float | None = None
    speed: float | None = None
    fly_through: bool | None = None
    wp_order: int | None = None
    gimbal_pitch: int | None = None


@dataclass
class WaypointTaskConfig:
    flight_id: str
    waypoints: list[Waypoint] = field(default_factory=list)
    fly_to_wayline_mode: str | None = None
    wayline_finish_action: str | None = None
    wayline_type: str | None = None
    wayline_turn_mode: str | None = None
    use_straight_line: bool | None = None
    wayline_precision_type: str | None = None
    exit_wayline_when_rc_lost: str | None = None
    rc_lost_action: str | None = None
    out_of_control_action: str | None = None
    take_off_security_height: float | None = None
    rth_altitude: int | None = None
    rth_mode: str | None = None
    rth_speed: float | None = None
    global_speed: float | None = None
    global_transition_speed: float | None = None
    global_height: float | None = None
    gimbal_pitch_mode: str | None = None
    global_gimbal_pitch: int | None = None
    payload_imaging_type: str | None = None
    file_url: str | None = None
    file_md5: str | None = None
    flight_area_file_url: str | None = None
    flight_area_checksum: str | None = None


# ---------------------------------------------------------------------------
# Detect task
# ---------------------------------------------------------------------------


@dataclass
class DetectionParameter:
    name: str
    value: str
    description: str | None = None


@dataclass
class DetectTaskConfig:
    detection_targets: list[str] = field(default_factory=list)
    detection_mode: str | None = None
    area_latitude: float | None = None
    area_longitude: float | None = None
    area_radius: float | None = None
    detection_altitude: float | None = None
    scan_pattern: str | None = None
    scan_speed: float | None = None
    thermal_detection: bool | None = None
    visual_detection: bool | None = None
    min_confidence: float | None = None
    max_detections: int | None = None
    auto_capture_on_detection: bool | None = None
    investigate_detections: bool | None = None
    investigation_distance: float | None = None
    investigation_duration: int | None = None
    gimbal_pitch: int | None = None
    enable_zoom: bool | None = None
    zoom_level: float | None = None
    max_duration: int | None = None
    on_max_detections_action: str | None = None
    realtime_alerts: bool | None = None
    ai_model_id: str | None = None
    detection_parameters: list[DetectionParameter] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Area mapping task
# ---------------------------------------------------------------------------


@dataclass
class AreaVertex:
    latitude: float
    longitude: float
    order: int | None = None


@dataclass
class AreaMappingTaskConfig:
    survey_altitude: float
    area_vertices: list[AreaVertex] = field(default_factory=list)
    flight_pattern: str | None = None
    front_overlap: int | None = None
    side_overlap: int | None = None
    speed: float | None = None
    gimbal_pitch: int | None = None
    camera_angle: int | None = None
    terrain_following: bool | None = None
    ground_sampling_distance: float | None = None
    enable_3d_reconstruction: bool | None = None


# ---------------------------------------------------------------------------
# POI task
# ---------------------------------------------------------------------------


@dataclass
class PoiTaskConfig:
    poi_latitude: float
    poi_longitude: float
    poi_altitude: float
    orbit_radius: float | None = None
    orbit_speed: float | None = None
    flight_altitude: float | None = None
    number_of_orbits: int | None = None
    orbit_direction: str | None = None
    start_angle: int | None = None
    end_angle: int | None = None
    capture_enabled: bool | None = None
    capture_interval: int | None = None
    lock_camera_on_poi: bool | None = None


# ---------------------------------------------------------------------------
# Follow task
# ---------------------------------------------------------------------------


@dataclass
class FollowTaskConfig:
    target_type: str
    initial_latitude: float | None = None
    initial_longitude: float | None = None
    follow_distance: float | None = None
    relative_altitude: float | None = None
    max_speed: float | None = None
    follow_mode: str | None = None
    angle_offset: int | None = None
    obstacle_avoidance: bool | None = None
    max_duration: int | None = None
    max_distance_from_start: float | None = None
    lost_target_action: str | None = None
    lost_target_timeout: int | None = None
    lock_camera_on_target: bool | None = None
    gimbal_pitch_offset: int | None = None
    auto_capture: bool | None = None
    capture_interval: int | None = None


# ---------------------------------------------------------------------------
# Track task
# ---------------------------------------------------------------------------


@dataclass
class TrackTaskConfig:
    target_type: str
    initial_latitude: float | None = None
    initial_longitude: float | None = None
    target_altitude: float | None = None
    tracking_mode: str | None = None
    max_movement_radius: float | None = None
    tracking_altitude: float | None = None
    gimbal_tracking: bool | None = None
    auto_zoom: bool | None = None
    zoom_level: float | None = None
    tracking_sensitivity: str | None = None
    max_duration: int | None = None
    lost_target_action: str | None = None
    lost_target_timeout: int | None = None
    search_pattern: str | None = None
    search_duration: int | None = None
    continuous_recording: bool | None = None
    photo_capture: bool | None = None
    capture_interval: int | None = None
    confidence_threshold: float | None = None


# ---------------------------------------------------------------------------
# Task / Mission
# ---------------------------------------------------------------------------


@dataclass
class Task:
    status: TaskStatus
    id: str | None = None
    mission_id: str | None = None
    name: str | None = None
    description: str | None = None
    task_type: TaskType | None = None
    asset_id: str | None = None
    sn_number: str | None = None
    current_progress: int | None = None
    current_step: str | None = None
    waypoint_config: WaypointTaskConfig | None = None
    detect_config: DetectTaskConfig | None = None
    area_mapping_config: AreaMappingTaskConfig | None = None
    poi_config: PoiTaskConfig | None = None
    follow_config: FollowTaskConfig | None = None
    track_config: TrackTaskConfig | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None


@dataclass
class Mission:
    name: str
    description: str
    status: MissionStatus
    type: MissionType
    id: str | None = None
    tasks: list[Task] = field(default_factory=list)
    geo_json: str | None = None
    assigned_assets: list[str] = field(default_factory=list)
    start_date: datetime | None = None
    end_date: datetime | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None

import math

from edge_sdk.client.telemetry_ingest import detection_to_v3
from edge_sdk.models.common import DetectionPosition, DetectionResult


def test_radar_geometry_reaches_the_v3_detection():
    detection = detection_to_v3(
        DetectionResult(
            object_id="track-7",
            object_type="UAV",
            confidence=0.8,
            position=DetectionPosition(
                latitude=52.5,
                longitude=13.4,
                altitude=120.0,
                range_m=900.0,
                bearing_deg=45.0,
                elevation_deg=3.0,
                speed_mps=12.0,
                heading_deg=270.0,
            ),
        )
    )

    assert detection.position.latitude == 52.5
    assert detection.range_meters == 900.0
    assert detection.bearing_degrees == 45.0
    assert detection.elevation_degrees == 3.0
    assert detection.speed == 12.0
    assert detection.heading_degrees == 270.0


def test_geometry_without_coordinates_is_kept_and_unset_fields_stay_unset():
    detection = detection_to_v3(
        DetectionResult(
            object_id="track-8",
            object_type="UAV",
            confidence=0.5,
            position=DetectionPosition(latitude=math.nan, longitude=math.nan, range_m=900.0, speed_mps=math.nan),
        )
    )

    assert not detection.HasField("position")
    assert detection.range_meters == 900.0
    assert not detection.HasField("bearing_degrees")
    assert not detection.HasField("speed")

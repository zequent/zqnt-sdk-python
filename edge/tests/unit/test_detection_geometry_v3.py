import math

from edge_sdk.client.telemetry_ingest import detection_to_v3
from edge_sdk.models.common import DetectionAttribute, DetectionPosition, DetectionResult


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


def test_attributes_and_model_reach_the_v3_detection():
    detection = detection_to_v3(
        DetectionResult(
            object_id="obj-1",
            object_type="licence_plate",
            confidence=0.9,
            model="plates@1.0.0",
            attributes=[
                DetectionAttribute(key="plate", value="M AB 123", confidence=0.93, model="plate-ocr@2.1.0"),
                DetectionAttribute(key="plate_country", value="DE", confidence=0.81),
            ],
        )
    )

    assert detection.model == "plates@1.0.0"
    assert [(a.key, a.value, a.model) for a in detection.attributes] == [
        ("plate", "M AB 123", "plate-ocr@2.1.0"),
        ("plate_country", "DE", ""),
    ]
    assert abs(detection.attributes[0].confidence - 0.93) < 1e-6


def test_a_detection_without_attributes_has_none():
    detection = detection_to_v3(DetectionResult(object_id="obj-2", object_type="car", confidence=0.5))

    assert len(detection.attributes) == 0
    assert detection.model == ""

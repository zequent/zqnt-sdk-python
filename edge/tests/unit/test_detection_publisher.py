"""The wire form of a detection: image box for cameras, position for sensors that locate targets."""

from edge_sdk.client.detection_publisher import DetectionPublisher
from edge_sdk.models import BoundingBox, DetectionBatch, DetectionPosition, DetectionResult


def _publisher() -> DetectionPublisher:
    return DetectionPublisher(host="live-data.test", port=8003, sn="SIM-RADAR-01")


def test_a_radar_detection_carries_its_position() -> None:
    batch = DetectionBatch(
        sn="SIM-RADAR-01",
        detections=[
            DetectionResult(
                object_id="track-7",
                object_type="UAV",
                confidence=0.9,
                position=DetectionPosition(
                    latitude=52.52, longitude=13.405, altitude=120.0, range_m=850.0, bearing_deg=42.5
                ),
            )
        ],
    )

    request = _publisher()._build_detection_request(batch)

    detection = request.detections[0]
    assert detection.object_type == "UAV"
    assert not detection.HasField("bounding_box")
    assert detection.position.latitude == 52.52
    assert detection.position.longitude == 13.405
    assert detection.position.altitude == 120.0
    assert detection.position.range_m == 850.0
    assert detection.position.bearing_deg == 42.5
    # Unset optionals stay absent rather than arriving as 0.
    assert not detection.position.HasField("speed_mps")


def test_a_camera_detection_keeps_its_box_and_has_no_position() -> None:
    batch = DetectionBatch(
        detections=[DetectionResult("obj-1", "person", 0.8, BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4))]
    )

    detection = _publisher()._build_detection_request(batch).detections[0]

    assert abs(detection.bounding_box.width - 0.3) < 1e-6
    assert not detection.HasField("position")

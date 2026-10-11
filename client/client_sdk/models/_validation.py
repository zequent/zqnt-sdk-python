"""Validation helpers shared across the SDK."""

from __future__ import annotations

import math


def validate_sn(sn: str) -> None:
    if not sn or not sn.strip():
        raise ValueError("SN must not be null or blank")


def validate_coordinates(latitude: float, longitude: float, altitude: float) -> None:
    for name, value in (("latitude", latitude), ("longitude", longitude), ("altitude", altitude)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number, got: {value}")
    if latitude < -90.0 or latitude > 90.0:
        raise ValueError(f"Latitude must be between -90 and 90, got: {latitude}")
    if longitude < -180.0 or longitude > 180.0:
        raise ValueError(f"Longitude must be between -180 and 180, got: {longitude}")


def validate_non_blank(name: str, value: str | None) -> None:
    if value is None or not value.strip():
        raise ValueError(f"{name} must not be null or blank")


def validate_positive(name: str, value: int | float) -> None:
    if value is None or value <= 0:
        raise ValueError(f"{name} must be positive, got: {value}")


def validate_non_negative(name: str, value: int | float) -> None:
    if value is None or value < 0:
        raise ValueError(f"{name} must be non-negative, got: {value}")

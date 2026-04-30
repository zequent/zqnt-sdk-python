"""Manual control input frame sent over the client-streaming RPC."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ManualControlInput:
    """One frame of manual control input.

    Mirrors :proto:`ManualControlInput`. All fields are optional — unset
    fields are not transmitted on the wire.
    """

    roll: float | None = None
    pitch: float | None = None
    yaw: float | None = None
    throttle: float | None = None
    gimbal_pitch: float | None = None

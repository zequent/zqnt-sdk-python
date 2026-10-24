"""Delays between attempts to reopen a publisher's long-lived stream."""

from __future__ import annotations

import time
from typing import Callable


class ReconnectBackoff:
    """Exponential delays between reconnects that start over once a stream has stayed up.

    The platform ends healthy streams on purpose: every core service closes gRPC connections after a
    few minutes so clients reach replicas started since. Such a break is not a failing platform, and
    counted as one it doubled the delay on every renewal (1 s, 2 s, 4 s ... 60 s), leaving the queue
    to fill and drop while the publisher waited.
    """

    def __init__(
        self,
        initial: float,
        maximum: float,
        healthy_after: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._initial = initial
        self._maximum = maximum
        self._healthy_after = healthy_after
        self._clock = clock
        self._delay = initial
        self._opened_at: float | None = None

    def opened(self) -> None:
        """A stream was opened just now."""
        self._opened_at = self._clock()

    def reset(self) -> None:
        """The stream ended cleanly; the next attempt waits the initial delay."""
        self._delay = self._initial
        self._opened_at = None

    def next_delay(self) -> float:
        """The delay before the next attempt; the one after it doubles, up to the maximum."""
        if self._opened_at is not None and self._clock() - self._opened_at >= self._healthy_after:
            self._delay = self._initial
        self._opened_at = None
        delay = self._delay
        self._delay = min(self._delay * 2, self._maximum)
        return delay

from edge_sdk.client._reconnect import ReconnectBackoff


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_failing_platform_doubles_the_delay_up_to_the_maximum():
    backoff = ReconnectBackoff(1.0, 8.0, clock=Clock())

    assert [backoff.next_delay() for _ in range(6)] == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_a_stream_that_stayed_up_starts_over_with_the_initial_delay():
    clock = Clock()
    backoff = ReconnectBackoff(1.0, 60.0, healthy_after=30.0, clock=clock)
    for _ in range(4):
        backoff.next_delay()

    backoff.opened()
    clock.now += 300.0

    assert backoff.next_delay() == 1.0
    assert backoff.next_delay() == 2.0


def test_a_stream_that_broke_at_once_keeps_backing_off():
    clock = Clock()
    backoff = ReconnectBackoff(1.0, 60.0, healthy_after=30.0, clock=clock)
    backoff.next_delay()
    backoff.next_delay()

    backoff.opened()
    clock.now += 2.0

    assert backoff.next_delay() == 4.0


def test_a_clean_end_starts_over():
    backoff = ReconnectBackoff(1.0, 60.0, clock=Clock())
    for _ in range(3):
        backoff.next_delay()

    backoff.reset()

    assert backoff.next_delay() == 1.0

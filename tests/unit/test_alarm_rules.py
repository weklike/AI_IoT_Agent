from datetime import timedelta


def test_only_continuous_unique_samples_advance_duration(fixed_now):
    from backend.app.alarms.rules import observe_duration

    state = None
    for offset in (0, 2, 4, 6, 8):
        state, reached = observe_duration(state, fixed_now + timedelta(seconds=offset), True, 10)
        assert not reached
    state, reached = observe_duration(state, fixed_now + timedelta(seconds=10), True, 10)
    assert reached
    _, repeated = observe_duration(state, fixed_now + timedelta(seconds=10), True, 10)
    assert not repeated
    state, reached = observe_duration(state, fixed_now + timedelta(seconds=14), True, 10)
    assert not reached
    state, reached = observe_duration(state, fixed_now + timedelta(seconds=12), True, 10)
    assert not reached and state["start_ts"] is None

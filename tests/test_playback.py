from auracd.playback import should_auto_advance


def test_auto_advance_uses_toc_when_driver_zeros_position_and_duration():
    assert should_auto_advance(
        now=101.5,
        started_at=100.0,
        started_offset=0.0,
        position=0.0,
        last_position=1.1,
        duration=0.0,
        last_duration=0.0,
        known_duration=1.2,
        stopped_samples=2,
    )


def test_auto_advance_ignores_transient_stop():
    assert not should_auto_advance(
        now=101.5,
        started_at=100.0,
        started_offset=0.0,
        position=0.0,
        last_position=1.1,
        duration=0.0,
        last_duration=0.0,
        known_duration=1.2,
        stopped_samples=1,
    )


def test_auto_advance_does_not_skip_mid_track():
    assert not should_auto_advance(
        now=130.0,
        started_at=100.0,
        started_offset=0.0,
        position=30.0,
        last_position=30.0,
        duration=240.0,
        last_duration=240.0,
        known_duration=240.0,
        stopped_samples=2,
    )

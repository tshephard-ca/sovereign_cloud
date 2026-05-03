from stateful_storage_fit.parse_iostat import parse_iostat_text


def test_parses_iostat_await_and_util():
    samples, warnings, meta = parse_iostat_text(
        """Device r/s w/s rkB/s wkB/s await aqu-sz %util
sda 1 2 3 4 1.0 0.1 10.0

Device r/s w/s rkB/s wkB/s await aqu-sz %util
sda 1 2 3 4 24.8 2.0 72.0
"""
    )
    assert not warnings
    assert samples["sda"].await_ms == 24.8
    assert samples["sda"].util_pct == 72.0
    assert meta["max_observed_await_ms"] == 24.8


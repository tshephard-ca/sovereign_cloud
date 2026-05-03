from __future__ import annotations

import pytest

from s3_compat_replay.models import Probe, ProbeStep
from s3_compat_replay.safety import ensure_key_within_prefix, probe_needs_write, validate_scratch_prefix


def test_rejects_unsafe_scratch_prefix():
    assert validate_scratch_prefix("")
    assert validate_scratch_prefix("/")
    assert validate_scratch_prefix("*")
    assert validate_scratch_prefix("short/")
    assert validate_scratch_prefix("compat-replay")


def test_allows_safe_scratch_prefix_and_enforces_keys():
    assert validate_scratch_prefix("compat-replay/") == []
    ensure_key_within_prefix("compat-replay/run/object.txt", "compat-replay/")
    with pytest.raises(ValueError):
        ensure_key_within_prefix("outside/object.txt", "compat-replay/")


def test_probe_needs_write_detects_put_delete_setup():
    probe = Probe(id="p", family="object_write", setup=[ProbeStep(operation="PutObject")], steps=[ProbeStep(operation="DeleteObject")])
    assert probe_needs_write(probe)

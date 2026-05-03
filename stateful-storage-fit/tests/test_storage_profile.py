import pytest

from stateful_storage_fit.storage_profile import StorageProfileError, parse_storage_profile_text

from tests.helpers import PROFILE


def test_storage_profile_validation_accepts_generic_profile():
    profile = parse_storage_profile_text(PROFILE)
    assert profile.storage_classes[0].name == "standard-rwo"
    assert profile.performance_tiers["fast"] == 2


def test_storage_profile_validation_rejects_unknown_tier():
    with pytest.raises(StorageProfileError):
        parse_storage_profile_text(
            """
storage_classes:
  - name: bad
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: missing
performance_tiers:
  standard: 1
"""
        )


from __future__ import annotations

import pytest
from pydantic import ValidationError

from brownout_policy_compiler.models import BrownoutMode, Priority
from brownout_policy_compiler.service_priority import load_service_priority, try_load_service_priority, validate_service_priority
from brownout_policy_compiler.data_generator import service_priority_fixture

from .conftest import write_yaml


def test_service_priority_yaml_parses(examples):
    services = load_service_priority(examples / "service_priority.yml")
    assert len(services.service_groups) == 6


def test_missing_service_groups_fails_validation(tmp_path, mutable_services):
    mutable_services.pop("service_groups")
    path = write_yaml(tmp_path / "services.yml", mutable_services)
    services, result = try_load_service_priority(path)
    assert services is None
    assert "SERVICE_PRIORITY_INVALID" in result.blockers


def test_p0_service_with_shed_fails_when_configured(tmp_path, mutable_services):
    mutable_services["service_groups"][0]["brownout_mode"] = "SHED"
    path = write_yaml(tmp_path / "services.yml", mutable_services)
    services = load_service_priority(path)
    assert services.service_groups[0].priority == Priority.P0
    assert services.service_groups[0].brownout_mode == BrownoutMode.SHED
    result = validate_service_priority(services, fail_on_p0_shed=True)
    assert "P0_SERVICE_MARKED_SHED" in result.blockers


def test_invalid_endpoint_port_fails(tmp_path, mutable_services):
    mutable_services["service_groups"][0]["endpoints"][0]["ports"] = ["70000-80000"]
    path = write_yaml(tmp_path / "services.yml", mutable_services)
    with pytest.raises(ValidationError):
        load_service_priority(path)


def test_generated_service_priority_has_modeled_business_metadata(tmp_path):
    path = write_yaml(tmp_path / "services.yml", service_priority_fixture())
    services = load_service_priority(path)
    result = validate_service_priority(services, strict=True)
    metadata_codes = {
        "ORGANIZATION_PROFILE_INCOMPLETE",
        "SERVICE_OWNERSHIP_METADATA_MISSING",
        "SERVICE_CRITICALITY_METADATA_MISSING",
        "APPROVAL_METADATA_MISSING",
        "ROLLBACK_CONTROL_MISSING",
        "ENDPOINT_OPERATIONAL_METADATA_MISSING",
        "SHARED_ENDPOINT_GROUP_MISSING",
        "TRUSTED_SOURCE_REVIEW_METADATA_MISSING",
    }
    assert not (set(result.warnings) & metadata_codes)
    assert not (set(result.blockers) & metadata_codes)

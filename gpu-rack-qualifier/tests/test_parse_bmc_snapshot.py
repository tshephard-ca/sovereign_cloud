from pathlib import Path

from gpu_rack_qualifier.features import derive_features
from gpu_rack_qualifier.models import NodeEvidence, QualificationPolicy
from gpu_rack_qualifier.parse_bmc_snapshot import parse_bmc_snapshot


def test_parses_redfish_like_sensor_snapshot(tmp_path):
    path = tmp_path / "bmc.json"
    path.write_text('{"Sensors":[{"Name":"Inlet Temp","SensorType":"Temperature","Reading":25,"Status":{"Health":"OK"}}]}', encoding="utf-8")
    result = parse_bmc_snapshot(path)
    assert result.parsed
    assert result.sensors[0].sensor_name == "Inlet Temp"


def test_detects_bmc_health_warning_and_critical_and_fan_failure(tmp_path):
    path = tmp_path / "bmc.json"
    path.write_text(
        '{"Sensors":['
        '{"Name":"Temp","SensorType":"Temperature","Reading":85,"Status":{"Health":"Warning"}},'
        '{"Name":"Voltage","SensorType":"Voltage","Reading":0,"Status":{"Health":"Critical"}},'
        '{"Name":"Fan 1","SensorType":"Fan","Reading":0,"Status":{"Health":"Critical"}}'
        "]}",
        encoding="utf-8",
    )
    result = parse_bmc_snapshot(path)
    assert result.warning_count == 1
    assert result.critical_count == 2
    assert result.fan_failure_count >= 1


def test_detects_temperature_warning_and_critical(tmp_path):
    warn = tmp_path / "warn.json"
    warn.write_text('{"Sensors":[{"Name":"Temp","SensorType":"Temperature","Reading":85,"Status":{"Health":"OK"}}]}', encoding="utf-8")
    critical = tmp_path / "critical.json"
    critical.write_text('{"Sensors":[{"Name":"Temp","SensorType":"Temperature","Reading":95,"Status":{"Health":"OK"}}]}', encoding="utf-8")
    warn_features = derive_features(NodeEvidence(node_name="warn", path=tmp_path, bmc_snapshot=parse_bmc_snapshot(warn)), QualificationPolicy())
    critical_features = derive_features(NodeEvidence(node_name="critical", path=tmp_path, bmc_snapshot=parse_bmc_snapshot(critical)), QualificationPolicy())
    assert "BMC_TEMP_WARNING" in warn_features.warnings
    assert "BMC_TEMP_CRITICAL" in critical_features.blockers

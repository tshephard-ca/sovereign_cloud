from __future__ import annotations

from cabinet_burst_envelope.redact import Redactor
from cabinet_burst_envelope.report import redact_envelope
from cabinet_burst_envelope.cli import _prepare_estimate

from .conftest import NOW, generated_power_rows, generated_temperature_rows, write_power_rows, write_profile, write_temperature_rows


def test_redaction_hides_cabinet_pdu_sensor_and_circuit_ids():
    redactor = Redactor()
    payload = {
        "cabinet_id": "cab-a01",
        "pdu_id": "pdu-a",
        "sensor_id": "sensor-top",
        "circuit_id": "circuit-1",
        "source": "normalized-power",
        "reading_kw": 12.5,
        "reason_code": "POWER_DATA_PRESENT",
    }
    redacted = redactor.redact_mapping(payload)
    assert redacted["cabinet_id"] == "cabinet_001"
    assert redacted["pdu_id"] == "pdu_001"
    assert redacted["sensor_id"] == "sensor_001"
    assert redacted["circuit_id"] == "circuit_001"
    assert redacted["reading_kw"] == 12.5
    assert redacted["reason_code"] == "POWER_DATA_PRESENT"


def test_redaction_preserves_kw_temperature_status_and_reason_codes(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    _loaded, _alignment, envelope, _summary = _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)
    redacted = redact_envelope(envelope, Redactor())
    assert redacted.cabinet_id == "cabinet_001"
    assert redacted.recommended_sustained_kw == envelope.recommended_sustained_kw
    assert redacted.observed_temperature == envelope.observed_temperature
    assert redacted.envelope_status == envelope.envelope_status
    assert redacted.reason_codes == envelope.reason_codes

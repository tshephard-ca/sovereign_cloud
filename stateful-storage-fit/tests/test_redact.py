from stateful_storage_fit.parse_processes import parse_processes_text
from stateful_storage_fit.redact import Redactor


def test_redaction_removes_process_args():
    processes, _ = parse_processes_text("101 postgres /usr/bin/postgres --password secret\n")
    redacted = Redactor().redact_processes(processes)
    assert redacted[0].command == "postgres"
    assert redacted[0].args is None
    assert "secret" not in redacted[0].raw


def test_redaction_covers_analysis_mount_paths():
    redactor = Redactor()
    analysis = {
        "evidence_graph": {
            "observations": [
                {"kind": "mount.candidate_data", "subject": "/srv/private", "value": {"target": "/srv/private"}}
            ]
        }
    }
    redacted = redactor.redact_analysis(analysis)
    obs = redacted["evidence_graph"]["observations"][0]
    assert obs["subject"] == "/redacted/path_001/private"
    assert obs["value"]["target"] == "/redacted/path_001/private"

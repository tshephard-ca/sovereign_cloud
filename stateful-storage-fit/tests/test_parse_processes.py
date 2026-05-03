from stateful_storage_fit.parse_processes import parse_processes_text


def test_parses_processes_with_args_and_command_only():
    entries, warnings = parse_processes_text(
        """101 postgres /usr/bin/postgres -D /data
worker
"""
    )
    assert len(entries) == 2
    assert entries[0].pid == 101
    assert entries[0].command == "postgres"
    assert entries[1].command == "worker"
    assert "PS_PROCESS_ARGS_MISSING" in warnings


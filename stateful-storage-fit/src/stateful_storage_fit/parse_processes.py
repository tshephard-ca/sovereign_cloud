from __future__ import annotations

from pathlib import Path

from .models import ProcessEntry


def parse_processes_text(text: str) -> tuple[list[ProcessEntry], list[str]]:
    entries: list[ProcessEntry] = []
    warnings: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(maxsplit=2)
        pid = None
        command = ""
        args = None
        if parts and parts[0].isdigit():
            pid = int(parts[0])
            if len(parts) >= 2:
                command = parts[1]
            if len(parts) >= 3:
                args = parts[2]
        else:
            command = parts[0]
            if len(parts) >= 2:
                args = " ".join(parts[1:])
        if not command:
            warnings.append(f"PS_UNPARSED_LINE:{line}")
            continue
        entries.append(ProcessEntry(pid=pid, command=command, args=args, raw=line))

    if not entries:
        warnings.append("PS_NO_PROCESSES_PARSED")
    if entries and any(entry.args is None for entry in entries):
        warnings.append("PS_PROCESS_ARGS_MISSING")
    return entries, warnings


def parse_processes_file(path: Path) -> tuple[list[ProcessEntry], list[str]]:
    return parse_processes_text(path.read_text(encoding="utf-8", errors="replace"))


from __future__ import annotations

from pathlib import Path


REQUESTS_PATTERN = "requests" + "."
URLLIB_PATTERN = "urllib" + ".request"
HTTP_CLIENT_PATTERN = "http" + ".client"
SOCKET_PATTERN = "socket" + "."
SCONTROL_UPDATE_PATTERN = "scontrol update " + "NodeName"
SBATCH_PATTERN = "sbatch" + " "
PARAMIKO_PATTERN = "para" + "miko"
FABRIC_PATTERN = "fabric" + ".Connection"
REDFISH_PATTERN = "redfish" + "_client"
IPMITOOL_PATTERN = "ipmi" + "tool"

FORBIDDEN_PATTERNS = [
    REQUESTS_PATTERN,
    URLLIB_PATTERN,
    HTTP_CLIENT_PATTERN,
    SOCKET_PATTERN,
    PARAMIKO_PATTERN,
    FABRIC_PATTERN,
    REDFISH_PATTERN,
    SCONTROL_UPDATE_PATTERN,
    SBATCH_PATTERN,
    IPMITOOL_PATTERN,
]

ALLOWED_FILES_WITH_PATTERNS = {
    "slurm_render.py": {SCONTROL_UPDATE_PATTERN},
    "planning.py": {SBATCH_PATTERN},
}


def run_runtime_guard(src_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(src_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        allowed = ALLOWED_FILES_WITH_PATTERNS.get(path.name, set())
        for pattern in FORBIDDEN_PATTERNS:
            if pattern not in text:
                continue
            if pattern in allowed:
                continue
            findings.append(f"{path}: forbidden live-operation or network pattern: {pattern}")
    return findings

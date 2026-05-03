from __future__ import annotations

import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

from .workflow import build_manifest


COLLECTOR_VERSION = "1.0"

COMMANDS: dict[str, list[str]] = {
    "df.txt": ["df", "-PT", "-B1"],
    "inode-df.txt": ["df", "-Pi"],
    "mount.txt": ["mount"],
    "fstab.txt": ["cat", "/etc/fstab"],
    "iostat.txt": ["iostat", "-x", "-d", "-m", "1", "5"],
    "ps.txt": ["ps", "-eo", "pid,comm,args", "--no-headers"],
    "findmnt.json": ["findmnt", "--json"],
    "lsblk.json": ["lsblk", "--json", "-O"],
    "blkid.txt": ["blkid"],
    "pvs.txt": ["pvs"],
    "vgs.txt": ["vgs"],
    "lvs.txt": ["lvs"],
}

MINIMAL_FILES = ["df.txt", "mount.txt", "fstab.txt", "iostat.txt", "ps.txt"]


class _BundleTextRedactor:
    def __init__(self, process_mode: str = "strict") -> None:
        self._path_map: dict[str, str] = {}
        self.process_mode = process_mode

    def _redact_path(self, path: str) -> str:
        if path.startswith(("/dev", "/proc", "/sys", "/run", "/tmp", "/boot", "/etc")):
            return path
        if path in {"/", "/var", "/var/lib", "/home"}:
            return path
        if path not in self._path_map:
            suffix = Path(path).name
            suffix = re.sub(r"[^A-Za-z0-9._-]", "_", suffix)[:48]
            if suffix in {"", ".", "/"}:
                suffix = "mount"
            self._path_map[path] = f"/redacted/path_{len(self._path_map) + 1:03d}/{suffix}"
        return self._path_map[path]

    def redact_ps(self, text: str) -> str:
        if self.process_mode == "none":
            return text
        lines = []
        for raw in text.splitlines():
            parts = raw.split(maxsplit=2)
            if not parts:
                continue
            if len(parts) >= 2 and parts[0].isdigit():
                pid, comm = parts[0], parts[1]
                args = parts[2] if len(parts) > 2 else ""
                if self.process_mode == "balanced":
                    safe_flags = []
                    for token in args.split():
                        if token.startswith("--") and "=" not in token:
                            safe_flags.append(token)
                        elif token.startswith("-") and len(token) <= 3:
                            safe_flags.append(token)
                    lines.append(" ".join([pid, comm, *safe_flags[:8]]).strip())
                else:
                    lines.append(f"{pid} {comm}")
            else:
                lines.append(parts[0])
        return "\n".join(lines) + ("\n" if lines else "")

    def redact_paths(self, text: str) -> str:
        pattern = re.compile(r"(?<![\w.-])/[A-Za-z0-9._~+@%=-][A-Za-z0-9._~+@%=/:-]*")
        return pattern.sub(lambda match: self._redact_path(match.group(0)), text)

    def redact(self, filename: str, text: str) -> str:
        if filename == "ps.txt":
            return self.redact_ps(text)
        if filename.endswith((".txt", ".json")):
            return self.redact_paths(text)
        return text

    def redaction_map(self) -> dict[str, Any]:
        import hashlib

        return {
            "schema_version": "1.0",
            "mode": "path_preserving",
            "entries": [
                {
                    "redacted_path": redacted,
                    "original_path_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                }
                for original, redacted in sorted(self._path_map.items(), key=lambda item: item[1])
            ],
        }


def _safe_host_facts() -> dict[str, Any]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
    }


def _load_manifest_for_update(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def collect_du_summary(
    bundle_dir: Path,
    *,
    data_paths: list[str],
    timeout_seconds: int = 30,
    redact_paths: bool = False,
) -> dict[str, Any]:
    """Collect path-scoped du data for user-declared data paths only."""
    if not data_paths:
        raise ValueError("at least one --data-path is required")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    redactor = _BundleTextRedactor()
    command_records: list[dict[str, Any]] = []
    rows = ["path\tbytes\tstatus\tmessage"]
    for raw_path in data_paths:
        target_path = Path(raw_path)
        command = ["du", "-sb", str(target_path)]
        command_for_manifest = command
        entry = {"file": "du-summary.txt", "command": command_for_manifest, "returncode": None, "status": "not_run"}
        display_path = redactor._redact_path(str(target_path)) if redact_paths else str(target_path)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            entry["returncode"] = completed.returncode
            entry["status"] = "ok" if completed.returncode == 0 else "command_failed"
            if completed.returncode == 0:
                first = completed.stdout.splitlines()[0] if completed.stdout.splitlines() else ""
                parts = first.split(maxsplit=1)
                size_bytes = parts[0] if parts and parts[0].isdigit() else ""
                rows.append(f"{display_path}\t{size_bytes}\tok\t")
            else:
                message = (completed.stderr or completed.stdout or "").splitlines()
                safe_message = redactor.redact_paths(message[0]) if redact_paths and message else (message[0] if message else "")
                rows.append(f"{display_path}\t\tcommand_failed\t{safe_message}")
        except FileNotFoundError:
            entry["status"] = "command_not_found"
            rows.append(f"{display_path}\t\tcommand_not_found\tdu command not found")
        except subprocess.TimeoutExpired:
            entry["status"] = "timeout"
            rows.append(f"{display_path}\t\ttimeout\tdu command timed out")
        if redact_paths:
            entry["command"] = ["du", "-sb", display_path]
        command_records.append(entry)
    (bundle_dir / "du-summary.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    if redact_paths:
        (bundle_dir / "redaction-map-du.json").write_text(
            json.dumps(redactor.redaction_map(), indent=2) + "\n",
            encoding="utf-8",
        )
    existing = _load_manifest_for_update(bundle_dir)
    manifest = build_manifest(
        bundle_dir,
        commands=[*(existing.get("commands") or []), *command_records],
        collector_version=str(existing.get("collector_version") or COLLECTOR_VERSION),
        redaction_mode=str(existing.get("redaction_mode") or ("du_redacted" if redact_paths else "none")),
        safe_host_facts=existing.get("safe_host_facts") if isinstance(existing.get("safe_host_facts"), dict) else _safe_host_facts(),
    )
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def collect_local_bundle(
    output_dir: Path,
    *,
    include_optional: bool = True,
    timeout_seconds: int = 20,
    redact_first: bool = False,
    process_redaction_mode: str = "strict",
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    if process_redaction_mode not in {"strict", "balanced", "none"}:
        raise ValueError("process_redaction_mode must be strict, balanced, or none")
    redactor = _BundleTextRedactor(process_mode=process_redaction_mode)
    command_records = []
    command_items = COMMANDS.items() if include_optional else [(filename, COMMANDS[filename]) for filename in MINIMAL_FILES]
    for filename, command in command_items:
        target = output_dir / filename
        entry = {"file": filename, "command": command, "returncode": None, "status": "not_run"}
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            stdout = redactor.redact(filename, completed.stdout) if redact_first else completed.stdout
            target.write_text(stdout, encoding="utf-8")
            if completed.stderr:
                stderr = redactor.redact(filename, completed.stderr) if redact_first else completed.stderr
                (output_dir / f"{filename}.stderr").write_text(stderr, encoding="utf-8")
            entry["returncode"] = completed.returncode
            entry["status"] = "ok" if completed.returncode == 0 else "command_failed"
        except FileNotFoundError:
            target.write_text("", encoding="utf-8")
            entry["status"] = "command_not_found"
        except subprocess.TimeoutExpired:
            target.write_text("", encoding="utf-8")
            entry["status"] = "timeout"
        command_records.append(entry)
    if redact_first:
        (output_dir / "redaction-map.json").write_text(
            json.dumps(redactor.redaction_map(), indent=2) + "\n",
            encoding="utf-8",
        )
    manifest = build_manifest(
        output_dir,
        commands=command_records,
        collector_version=COLLECTOR_VERSION,
        redaction_mode=f"redact_first:{process_redaction_mode}" if redact_first else "none",
        safe_host_facts=_safe_host_facts(),
    )
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

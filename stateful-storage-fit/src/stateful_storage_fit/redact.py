from __future__ import annotations

import copy
import re
from pathlib import PurePath
from typing import Any

from .models import CandidateDataMount, ProcessEntry


COMMON_PATHS = {
    "/",
    "/boot",
    "/boot/efi",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/tmp",
    "/var",
    "/var/lib",
    "/home",
}


class Redactor:
    def __init__(self) -> None:
        self._path_map: dict[str, str] = {}

    def redact_path(self, path: str) -> str:
        if path in COMMON_PATHS or path.startswith(("/proc/", "/sys/", "/dev/", "/run/", "/redacted/")):
            return path
        if path not in self._path_map:
            suffix = PurePath(path).name
            suffix = re.sub(r"[^A-Za-z0-9._-]", "_", suffix)[:48]
            if not suffix:
                suffix = "path"
            self._path_map[path] = f"/redacted/path_{len(self._path_map) + 1:03d}/{suffix}"
        return self._path_map[path]

    def redact_processes(self, processes: list[ProcessEntry]) -> list[ProcessEntry]:
        redacted: list[ProcessEntry] = []
        for process in processes:
            redacted.append(
                ProcessEntry(
                    pid=process.pid,
                    command=PurePath(process.command).name,
                    args=None,
                    raw=PurePath(process.command).name,
                )
            )
        return redacted

    def redact_mounts(self, candidates: list[CandidateDataMount]) -> list[CandidateDataMount]:
        redacted: list[CandidateDataMount] = []
        for candidate in candidates:
            data = candidate.dict() if hasattr(candidate, "dict") else candidate.model_dump()
            data["mount_path"] = self.redact_path(candidate.mount_path)
            redacted.append(CandidateDataMount(**data))
        return redacted

    def _redact_analysis_value(self, key: str, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._redact_analysis_value(k, v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._redact_analysis_value(key, item) for item in value]
        if isinstance(value, str):
            if key in {"mount_path", "target", "subject"} and value.startswith("/"):
                return self.redact_path(value)
        return value

    def redact_analysis(self, analysis: dict | None) -> dict | None:
        if analysis is None:
            return None
        redacted = copy.deepcopy(analysis)
        return self._redact_analysis_value("", redacted)

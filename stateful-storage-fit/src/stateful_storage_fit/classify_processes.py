from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath

from .models import ProcessEntry


DATABASE_PATTERNS = [
    r"^postgres$",
    r"^postmaster$",
    r"^mysqld$",
    r"^mariadbd$",
    r"^mongod$",
    r"^oracle$",
    r"^ora_",
    r"^db2sysc$",
    r"^sqlservr$",
    r"^cassandra$",
    r"^redis-server$",
    r"^elasticsearch$",
]

STATEFUL_PATTERNS = [
    r"^kafka$",
    r"^zookeeper$",
    r"^rabbitmq",
    r"^prometheus$",
    r"^influxd$",
    r"^clickhouse",
    r"^solr$",
]

FILE_SERVER_PATTERNS = [
    r"^smbd$",
    r"^nmbd$",
    r"^nfsd$",
    r"^ganesha",
    r"^minio$",
]


@dataclass
class ProcessClassification:
    database_processes: list[str] = field(default_factory=list)
    stateful_processes: list[str] = field(default_factory=list)
    file_server_processes: list[str] = field(default_factory=list)
    command_only: bool = False
    raw_block_required: bool = False
    raw_block_hint: bool = False


def _basename(command: str) -> str:
    return PurePath(command).name.lower()


def _matches(command: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, command, flags=re.I) for pattern in patterns)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def classify_processes(processes: list[ProcessEntry]) -> ProcessClassification:
    result = ProcessClassification(command_only=bool(processes) and any(p.args is None for p in processes))
    for process in processes:
        command = _basename(process.command)
        text = f"{command} {process.args or ''}".lower()
        if _matches(command, DATABASE_PATTERNS):
            _append_unique(result.database_processes, command)
        if _matches(command, STATEFUL_PATTERNS):
            _append_unique(result.stateful_processes, command)
        if _matches(command, FILE_SERVER_PATTERNS):
            _append_unique(result.file_server_processes, command)
        if "/dev/raw" in text:
            result.raw_block_required = True
            result.raw_block_hint = True
        elif re.search(r"\basm\b|/dev/mapper/[^ ]+", text):
            result.raw_block_hint = True
    return result


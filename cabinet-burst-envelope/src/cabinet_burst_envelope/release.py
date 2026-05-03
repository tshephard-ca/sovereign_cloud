from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .bundle import sha256_file
from .report import write_json


SKIP_DIRS = {".pytest_cache", "__pycache__", ".venv", "build", "dist", "out", ".git"}


def _iter_release_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def build_release_report(root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(root)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    files = []
    for path in _iter_release_files(source):
        relative = path.relative_to(source).as_posix()
        files.append({"path": relative, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    report = {
        "schema_version": "cabinet-burst-envelope.release.v1",
        "tool_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "file_count": len(files),
        "files": files,
    }
    write_json(target / "artifact_fingerprints.json", report)
    write_json(
        target / "sbom.spdx.json",
        {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "cabinet-burst-envelope-local-source",
            "documentNamespace": "https://example.invalid/cabinet-burst-envelope/local-source",
            "creationInfo": {"created": report["generated_at"], "creators": ["Tool: cabinet-burst-envelope"]},
            "files": [
                {
                    "SPDXID": f"SPDXRef-File-{index}",
                    "fileName": item["path"],
                    "checksums": [{"algorithm": "SHA256", "checksumValue": item["sha256"]}],
                }
                for index, item in enumerate(files, start=1)
            ],
        },
    )
    (target / "release_checklist.md").write_text(
        "\n".join(
            [
                "# Release Checklist",
                "",
                "- Run `python -m pytest -q`.",
                "- Generate synthetic benchmark output with `cabinet-burst-envelope benchmark`.",
                "- Review `artifact_fingerprints.json` and `sbom.spdx.json`.",
                "- Sign release artifacts using the maintainer-approved offline signing process.",
                "- Publish only source, schemas, examples, tests, and documentation.",
                "- Confirm no credentials, telemetry exports, or proprietary adapters are included.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report

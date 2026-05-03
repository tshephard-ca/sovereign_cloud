"""Review bundle creation for security, audit, and release handoff."""

from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_handoff_bundle(output_zip: Path, files: dict[str, Path | None]) -> dict[str, object]:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    manifest_files = []
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for arcname, path in sorted(files.items()):
            if path is None or not path.exists():
                continue
            archive.write(path, arcname)
            manifest_files.append({"path": arcname, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        manifest = {
            "schema_version": "rag_permission_canary.handoff_bundle.v1",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "purpose": "reviewable permission-regression evidence bundle",
            "files": manifest_files,
            "caveats": [
                "This bundle is evidence for the supplied canary pack only.",
                "It does not certify the full RAG system.",
                "Redacted artifacts may still contain sensitive identifiers if inputs were not synthetic.",
            ],
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest

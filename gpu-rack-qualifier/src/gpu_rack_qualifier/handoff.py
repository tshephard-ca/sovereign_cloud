from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .config import ensure_parent, utc_now_iso
from .evidence_bundle import sha256_file


def create_handoff_bundle(output_zip: Path, files: dict[str, Path | None], include_dirs: dict[str, Path | None] | None = None) -> dict[str, object]:
    ensure_parent(output_zip)
    manifest_files = []
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for arcname, path in sorted(files.items()):
            if path is None or not path.exists():
                continue
            archive.write(path, arcname)
            manifest_files.append({"path": arcname, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        for prefix, directory in sorted((include_dirs or {}).items()):
            if directory is None or not directory.exists() or not directory.is_dir():
                continue
            for path in sorted(item for item in directory.rglob("*") if item.is_file()):
                arcname = f"{prefix}/{path.relative_to(directory).as_posix()}"
                archive.write(path, arcname)
                manifest_files.append({"path": arcname, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        manifest = {
            "schema_version": "rackq.handoff_bundle.v1",
            "generated_at": utc_now_iso(),
            "mode": "REVIEW_ONLY",
            "files": manifest_files,
            "notes": [
                "This bundle is review-only.",
                "No Slurm state was changed.",
                "No BMC or network API was called.",
            ],
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest

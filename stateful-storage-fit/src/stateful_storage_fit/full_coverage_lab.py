from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .engine import analyze_paths
from .workflow import build_manifest, decision_record, now_utc, storage_profile_snapshot, validate_case


GIB = 1024**3


PROFILE_TEXT = """storage_classes:
  - name: balanced-block
    display_name: Balanced block-backed filesystem
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: standard
    max_size_gib: 8192
    supports_expansion: true
    supports_snapshots: true
  - name: performance-block
    display_name: Performance block-backed filesystem
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: fast
    max_size_gib: 16384
    supports_expansion: true
    supports_snapshots: true
  - name: shared-file
    display_name: Shared filesystem storage
    access_modes: [ReadWriteMany]
    volume_modes: [Filesystem]
    storage_kind: file
    performance_tier: standard
    max_size_gib: 16384
    supports_expansion: true
    supports_snapshots: false
  - name: direct-block
    display_name: Direct raw block volume
    access_modes: [ReadWriteOnce]
    volume_modes: [Block]
    storage_kind: block
    performance_tier: fast
    max_size_gib: 8192
    supports_expansion: false
    supports_snapshots: false
performance_tiers:
  standard: 1
  fast: 2
  low_latency: 3
"""


FAMILIES = {
    "relational_database": 25,
    "shared_filesystem": 25,
    "file_server": 15,
    "search_logging": 15,
    "queue_streaming": 10,
    "generic_stateful_app": 10,
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _iostat(device: str, *, await_ms: float = 2.0, util_pct: float = 12.0, reports: int = 12) -> str:
    lines = []
    for _ in range(reports):
        lines.append("Device r/s w/s rkB/s wkB/s await aqu-sz %util")
        lines.append(f"sda 0.1 0.1 4 4 0.5 0.01 1.0")
        lines.append(f"{device} 2.0 4.0 128 512 {await_ms:.1f} 0.5 {util_pct:.1f}")
        lines.append("")
    return "\n".join(lines)


def _case_shape(family: str, index: int) -> dict[str, Any]:
    shape = {
        "family": family,
        "mount_path": "/data",
        "source": "/dev/sdb1",
        "fs_type": "xfs",
        "used_gib": 120,
        "size_gib": 500,
        "capacity_pct": 24,
        "process": "100 appd /usr/bin/appd --data-dir /data\n",
        "await_ms": 2.0,
        "util_pct": 12.0,
        "purpose": "primary application data",
        "read_write_pattern": "read_write",
        "writer_topology": "single_writer",
        "outcome": "storage_fit_confirmed",
    }
    if family == "relational_database":
        shape.update({"process": "100 postgres /usr/bin/postgres -D /data/db\n", "purpose": "database data"})
        if index < 10:
            shape.update({"await_ms": 28.0, "util_pct": 84.0, "outcome": "storage_rework_required"})
        elif index < 20:
            shape.update({"used_gib": 480, "size_gib": 500, "capacity_pct": 96, "outcome": "storage_rework_required"})
        else:
            shape.update(
                {
                    "process": "100 postgres /usr/bin/postgres --device /dev/raw/raw1\n",
                    "purpose": "raw database device",
                    "read_write_pattern": "raw_device",
                    "outcome": "storage_fit_confirmed",
                }
            )
    elif family == "shared_filesystem":
        shape.update(
            {
                "mount_path": "/srv/content",
                "source": "fileserver:/exports/content",
                "fs_type": "nfs4",
                "process": "100 appd /usr/bin/appd --content /srv/content\n",
                "purpose": "shared content repository",
                "writer_topology": "multi_writer",
            }
        )
    elif family == "file_server":
        shape.update(
            {
                "mount_path": "/srv/files",
                "source": "fileserver:/exports/files",
                "fs_type": "nfs4",
                "process": "100 smbd /usr/sbin/smbd --foreground\n",
                "purpose": "file service data",
                "writer_topology": "multi_writer",
                "outcome": "storage_rework_required",
            }
        )
    elif family == "search_logging":
        shape.update(
            {
                "mount_path": "/var/lib/elasticsearch",
                "process": "100 elasticsearch /usr/share/elasticsearch/bin/elasticsearch\n",
                "purpose": "search index data",
            }
        )
        if index < 5:
            shape.update({"await_ms": 25.0, "util_pct": 81.0, "outcome": "storage_rework_required"})
    elif family == "queue_streaming":
        shape.update(
            {
                "mount_path": "/var/lib/kafka",
                "process": "100 kafka /usr/bin/kafka-server-start /etc/kafka/server.properties\n",
                "purpose": "stream log data",
            }
        )
    elif family == "generic_stateful_app":
        shape.update(
            {
                "mount_path": "/opt/appdata",
                "process": "100 worker /usr/local/bin/worker --state /opt/appdata\n",
                "purpose": "application state",
            }
        )
    return shape


def _df_text(shape: dict[str, Any]) -> str:
    size = int(shape["size_gib"] * GIB)
    used = int(shape["used_gib"] * GIB)
    avail = max(size - used, 0)
    return "\n".join(
        [
            "Filesystem Type 1B-blocks Used Available Use% Mounted on",
            f"/dev/sda1 ext4 {100 * GIB} {20 * GIB} {80 * GIB} 20% /",
            f"{shape['source']} {shape['fs_type']} {size} {used} {avail} {shape['capacity_pct']}% {shape['mount_path']}",
            "",
        ]
    )


def _mount_text(shape: dict[str, Any]) -> str:
    return "\n".join(
        [
            "/dev/sda1 on / type ext4 (rw,relatime)",
            f"{shape['source']} on {shape['mount_path']} type {shape['fs_type']} (rw,relatime)",
            "",
        ]
    )


def _fstab_text(shape: dict[str, Any]) -> str:
    return "\n".join(
        [
            "/dev/sda1 / ext4 defaults 0 1",
            f"{shape['source']} {shape['mount_path']} {shape['fs_type']} defaults 0 2",
            "",
        ]
    )


def _findmnt_json(shape: dict[str, Any]) -> str:
    return json.dumps(
        {
            "filesystems": [
                {"target": "/", "source": "/dev/sda1", "fstype": "ext4", "options": "rw,relatime"},
                {
                    "target": shape["mount_path"],
                    "source": shape["source"],
                    "fstype": shape["fs_type"],
                    "options": "rw,relatime",
                },
            ]
        },
        indent=2,
    )


def _lsblk_json(shape: dict[str, Any]) -> str:
    devices = [
        {"name": "sda", "type": "disk", "pkname": None, "mountpoint": None, "fstype": None, "size": "100G", "children": [
            {"name": "sda1", "type": "part", "pkname": "sda", "mountpoint": "/", "fstype": "ext4", "size": "100G"}
        ]},
    ]
    if str(shape["source"]).startswith("/dev/sdb"):
        devices.append(
            {
                "name": "sdb",
                "type": "disk",
                "pkname": None,
                "mountpoint": None,
                "fstype": None,
                "size": f"{shape['size_gib']}G",
                "children": [
                    {
                        "name": "sdb1",
                        "type": "part",
                        "pkname": "sdb",
                        "mountpoint": shape["mount_path"],
                        "fstype": shape["fs_type"],
                        "size": f"{shape['size_gib']}G",
                    }
                ],
            }
        )
    return json.dumps({"blockdevices": devices}, indent=2)


def _path_purpose(shape: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "paths": [
            {
                "path": shape["mount_path"],
                "purpose": shape["purpose"],
                "read_write_pattern": shape["read_write_pattern"],
                "writer_topology": shape["writer_topology"],
                "owner_confidence": "HIGH",
                "owner_id": "generated-owner",
                "confirmed_at": now_utc(),
                "notes": "Generated full-coverage lab owner attestation fixture.",
            }
        ],
    }


def _bundle(bundle_dir: Path, shape: dict[str, Any]) -> None:
    _write(bundle_dir / "df.txt", _df_text(shape))
    _write(bundle_dir / "mount.txt", _mount_text(shape))
    _write(bundle_dir / "fstab.txt", _fstab_text(shape))
    _write(bundle_dir / "iostat.txt", _iostat("sdb", await_ms=shape["await_ms"], util_pct=shape["util_pct"]))
    _write(bundle_dir / "ps.txt", shape["process"])
    _write(bundle_dir / "findmnt.json", _findmnt_json(shape))
    _write(bundle_dir / "lsblk.json", _lsblk_json(shape))
    _write(bundle_dir / "blkid.txt", '/dev/sdb1: UUID="generated" TYPE="xfs"\n')
    _write(bundle_dir / "pvs.txt", "PV VG Fmt Attr PSize PFree\n/dev/sdb lab lvm2 a-- 500g 0\n")
    _write(bundle_dir / "vgs.txt", "VG #PV #LV Attr VSize VFree\nlab 1 1 wz--n- 500g 0\n")
    _write(bundle_dir / "lvs.txt", "LV VG Attr LSize\napp lab -wi-ao---- 500g\n")
    _write(bundle_dir / "inode-df.txt", "Filesystem Inodes IUsed IFree IUse% Mounted on\n/dev/sdb1 1000000 10000 990000 1% " + shape["mount_path"] + "\n")
    _write(bundle_dir / "du-summary.txt", f"path\tbytes\tstatus\tmessage\n{shape['mount_path']}\t{int(shape['used_gib'] * GIB)}\tok\t\n")
    _write(bundle_dir / "path-purpose.yml", yaml.safe_dump(_path_purpose(shape), sort_keys=False))
    manifest = build_manifest(
        bundle_dir,
        commands=[
            {"file": name, "command": ["generated", name], "returncode": 0, "status": "ok"}
            for name in [
                "df.txt",
                "inode-df.txt",
                "mount.txt",
                "fstab.txt",
                "iostat.txt",
                "ps.txt",
                "findmnt.json",
                "lsblk.json",
                "blkid.txt",
                "pvs.txt",
                "vgs.txt",
                "lvs.txt",
                "du-summary.txt",
                "path-purpose.yml",
            ]
        ],
        collector_version="generated-full-coverage-1.0",
        redaction_mode="none",
        safe_host_facts={"system": "generated", "machine": "generated", "python_version": "generated"},
    )
    _write(bundle_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")


def _review(result: Any, reviewer: str) -> dict[str, Any]:
    return {
        "reviewer_id": reviewer,
        "reviewed_at": now_utc(),
        "fit_status": result.fit_status,
        "required_access_mode": result.required_access_mode,
        "required_volume_mode": result.required_volume_mode,
        "preferred_storage_kind": result.preferred_storage_kind,
        "confidence": result.confidence,
        "reason_code_agreement": result.reason_codes,
        "reason_code_disagreement": [],
        "notes": "Generated full-coverage lab expert review fixture.",
    }


def generate_full_coverage_lab(output_dir: Path, family_targets: dict[str, int] | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path = output_dir / "storage-profile.yml"
    _write(profile_path, PROFILE_TEXT)
    cases = []
    targets = family_targets or FAMILIES
    for family, count in targets.items():
        for index in range(count):
            case_id = f"{family}-{index + 1:03d}"
            shape = _case_shape(family, index)
            bundle_dir = output_dir / "bundles" / case_id
            _bundle(bundle_dir, shape)
            path_purpose_path = bundle_dir / "path-purpose.yml"
            analysis = analyze_paths(
                df=bundle_dir / "df.txt",
                mount=bundle_dir / "mount.txt",
                fstab=bundle_dir / "fstab.txt",
                iostat=bundle_dir / "iostat.txt",
                ps=bundle_dir / "ps.txt",
                storage_profile_path=profile_path,
                data_paths=[],
                strict=False,
                app_metadata={
                    "app_name": case_id,
                    "workload_family": family,
                    "path_purpose": yaml.safe_load(path_purpose_path.read_text(encoding="utf-8")),
                    "declared_data_paths": [shape["mount_path"]],
                },
            )
            result = analysis.result
            outcome_status = shape["outcome"]
            case = {
                "schema_version": "1.0",
                "id": case_id,
                "case_kind": "generated_full_coverage",
                "data_origin": "generated_full_coverage",
                "profile_origin": "generated_full_coverage",
                "lifecycle_state": "outcome_linked",
                "created_at": now_utc(),
                "bundle": {
                    "path": str(bundle_dir.resolve()),
                    "manifest": str((bundle_dir / "manifest.json").resolve()),
                    "validation": {},
                },
                "df": str((bundle_dir / "df.txt").resolve()),
                "mount": str((bundle_dir / "mount.txt").resolve()),
                "fstab": str((bundle_dir / "fstab.txt").resolve()),
                "iostat": str((bundle_dir / "iostat.txt").resolve()),
                "ps": str((bundle_dir / "ps.txt").resolve()),
                "storage_profile": str(profile_path.resolve()),
                "storage_profile_snapshot": storage_profile_snapshot(profile_path, origin="generated_full_coverage"),
                "data_paths": [shape["mount_path"]],
                "app_metadata": {"app_name": case_id, "workload_family": family, "path_purpose": _path_purpose(shape)},
                "engine_decision": decision_record(result),
                "expected_fit_status": result.fit_status,
                "expected_requirements": {
                    "required_access_mode": result.required_access_mode,
                    "required_volume_mode": result.required_volume_mode,
                    "preferred_storage_kind": result.preferred_storage_kind,
                },
                "expert_reviews": [_review(result, "generated-reviewer-a"), _review(result, "generated-reviewer-b")],
                "adjudication": None,
                "outcomes": [
                    {
                        "recorded_at": now_utc(),
                        "status": outcome_status,
                        "source_team": "generated-platform-review",
                        "confidence": "HIGH",
                        "target_storage_class": result.recommended_storage_class,
                        "final_storage_pattern": result.preferred_storage_kind,
                        "observed_storage_blockers": result.blockers,
                        "notes": "Generated full-coverage lab outcome fixture.",
                    }
                ],
                "business_impact": [
                    {
                        "recorded_at": now_utc(),
                        "assessment_minutes": 30,
                        "expert_review_minutes": 15,
                        "blocker_found_before_pilot": bool(result.blockers),
                        "failed_pilot_avoided": result.fit_status == "FAIL",
                        "platform_gap_identified": bool(result.blockers),
                        "decision": "proceed" if result.fit_status == "PASS" else "review",
                        "source": "generated-business-review",
                        "confidence": "HIGH",
                    }
                ],
            }
            case_path = output_dir / "corpus" / f"{case_id}.yml"
            _write(case_path, yaml.safe_dump(case, sort_keys=False))
            validation = validate_case(case_path)
            cases.append(
                {
                    "case_id": case_id,
                    "family": family,
                    "fit_status": result.fit_status,
                    "reason_codes": result.reason_codes,
                    "validation": validation,
                }
            )
    summary = {
        "schema_version": "1.0",
        "generated_at": now_utc(),
        "data_origin": "generated_full_coverage",
        "case_count": len(cases),
        "family_targets": targets,
        "cases": cases,
        "note": "Generated fixtures provide full regression coverage and simulated impact records; they are not empirical real-world calibration evidence.",
    }
    _write(output_dir / "full-coverage-lab-summary.json", json.dumps(summary, indent=2) + "\n")
    return summary

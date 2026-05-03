"""Deterministic input data and template generation."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from typing import Iterable

import yaml

from .answer_map import ANSWER_MAP_COLUMNS
from .assessment import build_preflight_assessment
from .lint_rules import analyze_inputs
from .report import write_findings_csv, write_observed_csv, write_owner_worklist_csv, write_preflight_assessment_json, write_summary_json
from .support_files import load_owner_map


BACKUP_TEMPLATE_COLUMNS = [
    "workload_name",
    "fqdn",
    "ip_addresses",
    "protected",
    "recovery_set",
    "include_in_recovery_set",
    "aliases",
    "role_tags",
    "os",
    "backup_job",
    "last_success_utc",
    "application_owner",
    "owner_team",
    "business_service",
    "criticality",
    "recovery_tier",
    "dependency_owner",
    "environment",
    "site",
    "notes",
]

DNS_TEMPLATE_COLUMNS = [
    "timestamp",
    "client_ip",
    "client_name",
    "qname",
    "qtype",
    "rcode",
    "answer_names",
    "answer_ips",
    "resolver_name",
    "resolver_ip",
    "query_id",
    "protocol",
    "view",
    "ttl",
    "raw_line",
    "source_file",
]

OWNER_MAP_COLUMNS = ["owner_team", "category", "contact", "notes"]

SAMPLE_SCENARIOS = [
    "pass-minimal",
    "missing-dns-resolver",
    "missing-directory-service",
    "missing-kerberos",
    "missing-global-catalog",
    "missing-database-host",
    "missing-file-share",
    "missing-license-server",
    "weak-vpn-signal",
    "external-ignored",
    "external-included",
    "unmapped-clients",
    "missing-answer-data",
    "role-tags-satisfy-directory",
    "multi-application-shared-prereq",
    "timestamp-windowing",
    "redaction-demo",
]


def init_inputs(output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(out / "backup_inventory_template.csv", BACKUP_TEMPLATE_COLUMNS, [])
    _write_csv(out / "dns_query_log_template.csv", DNS_TEMPLATE_COLUMNS, [])
    _write_csv(out / "offline_answer_map_template.csv", ANSWER_MAP_COLUMNS, [])
    _write_csv(out / "owner_map_template.csv", OWNER_MAP_COLUMNS, [])
    prereq_template = {
        "internal_domains": ["example.internal"],
        "prerequisites": [
            {
                "id": "license_core",
                "display_name": "License service",
                "category": "license_server",
                "names": ["license01.apps.example.internal"],
                "qname_regex": ["(^|\\.)license[0-9-]*\\.apps\\.example\\.internal$"],
                "required_in_recovery_set": True,
            },
            {
                "id": "database_core",
                "display_name": "Core database service",
                "category": "database_host",
                "names": ["sql01.apps.example.internal"],
                "qname_regex": ["(^|\\.)(sql|db)[0-9-]*\\.apps\\.example\\.internal$"],
                "required_in_recovery_set": True,
            }
        ],
    }
    resolver_template = {"resolvers": [{"name": "dns01.example.internal", "ip_addresses": ["10.0.0.10"], "recovery_required": True}]}
    policy_template = {
        "window_hours": 24,
        "min_query_count": 2,
        "require_resolver_identity_for_pass": True,
        "include_external_by_default": False,
    }
    _write_yaml(out / "known_prereqs_template.yml", prereq_template)
    _write_yaml(out / "prerequisite_catalog_template.yml", prereq_template)
    _write_yaml(out / "resolver_hints_template.yml", resolver_template)
    _write_yaml(out / "required_resolvers_template.yml", resolver_template)
    _write_yaml(out / "thresholds_template.yml", policy_template)
    _write_yaml(out / "policy_template.yml", policy_template)
    _write_yaml(
        out / "recovery_sets_template.yml",
        {"recovery_sets": [{"name": "dr-test-001", "purpose": "application recovery-test preflight", "site": "recovery-lab"}]},
    )
    _write_preflight_package(out / "preflight_package_template.yml", template=True)
    _write_yaml(
        out / "accepted_risks_template.yml",
        {
            "accepted_risks": [
                {
                    "id": "example_external_service",
                    "category": "vpn_endpoint",
                    "name": "portal.external.test",
                    "reason": "Provided outside this recovery set for this test scenario.",
                    "expires": "2026-12-31",
                }
            ]
        },
    )


def generate_sample_data(scenario: str, output_dir: str | Path) -> None:
    if scenario not in SAMPLE_SCENARIOS:
        raise ValueError(f"unknown sample scenario {scenario!r}; valid scenarios: {', '.join(SAMPLE_SCENARIOS)}")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    inventory = _base_inventory()
    include = {
        "dns01": True,
        "dc01": True,
        "sql01": True,
        "files01": True,
        "license01": True,
        "vpn01": True,
    }
    if scenario == "missing-dns-resolver":
        include["dns01"] = False
    if scenario in {"missing-directory-service", "missing-kerberos", "missing-global-catalog"}:
        include["dc01"] = False
    if scenario in {"missing-database-host", "multi-application-shared-prereq"}:
        include["sql01"] = False
    if scenario == "missing-file-share":
        include["files01"] = False
    if scenario == "missing-license-server":
        include["license01"] = False
    if scenario == "weak-vpn-signal":
        include["vpn01"] = False
    if scenario == "pass-minimal":
        include = {key: True for key in include}
    for row in inventory:
        name = row["workload_name"]
        if name in include:
            row["recovery_set"] = "dr-test-001" if include[name] else "shared-services"
            row["include_in_recovery_set"] = "true" if include[name] else "false"

    dns = _base_dns()
    if scenario == "missing-database-host":
        for idx, client in enumerate([("10.0.1.10", "app01.apps.example.internal"), ("10.0.1.11", "app02.apps.example.internal"), ("10.0.1.10", "app01.apps.example.internal"), ("10.0.1.11", "app02.apps.example.internal")], start=1):
            dns.append(
                _dns(
                    f"2026-04-29T08:{20 + idx:02d}:00Z",
                    client[0],
                    "sql01.apps.example.internal",
                    "A",
                    client_name=client[1],
                    answer_ips="10.0.2.30",
                )
            )
    if scenario == "external-ignored":
        dns.append(_dns("2026-04-29T09:00:00Z", "10.0.1.10", "portal.external.test", "A", answer_ips="44.55.66.77"))
    if scenario == "external-included":
        dns.append(_dns("2026-04-29T09:00:00Z", "10.0.1.10", "portal.external.test", "A", answer_ips="44.55.66.77"))
    if scenario == "unmapped-clients":
        dns.append(_dns("2026-04-29T09:10:00Z", "10.0.9.90", "db02.apps.example.internal", "A", client_name="unmapped.example.internal", answer_ips="10.0.2.31"))
    if scenario == "missing-answer-data":
        dns = [_dns("2026-04-29T08:00:00Z", "10.0.1.10", "_ldap._tcp.dc._msdcs.corp.example.internal", "SRV")]
    if scenario == "timestamp-windowing":
        dns.append(_dns("2026-04-25T08:00:00Z", "10.0.1.10", "oldsql.apps.example.internal", "A", answer_ips="10.0.2.80"))
    if scenario == "multi-application-shared-prereq":
        dns.append(_dns("2026-04-29T08:21:00Z", "10.0.1.11", "sql01.apps.example.internal", "A", answer_ips="10.0.2.30", client_name="app02.apps.example.internal"))

    _write_csv(out / "backup_inventory.csv", BACKUP_TEMPLATE_COLUMNS, inventory)
    _write_csv(out / "dns_queries.csv", DNS_TEMPLATE_COLUMNS, dns)
    _write_answer_map(out)
    _write_owner_map(out)
    _write_accepted_risks(out)
    _write_recovery_sets(out)
    _write_known_and_hints(out)
    _write_yaml(out / "thresholds.yml", _thresholds())
    _write_yaml(out / "policy.yml", _thresholds())
    _write_preflight_package(out / "preflight_package.yml")
    result = analyze_inputs(
        backup_inventory=out / "backup_inventory.csv",
        dns_log=out / "dns_queries.csv",
        recovery_set_name="dr-test-001",
        known_prereqs_path=out / "prerequisite_catalog.yml",
        resolver_hints_path=out / "required_resolvers.yml",
        answer_map_path=out / "answer_map.csv",
        accepted_risks_path=out / "accepted_risks.yml",
        recovery_sets_path=out / "recovery_sets.yml",
        config_path=out / "policy.yml",
        include_external=scenario == "external-included",
        include_unmapped_clients=scenario == "unmapped-clients",
    )
    write_findings_csv(out / "expected_findings.csv", result.findings)
    write_observed_csv(out / "expected_observed_prereqs.csv", result.observed)
    write_summary_json(out / "expected_summary.json", result.summary)
    assessment = build_preflight_assessment(findings=result.findings, summary=result.summary, owner_map=load_owner_map(out / "owner_map.csv"))
    write_preflight_assessment_json(out / "expected_preflight_assessment.json", assessment)
    write_owner_worklist_csv(out / "expected_owner_worklist.csv", assessment.owner_work_items)
    _write_accuracy_report(out, _expected_missing_for_scenario(scenario), result)


def generate_benchmark_data(
    output_dir: str | Path,
    *,
    protected_systems: int,
    queries: int,
    missing_prereq_rate: float,
    seed: int,
    timestamp_span_hours: int = 24,
    outcome_profile: str = "fail",
) -> None:
    if outcome_profile not in {"pass", "review", "fail", "mixed"}:
        raise ValueError("outcome_profile must be one of: pass, review, fail, mixed")
    rng = random.Random(seed)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    inventory = _base_inventory()
    inventory.append(_inv("dns02", "dns02.example.internal", "10.0.0.11", "true", "dr-test-001", "true", "dns_resolver"))
    inventory.append(_inv("ntp01", "ntp01.example.internal", "10.0.0.12", "true", "time-services", "false", "time_service"))
    inventory.append(_inv("stale01", "stale01.apps.example.internal", "10.1.250.10", "false", "retired", "false", "application", notes="stale inventory row retained for parser coverage"))
    inventory.append(_inv("dupehost01", "app-duplicate.apps.example.internal", "10.1.250.11", "true", "dr-test-001", "true", "application", aliases="legacy-dupe|APP-DUPLICATE"))
    inventory.append(_inv("dupehost02", "app-duplicate.apps.example.internal", "10.1.250.12", "true", "dr-test-001", "true", "application", aliases="legacy-dupe-conflict"))
    inventory.append(_inv("dupeip01", "dupeip01.apps.example.internal", "10.1.250.20", "true", "dr-test-001", "true", "application"))
    inventory.append(_inv("dupeip02", "dupeip02.apps.example.internal", "10.1.250.20", "true", "dr-test-001", "true", "application"))
    protected_seed_count = sum(1 for row in inventory if row["protected"] == "true")
    app_count = max(1, protected_systems - protected_seed_count)
    sites = ["primary", "secondary", "lab"]
    environments = ["prod", "test", "dev"]
    for idx in range(1, app_count + 1):
        site = sites[idx % len(sites)]
        environment = environments[idx % len(environments)]
        roles = "application"
        if idx % 53 == 0:
            roles = "application;database_client"
        elif idx % 71 == 0:
            roles = "application;file_client"
        inventory.append(
            {
                "workload_name": f"app{idx:04d}",
                "fqdn": f"app{idx:04d}.apps.example.internal",
                "ip_addresses": _app_ips(idx),
                "protected": "true",
                "recovery_set": "dr-test-001",
                "include_in_recovery_set": "true",
                "aliases": _app_aliases(idx),
                "role_tags": roles,
                "os": _os_for_idx(idx),
                "backup_job": f"job-{environment}-{site}",
                "last_success_utc": (datetime(2026, 4, 29, 2, 0, tzinfo=timezone.utc) - timedelta(hours=idx % 36)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "application_owner": f"owner-{idx % 12:02d}",
                "owner_team": _owner_team_for_idx(idx),
                "business_service": _business_service_for_idx(idx),
                "criticality": _criticality_for_idx(idx),
                "recovery_tier": _recovery_tier_for_idx(idx),
                "dependency_owner": _owner_team_for_idx(idx),
                "environment": environment,
                "site": site,
                "notes": "",
            }
        )
    shared_candidates = {"sql01", "files01", "license01", "vpn01", "ntp01", "dns02", "coordinator01"}
    excluded_shared: list[str] = []
    forced_missing = {"files01", "license01", "vpn01", "coordinator01"} if outcome_profile == "fail" else set()
    if outcome_profile == "pass":
        missing_prereq_rate = 0.0
    elif outcome_profile == "review":
        missing_prereq_rate = 0.0
    elif outcome_profile == "mixed":
        missing_prereq_rate = max(missing_prereq_rate, 0.2)
    for row in inventory:
        if row["workload_name"] in forced_missing or (row["workload_name"] in shared_candidates and rng.random() < missing_prereq_rate):
            row["recovery_set"] = "shared-services"
            row["include_in_recovery_set"] = "false"
            excluded_shared.append(row["workload_name"])
    dns: list[dict[str, str]] = []
    targets = _benchmark_targets(app_count=app_count, outcome_profile=outcome_profile)
    newest = datetime(2026, 4, 29, 23, 59, tzinfo=timezone.utc)
    span_minutes = max(60, int(timestamp_span_hours) * 60)
    for idx in range(queries):
        app_idx = rng.randint(1, app_count)
        unmapped = rng.random() < 0.015
        client_name_only = not unmapped and rng.random() < 0.05
        client_ip_only = not unmapped and not client_name_only and rng.random() < 0.05
        ambiguous_shared_ip = not unmapped and rng.random() < 0.015
        client_ip = _benchmark_client_ip(app_idx, idx, unmapped=unmapped, client_name_only=client_name_only, ambiguous_shared_ip=ambiguous_shared_ip)
        client_name = "" if client_ip_only else ("unmapped.example.internal" if unmapped else _client_name_for_idx(app_idx, rng))
        profile = _app_query_profile(app_idx)
        target = rng.choices(targets, weights=[_profiled_weight(item, profile) for item in targets], k=1)[0]
        age_minutes = _benchmark_age_minutes(idx, app_idx, str(target.get("cadence", "random")), span_minutes, rng)
        timestamp = (newest - timedelta(minutes=age_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        qtype = str(target["qtype"])
        rcode = target.get("rcode", "NOERROR")
        if rng.random() < 0.015:
            rcode = "NXDOMAIN"
        elif rng.random() < 0.005:
            rcode = "SERVFAIL"
        answer_names = str(target.get("answer_names", ""))
        answer_ips = str(target.get("answer_ips", ""))
        if rng.random() < 0.08:
            answer_names = ""
        if rng.random() < 0.04:
            answer_ips = ""
        resolver = ("dns02.example.internal", "10.0.0.11") if rng.random() < 0.35 else ("dns01.example.internal", "10.0.0.10")
        if rng.random() < 0.02:
            resolver = ("", "")
        qname = "" if idx % 1499 == 0 else str(target["qname"])
        if idx % 1777 == 0:
            client_ip = "not_an_ip"
        if idx % 1223 == 0:
            qtype = "UNSUPPORTED"
            qname = "odd..name.apps.example.internal"
            answer_names = "odd target name"
            answer_ips = "999.999.999.999"
        if idx % 1613 == 0:
            answer_ips = f"{answer_ips}|999.999.999.999" if answer_ips else "999.999.999.999"
        if idx % 1999 == 0 and client_name:
            client_name = client_name.replace(".", " . ").upper() + "."
        dns.append(
            _dns(
                timestamp,
                client_ip,
                qname,
                qtype,
                client_name=client_name,
                answer_names=answer_names,
                answer_ips=answer_ips,
                rcode=rcode,
                resolver_name=resolver[0],
                resolver_ip=resolver[1],
                source_file=f"synthetic-{idx % 4}.csv",
                query_id=f"q-{seed}-{idx:08d}",
                protocol="udp" if rng.random() < 0.94 else "tcp",
                view=profile,
                ttl=str(target.get("ttl", rng.choice([30, 60, 120, 300, 900]))),
                raw_line=f"synthetic row {idx} {target['qtype']} {qname}",
            )
        )
    _write_csv(out / "backup_inventory.csv", BACKUP_TEMPLATE_COLUMNS, inventory)
    _write_csv(out / "dns_queries.csv", DNS_TEMPLATE_COLUMNS, dns)
    _write_malformed_dns_fixture(out)
    _write_answer_map(out)
    _write_owner_map(out)
    _write_accepted_risks(out)
    _write_recovery_sets(out)
    _write_known_and_hints(out, include_secondary_resolver=True)
    _write_yaml(out / "thresholds.yml", _thresholds())
    _write_yaml(out / "policy.yml", _thresholds())
    _write_preflight_package(out / "preflight_package.yml", compare_window_hours=[24, 168])
    analysis = analyze_inputs(
        backup_inventory=out / "backup_inventory.csv",
        dns_log=out / "dns_queries.csv",
        recovery_set_name="dr-test-001",
        known_prereqs_path=out / "prerequisite_catalog.yml",
        resolver_hints_path=out / "required_resolvers.yml",
        answer_map_path=out / "answer_map.csv",
        accepted_risks_path=out / "accepted_risks.yml",
        recovery_sets_path=out / "recovery_sets.yml",
        config_path=out / "policy.yml",
        include_unmapped_clients=True,
    )
    write_findings_csv(out / "expected_findings.csv", analysis.findings)
    write_observed_csv(out / "expected_observed_prereqs.csv", analysis.observed)
    write_summary_json(out / "expected_summary.json", analysis.summary)
    assessment = build_preflight_assessment(findings=analysis.findings, summary=analysis.summary, owner_map=load_owner_map(out / "owner_map.csv"))
    write_preflight_assessment_json(out / "expected_preflight_assessment.json", assessment)
    write_owner_worklist_csv(out / "expected_owner_worklist.csv", assessment.owner_work_items)
    expected_missing = _expected_missing_from_inventory(inventory)
    _write_accuracy_report(out, expected_missing, analysis)
    (out / "expected_counts.json").write_text(
        json.dumps(
            {
                "protected_systems": len(inventory),
                "dns_queries": len(dns),
                "seed": seed,
                "timestamp_span_hours": timestamp_span_hours,
                "outcome_profile": outcome_profile,
                "missing_prereq_rate": missing_prereq_rate,
                "excluded_shared_prerequisites": excluded_shared,
                "expected_missing_prerequisites": expected_missing,
                "inventory_quality_cases": ["stale_inventory_row", "duplicate_hostname", "duplicate_ip", "conflicting_alias", "multi_ip", "ipv6"],
                "main_dns_malformed_cases": ["blank_qname", "bad_client_ip", "unsupported_qtype", "invalid_answer_ip", "spaced_uppercase_client_name"],
                "target_mix": {str(item["qname"]): item["weight"] for item in targets},
                "query_profiles": ["database-heavy", "file-heavy", "remote-heavy", "auth-heavy", "general"],
                "notes": [
                    "Synthetic data intentionally includes unmapped clients, name-only clients, IP-only clients, ambiguous shared-IP clients, missing resolver identity, malformed query-name/client rows, missing answer data, multiple resolvers, multi-site inventory, mixed qtypes, optional DNS columns, varied application profiles, and configurable timestamp spread.",
                    "Additional malformed timestamp examples are written to dns_queries_malformed.csv so the main benchmark still supports window comparison.",
                    "DNS logs show lookup behavior only and are not proof of successful connections.",
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def generate_role_tag_worksheet(backup_inventory: str | Path, output: str | Path) -> None:
    with Path(backup_inventory).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    fieldnames = ["workload_name", "fqdn", "ip_addresses", "current_role_tags", "suggested_role_tags", "human_confirmed_role_tags", "notes"]
    output_rows = []
    for row in rows:
        name = (row.get("workload_name") or row.get("hostname") or row.get("name") or "").lower()
        fqdn = (row.get("fqdn") or row.get("dns_name") or "").lower()
        current = row.get("role_tags", "")
        suggested = _suggest_role_tags(name, fqdn)
        output_rows.append(
            {
                "workload_name": row.get("workload_name") or row.get("hostname") or row.get("name") or "",
                "fqdn": row.get("fqdn") or row.get("dns_name") or "",
                "ip_addresses": row.get("ip_addresses") or row.get("ip") or row.get("guest_ip") or "",
                "current_role_tags": current,
                "suggested_role_tags": "|".join(suggested),
                "human_confirmed_role_tags": "",
                "notes": "",
            }
        )
    _write_csv(output, fieldnames, output_rows)


def _suggest_role_tags(name: str, fqdn: str) -> list[str]:
    text = f"{name}.{fqdn}"
    tags: list[str] = []
    if "dc" in name or "domain" in text:
        tags.extend(["domain_controller", "directory_service", "kerberos"])
    if "dns" in name:
        tags.append("dns_resolver")
    if "sql" in text or "db" in name:
        tags.append("database")
    if "file" in text or "fs" == name[:2] or "nas" in text:
        tags.append("file_server")
    if "lic" in text or "kms" in text:
        tags.append("license_server")
    if "vpn" in text or "remote" in text or "portal" in text:
        tags.append("vpn_endpoint")
    return tags


def _base_inventory() -> list[dict[str, str]]:
    return [
        _inv("app01", "app01.apps.example.internal", "10.0.1.10", "true", "dr-test-001", "true", "application"),
        _inv("app02", "app02.apps.example.internal", "10.0.1.11", "true", "dr-test-001", "true", "application"),
        _inv("dns01", "dns01.example.internal", "10.0.0.10", "true", "dr-test-001", "true", "dns_resolver"),
        _inv("dc01", "dc01.corp.example.internal", "10.0.0.20", "true", "dr-test-001", "true", "domain_controller;kerberos;global_catalog"),
        _inv("sql01", "sql01.apps.example.internal", "10.0.2.30", "true", "dr-test-001", "true", "database"),
        _inv("files01", "files01.apps.example.internal", "10.0.3.40", "true", "dr-test-001", "true", "file_server"),
        _inv("license01", "license01.apps.example.internal", "10.0.4.50", "true", "dr-test-001", "true", "license_server"),
        _inv("vpn01", "vpn01.example.internal", "10.0.5.60", "true", "dr-test-001", "true", "vpn_endpoint"),
        _inv("coordinator01", "coordinator01.apps.example.internal", "10.0.6.70", "true", "dr-test-001", "true", "other_prerequisite"),
    ]


def _base_dns() -> list[dict[str, str]]:
    return [
        _dns("2026-04-29T08:00:00Z", "10.0.1.10", "_ldap._tcp.dc._msdcs.corp.example.internal", "SRV", answer_names="dc01.corp.example.internal", answer_ips="10.0.0.20"),
        _dns("2026-04-29T08:05:00Z", "10.0.1.10", "_kerberos._tcp.corp.example.internal", "SRV", answer_names="dc01.corp.example.internal", answer_ips="10.0.0.20"),
        _dns("2026-04-29T08:10:00Z", "10.0.1.10", "_gc._tcp.corp.example.internal", "SRV", answer_names="dc01.corp.example.internal", answer_ips="10.0.0.20"),
        _dns("2026-04-29T08:20:00Z", "10.0.1.10", "sql01.apps.example.internal", "A", answer_ips="10.0.2.30"),
        _dns("2026-04-29T08:30:00Z", "10.0.1.10", "files01.apps.example.internal", "A", answer_ips="10.0.3.40"),
        _dns("2026-04-29T08:40:00Z", "10.0.1.10", "license01.apps.example.internal", "A", answer_ips="10.0.4.50"),
        _dns("2026-04-29T08:50:00Z", "10.0.1.10", "vpn01.example.internal", "A", answer_ips="10.0.5.60"),
    ]


def _benchmark_targets(*, app_count: int, outcome_profile: str) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = [
        {"qname": "sql01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.2.30", "weight": 16, "profiles": ["database-heavy"], "cadence": "business", "ttl": 300},
        {"qname": "_mssql._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "sql01.apps.example.internal", "answer_ips": "10.0.2.30", "weight": 4, "profiles": ["database-heavy"], "cadence": "startup", "ttl": 600},
        {"qname": "files01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.3.40", "weight": 13, "profiles": ["file-heavy"], "cadence": "business", "ttl": 300},
        {"qname": "_cifs._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "files01.apps.example.internal", "answer_ips": "10.0.3.40", "weight": 3, "profiles": ["file-heavy"], "cadence": "startup", "ttl": 600},
        {"qname": "license01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.4.50", "weight": 8, "profiles": ["general", "database-heavy", "file-heavy"], "cadence": "business", "ttl": 900},
        {"qname": "vpn01.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.5.60", "weight": 4, "profiles": ["remote-heavy"], "cadence": "business", "ttl": 300},
        {"qname": "coordinator01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.6.70", "weight": 3, "profiles": ["general", "auth-heavy"], "cadence": "business", "ttl": 300},
        {"qname": "ntp01.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.0.12", "weight": 5, "profiles": ["auth-heavy", "general"], "cadence": "hourly", "ttl": 900},
        {"qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "weight": 12, "profiles": ["auth-heavy", "general"], "cadence": "startup", "ttl": 600},
        {"qname": "_kerberos._tcp.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "weight": 8, "profiles": ["auth-heavy", "general"], "cadence": "startup", "ttl": 600},
        {"qname": "_gc._tcp.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "weight": 4, "profiles": ["auth-heavy"], "cadence": "startup", "ttl": 600},
        {"qname": "portal.external.test", "qtype": "A", "answer_names": "", "answer_ips": "44.55.66.77", "weight": 4, "profiles": ["remote-heavy"], "cadence": "business", "ttl": 300},
        {"qname": "telemetry.external.test", "qtype": "AAAA", "answer_names": "", "answer_ips": "", "weight": 2, "profiles": ["general"], "cadence": "background", "ttl": 60},
        {"qname": "10.1.0.10.in-addr.arpa", "qtype": "PTR", "answer_names": "app0001.apps.example.internal", "answer_ips": "", "weight": 2, "profiles": ["general"], "cadence": "background", "ttl": 300},
        {"qname": "missing-name.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "", "weight": 1, "rcode": "NXDOMAIN", "profiles": ["general"], "cadence": "background", "ttl": 60},
    ]
    if outcome_profile == "review":
        targets.append({"qname": "_ldap._tcp.pdc._msdcs.corp.example.internal", "qtype": "SRV", "answer_names": "", "answer_ips": "", "weight": 8, "profiles": ["auth-heavy", "general"], "cadence": "startup", "ttl": 600})

    benign_prefixes = ("api", "web", "config", "status", "metrics", "queue", "worker", "appsvc", "cacheview", "batch")
    qtypes = ("A", "AAAA", "CNAME", "TXT", "MX", "NS", "SOA", "HTTPS")
    benign_count = max(120, min(420, app_count // 2))
    for idx in range(1, benign_count + 1):
        prefix = benign_prefixes[idx % len(benign_prefixes)]
        qtype = qtypes[idx % len(qtypes)]
        domain = "apps.example.internal" if idx % 4 else "ops.example.internal"
        qname = f"{prefix}{idx:03d}.{domain}"
        answer_names = ""
        answer_ips = ""
        if qtype in {"A", "HTTPS"}:
            answer_ips = f"10.2.{idx // 200}.{idx % 200 + 20}"
        elif qtype == "AAAA":
            answer_ips = f"fd00:2::{idx:x}"
        elif qtype == "CNAME":
            answer_names = f"{prefix}{idx:03d}-target.{domain}"
        elif qtype in {"NS", "SOA"}:
            answer_names = f"ns{idx % 4 + 1}.example.internal"
        elif qtype == "MX":
            answer_names = f"mail{idx % 6 + 1}.example.internal"
        targets.append(
            {
                "qname": qname,
                "qtype": qtype,
                "answer_names": answer_names,
                "answer_ips": answer_ips,
                "weight": 1,
                "profiles": ["general", "database-heavy", "file-heavy", "remote-heavy", "auth-heavy"],
                "cadence": "background",
                "ttl": [30, 60, 120, 300, 900][idx % 5],
            }
        )
    for idx in range(1, 41):
        targets.append(
            {
                "qname": f"external{idx:03d}.external.test",
                "qtype": ("A", "AAAA", "TXT", "HTTPS")[idx % 4],
                "answer_names": "",
                "answer_ips": "" if idx % 4 else f"44.55.{idx // 255}.{idx % 255}",
                "weight": 1,
                "profiles": ["general", "remote-heavy"],
                "cadence": "background",
                "ttl": 60,
            }
        )
    return targets


def _app_query_profile(idx: int) -> str:
    profiles = ["database-heavy", "file-heavy", "remote-heavy", "auth-heavy", "general"]
    return profiles[idx % len(profiles)]


def _profiled_weight(target: dict[str, object], profile: str) -> int:
    base = int(target.get("weight", 1))
    profiles = set(target.get("profiles", [])) if isinstance(target.get("profiles"), list) else set()
    if profile in profiles:
        return base * 3
    if "general" in profiles:
        return base
    return max(1, base // 2)


def _benchmark_age_minutes(idx: int, app_idx: int, cadence: str, span_minutes: int, rng: random.Random) -> int:
    if cadence == "hourly":
        hour = rng.randint(0, max(0, span_minutes // 60 - 1))
        return min(span_minutes - 1, hour * 60 + app_idx % 8)
    if cadence == "startup":
        return min(span_minutes - 1, rng.choice([5, 10, 15, 30, 60, 120, 240, 480]) + (app_idx % 10))
    if cadence == "business":
        day_offset = rng.randint(0, max(0, span_minutes // (24 * 60) - 1))
        minute = rng.randint(8 * 60, 18 * 60)
        return min(span_minutes - 1, day_offset * 24 * 60 + minute)
    if cadence == "background":
        return min(span_minutes - 1, (idx * 17 + app_idx * 13 + rng.randint(0, 180)) % span_minutes)
    return rng.randint(0, span_minutes - 1)


def _benchmark_client_ip(app_idx: int, idx: int, *, unmapped: bool, client_name_only: bool, ambiguous_shared_ip: bool) -> str:
    if unmapped:
        return f"10.9.{idx % 200}.{idx % 240 + 10}"
    if client_name_only:
        return ""
    if ambiguous_shared_ip:
        return "10.1.250.20"
    return f"10.1.{app_idx // 200}.{app_idx % 200 + 10}"


def _app_ips(idx: int) -> str:
    primary = f"10.1.{idx // 200}.{idx % 200 + 10}"
    if idx % 17 == 0:
        return f"{primary};172.16.{idx % 20}.{idx % 200 + 20}"
    if idx % 29 == 0:
        return f"{primary};fd00::{idx:x}"
    return primary


def _app_aliases(idx: int) -> str:
    aliases = [f"app{idx:04d}", f"legacy-app{idx:04d}"]
    if idx % 11 == 0:
        aliases.append(f"CNAME-App{idx:04d}.apps.example.internal")
    if idx % 37 == 0:
        aliases.append("shared-conflict")
    return "|".join(aliases)


def _client_name_for_idx(idx: int, rng: random.Random) -> str:
    if idx % 11 == 0 and rng.random() < 0.3:
        return f"cname-app{idx:04d}.apps.example.internal"
    if idx % 37 == 0 and rng.random() < 0.2:
        return "shared-conflict"
    if rng.random() < 0.05:
        return f"APP{idx:04d}.APPS.EXAMPLE.INTERNAL."
    return f"app{idx:04d}.apps.example.internal"


def _os_for_idx(idx: int) -> str:
    values = ["linux", "windows", "unix", "appliance"]
    return values[idx % len(values)]


def _owner_team_for_idx(idx: int) -> str:
    teams = ["application-team", "platform-team", "database-team", "storage-team", "identity-team", "network-team"]
    return teams[idx % len(teams)]


def _business_service_for_idx(idx: int) -> str:
    services = ["order-entry", "member-service", "claims-processing", "billing", "case-management", "field-operations"]
    return services[idx % len(services)]


def _criticality_for_idx(idx: int) -> str:
    values = ["tier-1", "tier-2", "tier-3"]
    return values[idx % len(values)]


def _recovery_tier_for_idx(idx: int) -> str:
    values = ["0-4h", "4-24h", "24-72h"]
    return values[idx % len(values)]


def _inv(
    name: str,
    fqdn: str,
    ip: str,
    protected: str,
    recovery_set: str,
    include: str,
    role_tags: str,
    *,
    aliases: str = "",
    notes: str = "",
) -> dict[str, str]:
    owner_team = _owner_team_for_name(name, role_tags)
    return {
        "workload_name": name,
        "fqdn": fqdn,
        "ip_addresses": ip,
        "protected": protected,
        "recovery_set": recovery_set,
        "include_in_recovery_set": include,
        "aliases": aliases or f"{name}|{name.upper()}",
        "role_tags": role_tags,
        "os": _os_for_name(name, role_tags),
        "backup_job": f"job-{owner_team}",
        "last_success_utc": "2026-04-29T02:00:00Z",
        "application_owner": f"{owner_team}-owner",
        "owner_team": owner_team,
        "business_service": _business_service_for_name(name, role_tags),
        "criticality": "tier-1" if "application" in role_tags or "database" in role_tags else "tier-2",
        "recovery_tier": "0-4h" if "dns" in role_tags or "domain_controller" in role_tags else "4-24h",
        "dependency_owner": owner_team,
        "environment": "prod",
        "site": "primary",
        "notes": notes,
    }


def _owner_team_for_name(name: str, role_tags: str) -> str:
    if "dns" in role_tags:
        return "network-team"
    if "domain_controller" in role_tags or "kerberos" in role_tags:
        return "identity-team"
    if "database" in role_tags:
        return "database-team"
    if "file" in role_tags:
        return "storage-team"
    if "license" in role_tags:
        return "application-team"
    if "vpn" in role_tags:
        return "network-team"
    if "time" in role_tags:
        return "platform-team"
    return "application-team"


def _os_for_name(name: str, role_tags: str) -> str:
    if "dns" in role_tags or "domain_controller" in role_tags:
        return "windows"
    if "database" in role_tags or "file" in role_tags:
        return "linux"
    if "vpn" in role_tags:
        return "appliance"
    return "linux"


def _business_service_for_name(name: str, role_tags: str) -> str:
    if "application" in role_tags:
        return "order-entry"
    if "database" in role_tags:
        return "shared-data-services"
    if "file" in role_tags:
        return "shared-document-services"
    if "dns" in role_tags or "domain_controller" in role_tags:
        return "core-infrastructure"
    if "vpn" in role_tags:
        return "remote-access"
    return f"{name}-service"


def _dns(
    timestamp: str,
    client_ip: str,
    qname: str,
    qtype: str,
    *,
    client_name: str = "app01.apps.example.internal",
    answer_names: str = "",
    answer_ips: str = "",
    rcode: str = "NOERROR",
    resolver_name: str = "dns01.example.internal",
    resolver_ip: str = "10.0.0.10",
    query_id: str = "",
    protocol: str = "udp",
    view: str = "default",
    ttl: str = "300",
    raw_line: str = "",
    source_file: str = "synthetic.csv",
) -> dict[str, str]:
    return {
        "timestamp": timestamp,
        "client_ip": client_ip,
        "client_name": client_name,
        "qname": qname,
        "qtype": qtype,
        "rcode": rcode,
        "answer_names": answer_names,
        "answer_ips": answer_ips,
        "resolver_name": resolver_name,
        "resolver_ip": resolver_ip,
        "query_id": query_id,
        "protocol": protocol,
        "view": view,
        "ttl": ttl,
        "raw_line": raw_line,
        "source_file": source_file,
    }


def _write_known_and_hints(out: Path, *, include_secondary_resolver: bool = False) -> None:
    prereq_payload = {
        "internal_domains": ["example.internal", "corp.example"],
        "prerequisites": [
            {"id": "license_core", "display_name": "License service", "category": "license_server", "qname_regex": ["(^|\\.)license[0-9-]*\\.apps\\.example\\.internal$"], "required_in_recovery_set": True},
            {"id": "database_core", "display_name": "Core database service", "category": "database_host", "qname_regex": ["(^|\\.)(sql|db)[0-9-]*\\.apps\\.example\\.internal$"], "required_in_recovery_set": True},
            {"id": "file_services", "display_name": "File services", "category": "file_share", "qname_regex": ["(^|\\.)files?[0-9-]*\\.apps\\.example\\.internal$"], "required_in_recovery_set": True},
            {"id": "remote_access", "display_name": "Remote access portal", "category": "vpn_endpoint", "qname_regex": ["(^|\\.)vpn[0-9-]*\\.example\\.internal$"], "required_in_recovery_set": True},
            {"id": "time_source", "display_name": "Time service", "category": "time_service", "qname_regex": ["(^|\\.)ntp[0-9-]*\\.example\\.internal$"], "required_in_recovery_set": False},
            {"id": "batch_coordinator", "display_name": "Batch coordinator", "category": "other_prerequisite", "qname_regex": ["(^|\\.)coordinator[0-9-]*\\.apps\\.example\\.internal$"], "required_in_recovery_set": True},
        ],
    }
    _write_yaml(out / "known_prereqs.yml", prereq_payload)
    _write_yaml(out / "prerequisite_catalog.yml", prereq_payload)
    resolvers = [{"name": "dns01.example.internal", "ip_addresses": ["10.0.0.10"], "recovery_required": True}]
    if include_secondary_resolver:
        resolvers.append({"name": "dns02.example.internal", "ip_addresses": ["10.0.0.11"], "recovery_required": True})
    resolver_payload = {"resolvers": resolvers}
    _write_yaml(out / "resolver_hints.yml", resolver_payload)
    _write_yaml(out / "required_resolvers.yml", resolver_payload)


def _write_answer_map(out: Path) -> None:
    rows = [
        {"qname": "sql01.apps.example.internal", "qtype": "A", "answer_names": "sql01.apps.example.internal", "answer_ips": "10.0.2.30", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "_mssql._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "sql01.apps.example.internal", "answer_ips": "10.0.2.30", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "files01.apps.example.internal", "qtype": "A", "answer_names": "files01.apps.example.internal", "answer_ips": "10.0.3.40", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "_cifs._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "files01.apps.example.internal", "answer_ips": "10.0.3.40", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "license01.apps.example.internal", "qtype": "A", "answer_names": "license01.apps.example.internal", "answer_ips": "10.0.4.50", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "vpn01.example.internal", "qtype": "A", "answer_names": "vpn01.example.internal", "answer_ips": "10.0.5.60", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "coordinator01.apps.example.internal", "qtype": "A", "answer_names": "coordinator01.apps.example.internal", "answer_ips": "10.0.6.70", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "ntp01.example.internal", "qtype": "A", "answer_names": "ntp01.example.internal", "answer_ips": "10.0.0.12", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "_kerberos._tcp.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
        {"qname": "_gc._tcp.corp.example.internal", "qtype": "SRV", "answer_names": "dc01.corp.example.internal", "answer_ips": "10.0.0.20", "source": "offline-answer-map", "observed_utc": "2026-04-29T08:00:00Z"},
    ]
    _write_csv(out / "answer_map.csv", ANSWER_MAP_COLUMNS, rows)


def _write_owner_map(out: Path) -> None:
    rows = [
        {"owner_team": "network-team", "category": "dns_resolver|vpn_endpoint", "contact": "network-queue", "notes": "Owns resolver and remote-access prerequisite questions."},
        {"owner_team": "identity-team", "category": "directory_service|kerberos_service|global_catalog", "contact": "identity-queue", "notes": "Owns directory and authentication prerequisite questions."},
        {"owner_team": "database-team", "category": "database_host", "contact": "database-queue", "notes": "Owns database host prerequisite questions."},
        {"owner_team": "storage-team", "category": "file_share", "contact": "storage-queue", "notes": "Owns file service prerequisite questions."},
        {"owner_team": "platform-team", "category": "time_service", "contact": "platform-queue", "notes": "Owns time-source prerequisite questions."},
        {"owner_team": "application-team", "category": "license_server|other_prerequisite", "contact": "application-queue", "notes": "Owns application-specific prerequisite questions."},
    ]
    _write_csv(out / "owner_map.csv", OWNER_MAP_COLUMNS, rows)


def _write_accepted_risks(out: Path) -> None:
    _write_yaml(
        out / "accepted_risks.yml",
        {
            "accepted_risks": [
                {
                    "id": "external_portal_out_of_scope",
                    "category": "vpn_endpoint",
                    "name": "portal.external.test",
                    "reason": "External access is outside the isolated recovery-test preflight scope.",
                    "expires": "2026-12-31",
                }
            ]
        },
    )


def _write_recovery_sets(out: Path) -> None:
    _write_yaml(
        out / "recovery_sets.yml",
        {
            "recovery_sets": [
                {"name": "dr-test-001", "purpose": "application recovery-test preflight", "site": "lab"},
                {"name": "shared-services", "purpose": "shared prerequisite services", "site": "primary"},
                {"name": "time-services", "purpose": "time-source services", "site": "primary"},
                {"name": "retired", "purpose": "stale inventory coverage", "site": "primary"},
            ]
        },
    )


def _write_malformed_dns_fixture(out: Path) -> None:
    rows = [
        _dns("not-a-timestamp", "10.1.0.10", "sql01.apps.example.internal", "A", answer_ips="10.0.2.30"),
        _dns("2026-04-29T08:00:00Z", "not_an_ip", "files01.apps.example.internal", "A", answer_ips="10.0.3.40"),
        _dns("2026-04-29T08:00:00Z", "10.1.0.11", "", "A", answer_ips="10.0.2.30"),
        _dns("2026-04-29T08:00:00Z", "", "license01.apps.example.internal", "A", client_name="APP0001.APPS.EXAMPLE.INTERNAL.", answer_ips="10.0.4.50"),
    ]
    _write_csv(out / "dns_queries_malformed.csv", DNS_TEMPLATE_COLUMNS, rows)


def _expected_missing_for_scenario(scenario: str) -> list[str]:
    mapping = {
        "missing-dns-resolver": ["dns01.example.internal"],
        "missing-directory-service": ["dc01.corp.example.internal"],
        "missing-kerberos": ["dc01.corp.example.internal"],
        "missing-global-catalog": ["dc01.corp.example.internal"],
        "missing-database-host": ["sql01.apps.example.internal"],
        "missing-file-share": ["files01.apps.example.internal", "File services"],
        "missing-license-server": ["license01.apps.example.internal", "License service"],
        "weak-vpn-signal": ["vpn01.example.internal", "Remote access portal"],
        "multi-application-shared-prereq": ["sql01.apps.example.internal"],
    }
    return mapping.get(scenario, [])


def _expected_missing_from_inventory(inventory: list[dict[str, str]]) -> list[str]:
    result: list[str] = []
    for row in inventory:
        if "time_service" in row.get("role_tags", ""):
            continue
        if row.get("protected") == "true" and row.get("include_in_recovery_set") == "false":
            result.append(row.get("fqdn", "") or row.get("workload_name", ""))
    return [item for item in result if item]


def _write_accuracy_report(out: Path, expected_missing: list[str], result: object) -> None:
    findings = getattr(result, "findings", [])
    expected = {item.lower() for item in expected_missing}
    actual_names: set[str] = set()
    equivalent_expected_values: set[str] = set()
    for finding in findings:
        if finding.present_in_recovery_set or finding.severity not in {"CRITICAL", "WARNING", "REVIEW"}:
            continue
        candidates = {
            value.lower()
            for value in [
                finding.prerequisite_name,
                finding.prerequisite_target,
                finding.prerequisite_target_ip,
                *finding.example_qnames,
                *finding.example_answer_names,
                *finding.example_answer_ips,
            ]
            if value
        }
        actual_names.update(candidates)
        if candidates.intersection(expected):
            equivalent_expected_values.update(candidates)
    matched = [item for item in expected_missing if item.lower() in actual_names]
    missed = [item for item in expected_missing if item.lower() not in actual_names]
    unexpected = sorted(actual_names - expected - equivalent_expected_values)
    report = {
        "expected_missing": expected_missing,
        "matched_expected_missing": matched,
        "missed_expected_missing": missed,
        "unexpected_missing_candidates": unexpected,
        "accuracy_status": "PASS" if not missed else "REVIEW",
        "notes": [
            "This compares generated benchmark intent to output candidate names and targets.",
            "Unexpected candidates may still be valid review signals from DNS evidence.",
        ],
    }
    (out / "accuracy_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_preflight_package(path: str | Path, *, compare_window_hours: list[int] | None = None, template: bool = False) -> None:
    suffix = "_template" if template else ""
    payload = {
        "schema_version": "1.0",
        "recovery_set": "dr-test-001",
        "inputs": {
            "backup_inventory": f"backup_inventory{suffix}.csv",
            "dns_queries": f"dns_query_log{suffix}.csv" if template else "dns_queries.csv",
            "prerequisite_catalog": f"prerequisite_catalog{suffix}.yml",
            "required_resolvers": f"required_resolvers{suffix}.yml",
            "answer_map": "offline_answer_map_template.csv" if template else "answer_map.csv",
            "accepted_risks": f"accepted_risks{suffix}.yml",
            "recovery_sets": f"recovery_sets{suffix}.yml",
            "owner_map": f"owner_map{suffix}.csv",
            "policy": f"policy{suffix}.yml",
        },
        "policy": {
            "pack": "isolated_recovery_lab",
            "window_hours": 24,
            "compare_window_hours": compare_window_hours or [],
            "include_unmapped_clients": True,
            "include_external": False,
        },
    }
    _write_yaml(path, payload)


def _thresholds() -> dict[str, object]:
    return {
        "window_hours": 24,
        "min_query_count": 2,
        "max_examples_per_finding": 5,
        "max_source_rows_per_finding": 20,
        "high_confidence_min_clients": 2,
        "repeated_observation_min_count": 5,
        "unmapped_client_warning_pct": 20,
        "require_resolver_identity_for_pass": True,
        "include_external_by_default": False,
    }


def _write_csv(path: str | Path, fieldnames: list[str], rows: Iterable[dict[str, str]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_yaml(path: str | Path, data: object) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False)

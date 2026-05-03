"""Human and machine-readable schema metadata."""

from __future__ import annotations

from .answer_map import ANSWER_MAP_COLUMNS
from .columns import BACKUP_COLUMN_ALIASES, DNS_COLUMN_ALIASES
from .models import SUPPORTED_CATEGORIES
from .report import FINDINGS_COLUMNS, OBSERVED_COLUMNS, OWNER_WORKLIST_COLUMNS


REASON_CODES = [
    "DNS_RESOLVER_NOT_IN_RECOVERY_SET",
    "DNS_RESOLVER_IDENTITY_UNKNOWN",
    "DIRECTORY_SERVICE_LOOKUP_OBSERVED",
    "DIRECTORY_SERVICE_ROLE_NOT_IN_RECOVERY_SET",
    "KERBEROS_LOOKUP_OBSERVED",
    "KERBEROS_ROLE_NOT_IN_RECOVERY_SET",
    "GLOBAL_CATALOG_LOOKUP_OBSERVED",
    "GLOBAL_CATALOG_NOT_IN_RECOVERY_SET",
    "SPECIFIC_TARGET_NOT_IN_RECOVERY_SET",
    "TARGET_PRESENT_IN_RECOVERY_SET",
    "KNOWN_PREREQ_MATCH",
    "SRV_LOOKUP_MATCH",
    "INTERNAL_QNAME_HEURISTIC_MATCH",
    "EXTERNAL_QNAME_IGNORED",
    "EXTERNAL_QNAME_INCLUDED",
    "ANSWER_NAMES_PRESENT",
    "ANSWER_IPS_PRESENT",
    "ANSWER_DATA_MISSING",
    "PROTECTED_CLIENT_MAPPED",
    "UNMAPPED_DNS_CLIENT",
    "RECOVERY_SET_SCOPE_ASSUMED",
    "INTERNAL_DOMAINS_INFERRED",
    "LOW_QUERY_COUNT",
    "MULTIPLE_PROTECTED_SYSTEMS_OBSERVED",
    "ROLE_TAG_MATCH",
    "HOSTNAME_MATCH",
    "IP_MATCH",
    "ALIAS_MATCH",
    "NO_RECOVERY_SET_MATCH",
    "HEURISTIC_ONLY_REVIEW",
    "TIMESTAMP_UNPARSEABLE",
    "DNS_LOG_WINDOW_ASSUMED",
    "PDC_EMULATOR_LOOKUP_OBSERVED",
    "ANSWER_MAP_ENRICHED",
    "OPTIONAL_PREREQ_OBSERVED",
    "ACCEPTED_RISK_APPLIED",
]


MISSING_DATA_VALUES = [
    "resolver_name",
    "resolver_ip",
    "answer_names",
    "answer_ips",
    "client_ip",
    "client_name",
    "protected_system_ip",
    "protected_system_fqdn",
    "role_tags",
    "recovery_set",
    "include_in_recovery_set",
    "timestamp",
    "internal_domains",
    "known_prereqs",
]


def schema_catalog() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "inputs": {
            "backup_inventory": {
                "format": "csv",
                "required_any": {"workload_name": list(BACKUP_COLUMN_ALIASES["workload_name"])},
                "strongly_preferred": {
                    name: list(BACKUP_COLUMN_ALIASES[name])
                    for name in ["fqdn", "ip_addresses", "protected", "recovery_set", "include_in_recovery_set"]
                },
                "optional": {
                    name: list(BACKUP_COLUMN_ALIASES[name])
                    for name in [
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
                },
            },
            "dns_query_log": {
                "format": "csv",
                "required": {
                    "qname": list(DNS_COLUMN_ALIASES["qname"]),
                    "client_identity": list(DNS_COLUMN_ALIASES["client_ip"] + DNS_COLUMN_ALIASES["client_name"]),
                },
                "strongly_preferred": {
                    name: list(DNS_COLUMN_ALIASES[name])
                    for name in ["timestamp", "qtype", "rcode", "answer_names", "answer_ips", "resolver_name", "resolver_ip"]
                },
            },
            "answer_map": {"format": "csv", "columns": ANSWER_MAP_COLUMNS},
            "prerequisite_catalog": {"format": "yaml", "aliases": ["known_prereqs"], "categories": sorted(SUPPORTED_CATEGORIES)},
            "required_resolvers": {"format": "yaml", "aliases": ["resolver_hints"]},
            "known_prereqs": {"format": "yaml", "alias_for": "prerequisite_catalog", "categories": sorted(SUPPORTED_CATEGORIES)},
            "resolver_hints": {"format": "yaml", "alias_for": "required_resolvers"},
            "policy": {"format": "yaml", "aliases": ["thresholds", "config"]},
            "preflight_package": {
                "format": "yaml",
                "required": ["schema_version", "recovery_set", "inputs.backup_inventory", "inputs.dns_queries"],
                "optional_inputs": ["prerequisite_catalog", "required_resolvers", "answer_map", "accepted_risks", "recovery_sets", "owner_map", "policy"],
            },
        },
        "outputs": {
            "coverage_gaps_csv": {"aliases": ["findings_csv"], "columns": FINDINGS_COLUMNS},
            "evidence_detail_csv": {"aliases": ["observed_prereqs_csv"], "columns": OBSERVED_COLUMNS},
            "findings_csv": FINDINGS_COLUMNS,
            "observed_prereqs_csv": OBSERVED_COLUMNS,
            "owner_worklist_csv": OWNER_WORKLIST_COLUMNS,
            "preflight_assessment_json": {
                "required_top_level": [
                    "schema_version",
                    "tool_version",
                    "assessment_type",
                    "recovery_set",
                    "decision",
                    "business_impact",
                    "service_families",
                    "decisions",
                    "owner_work_items",
                    "evidence_quality",
                    "limitations",
                ]
            },
            "summary_json": {
                "required_top_level": [
                    "schema_version",
                    "tool_version",
                    "lint_status",
                    "recovery_set",
                    "input",
                    "evidence_quality",
                    "findings",
                    "categories",
                    "warnings",
                    "assumptions",
                    "run_metadata",
                ]
            },
        },
        "reason_codes": REASON_CODES,
        "missing_data_values": MISSING_DATA_VALUES,
    }

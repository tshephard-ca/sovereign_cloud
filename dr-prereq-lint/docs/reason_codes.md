# Reason Codes

Reason codes are audit detail. The primary review artifact is `preflight_assessment.json`; reason codes explain why a finding or evidence-quality warning exists.

## Finding And Warning Codes

- `DNS_RESOLVER_NOT_IN_RECOVERY_SET`: a required resolver is absent from the declared recovery set.
- `DNS_RESOLVER_IDENTITY_UNKNOWN`: resolver identity was not available in resolver hints or DNS rows.
- `DIRECTORY_SERVICE_LOOKUP_OBSERVED`: directory-service SRV lookup observed.
- `DIRECTORY_SERVICE_ROLE_NOT_IN_RECOVERY_SET`: role-level directory signal lacks a matching recovery-set role tag.
- `KERBEROS_LOOKUP_OBSERVED`: Kerberos/KDC SRV lookup observed.
- `KERBEROS_ROLE_NOT_IN_RECOVERY_SET`: Kerberos signal lacks a matching recovery-set role tag.
- `GLOBAL_CATALOG_LOOKUP_OBSERVED`: global catalog lookup observed.
- `GLOBAL_CATALOG_NOT_IN_RECOVERY_SET`: global catalog signal is absent from the recovery set.
- `SPECIFIC_TARGET_NOT_IN_RECOVERY_SET`: a target candidate is absent from the recovery set.
- `TARGET_PRESENT_IN_RECOVERY_SET`: observed target matched the recovery set.
- `KNOWN_PREREQ_MATCH`: prerequisite catalog rule matched.
- `SRV_LOOKUP_MATCH`: service-discovery SRV pattern matched.
- `INTERNAL_QNAME_HEURISTIC_MATCH`: internal-name heuristic matched.
- `EXTERNAL_QNAME_IGNORED`: external query ignored by default.
- `EXTERNAL_QNAME_INCLUDED`: external query included by flag.
- `ANSWER_NAMES_PRESENT`: DNS answer names were available.
- `ANSWER_IPS_PRESENT`: DNS answer IPs were available.
- `ANSWER_DATA_MISSING`: DNS answer names and IPs were absent.
- `PROTECTED_CLIENT_MAPPED`: DNS client mapped to a protected system.
- `UNMAPPED_DNS_CLIENT`: DNS client did not map to the backup inventory.
- `RECOVERY_SET_SCOPE_ASSUMED`: recovery-set inclusion was inferred.
- `INTERNAL_DOMAINS_INFERRED`: internal domains were inferred from inventory FQDNs.
- `LOW_QUERY_COUNT`: evidence count is below the configured threshold.
- `MULTIPLE_PROTECTED_SYSTEMS_OBSERVED`: more than one protected system observed the same candidate.
- `ROLE_TAG_MATCH`: recovery-set role tags satisfied role-level evidence.
- `HOSTNAME_MATCH`: recovery-set hostname matched.
- `IP_MATCH`: recovery-set IP matched.
- `ALIAS_MATCH`: recovery-set alias matched.
- `NO_RECOVERY_SET_MATCH`: no recovery-set match was found.
- `HEURISTIC_ONLY_REVIEW`: keyword-only evidence requires human review.
- `TIMESTAMP_UNPARSEABLE`: one or more DNS timestamps could not be parsed.
- `DNS_LOG_WINDOW_ASSUMED`: timestamp issues caused the tool to analyze all rows.
- `PDC_EMULATOR_LOOKUP_OBSERVED`: a PDC-emulator lookup pattern was observed.
- `ANSWER_MAP_ENRICHED`: offline answer-map data filled missing answer data.
- `OPTIONAL_PREREQ_OBSERVED`: prerequisite was observed but marked non-required by policy or accepted risk.
- `ACCEPTED_RISK_APPLIED`: an accepted-risk entry matched this finding.

## Missing-Data Values

- `resolver_name`
- `resolver_ip`
- `answer_names`
- `answer_ips`
- `client_ip`
- `client_name`
- `protected_system_ip`
- `protected_system_fqdn`
- `role_tags`
- `recovery_set`
- `include_in_recovery_set`
- `timestamp`
- `internal_domains`
- `known_prereqs`
